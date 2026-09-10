"""Gestione: utenti (inviti via Keycloak), ruoli e permessi, squadre."""

from __future__ import annotations

from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as df
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authn.jwt import invalidate_user_cache
from safe.apps.authz import resolve
from safe.apps.authz.drf import HasPermission
from safe.apps.authz.models import Role, RolePermission
from safe.apps.core.exceptions import BusinessError

from . import keycloak
from .models import AppUser, Team
from .serializers import (
    InviteSerializer,
    PermissionsPutSerializer,
    RoleSerializer,
    TeamSerializer,
    UserPatchSerializer,
    UserSerializer,
    apply_permissions,
    apply_teams,
    team_queryset,
    user_queryset,
)

INVITE_LIFESPAN = 7 * 24 * 3600


def actor(request: Request) -> AppUser:
    return cast(AppUser, request.user)


def _kc_call(fn, *args: Any, **kw: Any) -> Any:  # noqa: ANN001
    try:
        return fn(*args, **kw)
    except keycloak.KeycloakError as exc:
        raise BusinessError(exc.code, exc.detail) from exc


def send_invite(user: AppUser) -> None:
    client = keycloak.get_client()
    if not user.keycloak_id:
        user.keycloak_id = _kc_call(
            client.create_user,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            locale=user.locale,
        )
        user.save(update_fields=["keycloak_id", "updated_at"])
    _kc_call(
        client.send_actions_email,
        user.keycloak_id,
        actions=keycloak.invite_actions(user.mfa_required),
        redirect_uri=f"{settings.WEB_BASE_URL.rstrip('/')}/{user.locale}/home",
        lifespan=INVITE_LIFESPAN,
    )


# --- squadre ---------------------------------------------------------------------------


class TeamViewSet(viewsets.ModelViewSet):
    permission_classes = [HasPermission]
    permission_map = {"list": ("teams.view",), "retrieve": ("teams.view",), "*": ("teams.manage",)}
    serializer_class = TeamSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet:
        qs = team_queryset().order_by("name")
        if self.request.query_params.get("include_inactive") not in ("true", "1"):
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance: Team) -> None:
        """Disattivazione: bloccata se la squadra ha eventi (docs/05 §4.14)."""
        if instance.events.filter(deleted_at__isnull=True).exists():
            raise BusinessError("team_has_events", "La squadra ha eventi registrati: si può solo rinominare.")
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


# --- utenti ----------------------------------------------------------------------------


