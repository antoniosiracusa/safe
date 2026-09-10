from __future__ import annotations

from typing import Any

from django.db.models import Count, Q
from rest_framework import serializers

from safe.apps.authz.catalog import ALL_CODES
from safe.apps.authz.models import Role, UserPermission, UserRole
from safe.apps.lookups.fields import LookupCodeField
from safe.apps.rescue.models import Event

from .models import AppUser, Team, UserTeam

LOCALES = ("it", "en", "de")
ASSIGNABLE_CODES = tuple(c for c in ALL_CODES if c != "platform.admin")


# --- squadre ---------------------------------------------------------------------------


class TeamSerializer(serializers.ModelSerializer):
    body = LookupCodeField("team_body", required=False, allow_null=True)
    users_count = serializers.IntegerField(read_only=True)
    events_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "body", "is_active", "users_count", "events_count", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        qs = Team.objects.filter(name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Esiste già una squadra con questo nome.")
        return value


def team_queryset():  # noqa: ANN201
    return Team.objects.annotate(
        users_count=Count(
            "user_teams", filter=Q(user_teams__user__status=AppUser.Status.ACTIVE), distinct=True
        ),
        events_count=Count("events", filter=Q(events__deleted_at__isnull=True), distinct=True),
    ).select_related("body")


# --- utenti ----------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    teams = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    grants = serializers.SerializerMethodField()
    denies = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    devices_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = AppUser
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "locale",
            "status",
            "mfa_required",
            "is_platform_admin",
            "teams",
            "roles",
            "grants",
            "denies",
            "invited_at",
            "activated_at",
            "disabled_at",
            "last_login_at",
            "devices_count",
            "created_at",
        ]

    def get_teams(self, u: AppUser) -> list[dict[str, Any]]:
        uts = getattr(u, "_prefetched_objects_cache", {}).get("user_teams") or u.user_teams.select_related(
            "team"
        )
        return [{"id": str(ut.team_id), "name": ut.team.name, "is_default": ut.is_default} for ut in uts]

    def get_roles(self, u: AppUser) -> list[str]:
        return [ur.role.code for ur in u.user_roles.all()]

    def get_grants(self, u: AppUser) -> list[str]:
        return [
            up.permission_id for up in u.user_permissions.all() if up.effect == UserPermission.Effect.GRANT
        ]

    def get_denies(self, u: AppUser) -> list[str]:
        return [
            up.permission_id for up in u.user_permissions.all() if up.effect == UserPermission.Effect.DENY
        ]


def user_queryset():  # noqa: ANN201
    return (
        AppUser.objects.all()
        .prefetch_related("user_teams__team", "user_roles__role", "user_permissions")
        .annotate(devices_count=Count("devices", filter=Q(devices__status="authorized"), distinct=True))
        .order_by("last_name", "first_name", "email")
    )


class TeamsMixin(serializers.Serializer):
    teams = serializers.ListField(child=serializers.UUIDField(), required=False)
    default_team = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "teams" in attrs:
            ids = {str(t) for t in attrs["teams"]}
            found = {str(t) for t in Team.objects.filter(id__in=ids).values_list("id", flat=True)}
            if ids - found:
                raise serializers.ValidationError({"teams": ["Squadra non trovata."]})
            default = attrs.get("default_team")
            if default is not None and str(default) not in ids:
                raise serializers.ValidationError(
                    {"default_team": ["Deve essere una delle squadre assegnate."]}
                )
        return attrs


class InviteSerializer(TeamsMixin):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    locale = serializers.ChoiceField(choices=LOCALES, required=False)
    roles = serializers.ListField(child=serializers.SlugField(), required=False, default=list)
    mfa_required = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_roles(self, codes: list[str]) -> list[str]:
        found = set(Role.objects.filter(code__in=codes).values_list("code", flat=True))
        missing = [c for c in codes if c not in found]
        if missing:
            raise serializers.ValidationError(f"Ruolo sconosciuto: {', '.join(missing)}")
        return codes