class UserFilter(df.FilterSet):
    status = df.CharFilter(field_name="status")
    team = df.UUIDFilter(field_name="user_teams__team_id", distinct=True)
    search = df.CharFilter(method="filter_search")

    def filter_search(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        from django.db.models import Q

        return qs.filter(
            Q(email__icontains=value) | Q(first_name__icontains=value) | Q(last_name__icontains=value)
        )


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [HasPermission]
    permission_map = {
        "list": ("users.view",),
        "retrieve": ("users.view",),
        "partial_update": ("users.manage",),
        "invite": ("users.invite",),
        "resend_invite": ("users.invite",),
        "disable": ("users.manage",),
        "enable": ("users.manage",),
        "permissions": ("users.assign_permissions",),
    }
    serializer_class = UserSerializer
    filterset_class = UserFilter
    pagination_class = None

    def get_queryset(self) -> QuerySet:
        return user_queryset()

    def _fresh(self, user: AppUser) -> Response:
        return Response(UserSerializer(user_queryset().get(pk=user.pk)).data)

    @extend_schema(request=InviteSerializer, responses={201: UserSerializer})
    @action(detail=False, methods=["post"])
    def invite(self, request: Request) -> Response:
        ser = InviteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if AppUser.all_objects.filter(email=d["email"]).exists():
            return Response(
                {"code": "email_in_use", "detail": "Esiste già un utente con questa email."},
                status=status.HTTP_409_CONFLICT,
            )
        me = actor(request)
        company = me.company
        with transaction.atomic():
            user = AppUser.objects.create(
                email=d["email"],
                first_name=d.get("first_name", ""),
                last_name=d.get("last_name", ""),
                locale=d.get("locale") or company.default_locale,
                status=AppUser.Status.INVITED,
                mfa_required=d.get("mfa_required", False),
                invited_at=timezone.now(),
                invited_by=me,
            )
            apply_teams(user, d.get("teams"), d.get("default_team"))
            apply_permissions(user, d.get("roles", []), [], [], me)
            send_invite(user)
            audit.record(
                "user.invite",
                "user",
                object_id=user.id,
                request=request,
                metadata={"roles": d.get("roles", [])},
            )
        return Response(UserSerializer(user_queryset().get(pk=user.pk)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(user_queryset(), pk=pk)
        ser = UserPatchSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        changed = []
        for f in ("first_name", "last_name", "locale", "mfa_required"):
            if f in d and getattr(user, f) != d[f]:
                setattr(user, f, d[f])
                changed.append(f)
        if changed:
            user.save(update_fields=[*changed, "updated_at"])
            if user.keycloak_id and any(f in changed for f in ("first_name", "last_name", "locale")):
                _kc_call(
                    keycloak.get_client().update_user,
                    user.keycloak_id,
                    **{f: d[f] for f in changed if f != "mfa_required"},
                )
        if "teams" in d:
            apply_teams(user, d["teams"], d.get("default_team"))
            changed.append("teams")
        audit.record("user.update", "user", object_id=user.id, request=request, changed_fields=changed)
        return self._fresh(user)

    @action(detail=True, methods=["post"], url_path="resend-invite")
    def resend_invite(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(AppUser.objects.all(), pk=pk)
        if user.status != AppUser.Status.INVITED:
            raise BusinessError("not_invited", "L'utente ha già completato l'accesso.")
        send_invite(user)
        user.invited_at = timezone.now()
        user.save(update_fields=["invited_at", "updated_at"])
        audit.record("user.invite_resend", "user", object_id=user.id, request=request)
        return self._fresh(user)

    @action(detail=True, methods=["post"])
    def disable(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(AppUser.objects.all(), pk=pk)
        if user.pk == actor(request).pk:
            raise BusinessError("self_disable", "Non puoi disattivare il tuo utente.")
        if user.status != AppUser.Status.DISABLED:
            user.status = AppUser.Status.DISABLED
            user.disabled_at = timezone.now()
            user.save(update_fields=["status", "disabled_at", "updated_at"])
            if user.keycloak_id:
                _kc_call(keycloak.get_client().set_enabled, user.keycloak_id, False)
            invalidate_user_cache(user)
            audit.record("user.disable", "user", object_id=user.id, request=request)
        return self._fresh(user)

    @action(detail=True, methods=["post"])
    def enable(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(AppUser.objects.all(), pk=pk)
        if user.status == AppUser.Status.DISABLED:
            user.status = AppUser.Status.ACTIVE if user.oidc_subject else AppUser.Status.INVITED
            user.disabled_at = None
            user.save(update_fields=["status", "disabled_at", "updated_at"])
            if user.keycloak_id:
                _kc_call(keycloak.get_client().set_enabled, user.keycloak_id, True)
            invalidate_user_cache(user)
            audit.record("user.enable", "user", object_id=user.id, request=request)
        return self._fresh(user)

    @extend_schema(request=PermissionsPutSerializer, responses=UserSerializer)
    @action(detail=True, methods=["put"])
    def permissions(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(AppUser.objects.all(), pk=pk)
        ser = PermissionsPutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        me = actor(request)
        if user.pk == me.pk and "users.assign_permissions" in d["denies"]:
            raise BusinessError("self_lockout", "Non puoi negare a te stesso la gestione dei permessi.")
        with transaction.atomic():
            apply_permissions(user, d["roles"], d["grants"], d["denies"], me)
        resolve.invalidate(user.id)
        audit.record(
            "user.permissions",
            "user",
            object_id=user.id,
            request=request,
            metadata={"roles": d["roles"], "grants": d["grants"], "denies": d["denies"]},
        )
        return self._fresh(user)


# --- ruoli -----------------------------------------------------------------------------


class RolesView(APIView):
    permission_classes = [HasPermission]
    permission_map = {"get": ("users.view",), "post": ("users.assign_permissions",)}

    @extend_schema(tags=["users"], responses=RoleSerializer(many=True))
    def get(self, request: Request) -> Response:
        roles = Role.objects.prefetch_related("role_permissions").order_by("company_id", "code")
        return Response(RoleSerializer(roles, many=True).data)

    @extend_schema(tags=["users"], request=RoleSerializer, responses={201: RoleSerializer})
    def post(self, request: Request) -> Response:
        ser = RoleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        with transaction.atomic():
            role = Role.objects.create(
                company_id=actor(request).company_id,
                code=d["code"],
                name_it=d["name_it"],
                name_en=d["name_en"],
                name_de=d["name_de"],
                is_system=False,
            )
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission_id=c) for c in set(d["permission_codes"])]
            )
        audit.record("role.create", "role", object_id=role.id, request=request, metadata={"code": role.code})
        return Response(
            RoleSerializer(Role.objects.prefetch_related("role_permissions").get(pk=role.pk)).data, status=201
        )