class UserPatchSerializer(TeamsMixin):
    first_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    locale = serializers.ChoiceField(choices=LOCALES, required=False)
    mfa_required = serializers.BooleanField(required=False)


class PermissionsPutSerializer(serializers.Serializer):
    roles = serializers.ListField(child=serializers.SlugField(), default=list)
    grants = serializers.ListField(child=serializers.CharField(), default=list)
    denies = serializers.ListField(child=serializers.CharField(), default=list)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        found = set(Role.objects.filter(code__in=attrs["roles"]).values_list("code", flat=True))
        missing = [c for c in attrs["roles"] if c not in found]
        if missing:
            raise serializers.ValidationError({"roles": [f"Ruolo sconosciuto: {', '.join(missing)}"]})
        for key in ("grants", "denies"):
            bad = [c for c in attrs[key] if c not in ASSIGNABLE_CODES]
            if bad:
                raise serializers.ValidationError({key: [f"Permesso sconosciuto: {', '.join(bad)}"]})
        both = set(attrs["grants"]) & set(attrs["denies"])
        if both:
            raise serializers.ValidationError(
                {"denies": [f"Permesso sia concesso che negato: {', '.join(sorted(both))}"]}
            )
        return attrs


def apply_teams(user: AppUser, teams: list | None, default_team: Any) -> None:
    if teams is None:
        return
    ids = [str(t) for t in teams]
    UserTeam.objects.filter(user=user).exclude(team_id__in=ids).delete()
    existing = {str(ut.team_id): ut for ut in UserTeam.objects.filter(user=user)}
    default = str(default_team) if default_team else (ids[0] if ids else None)
    for tid in ids:
        ut = existing.get(tid)
        if ut is None:
            UserTeam.objects.create(user=user, team_id=tid, is_default=(tid == default))
        elif ut.is_default != (tid == default):
            ut.is_default = tid == default
            ut.save(update_fields=["is_default"])


def apply_permissions(
    user: AppUser, roles: list[str], grants: list[str], denies: list[str], actor: AppUser
) -> None:
    UserRole.objects.filter(user=user).exclude(role__code__in=roles).delete()
    have = set(UserRole.objects.filter(user=user).values_list("role__code", flat=True))
    for role in Role.objects.filter(code__in=[c for c in roles if c not in have]):
        UserRole.objects.create(user=user, role=role)
    wanted = {c: UserPermission.Effect.GRANT for c in grants} | {
        c: UserPermission.Effect.DENY for c in denies
    }
    UserPermission.objects.filter(user=user).exclude(permission_id__in=list(wanted)).delete()
    current = {up.permission_id: up for up in UserPermission.objects.filter(user=user)}
    for code, effect in wanted.items():
        up = current.get(code)
        if up is None:
            UserPermission.objects.create(user=user, permission_id=code, effect=effect, granted_by=actor)
        elif up.effect != effect:
            up.effect = effect
            up.granted_by = actor
            up.save(update_fields=["effect", "granted_by"])


# --- ruoli -----------------------------------------------------------------------------


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    is_custom = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "code", "name_it", "name_en", "name_de", "is_system", "is_custom", "permissions"]
        read_only_fields = ["id", "is_system"]

    def get_is_custom(self, r: Role) -> bool:
        return r.company_id is not None

    def get_permissions(self, r: Role) -> list[str]:
        return sorted(rp.permission_id for rp in r.role_permissions.all())

    def validate_code(self, value: str) -> str:
        if Role.objects.filter(code=value).exists():
            raise serializers.ValidationError("Codice ruolo già usato.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        codes = self.initial_data.get("permissions") if isinstance(self.initial_data, dict) else None
        if not isinstance(codes, list):
            raise serializers.ValidationError({"permissions": ["Elenco di permessi obbligatorio."]})
        bad = [c for c in codes if c not in ASSIGNABLE_CODES]
        if bad:
            raise serializers.ValidationError({"permissions": [f"Permesso sconosciuto: {', '.join(bad)}"]})
        attrs["permission_codes"] = codes
        return attrs


_ = Event  # usato dalle annotate (events related_name)
