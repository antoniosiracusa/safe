"""Eventi e persone: CRUD, blocco/sblocco, identità cifrata. Ogni operazione dichiara i permessi
(permission_map) e i queryset applicano lo scoping per squadra."""

from __future__ import annotations

import base64
from typing import cast

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from safe.apps.audit import service as audit
from safe.apps.authz.drf import HasPermission, PermissionDenied
from safe.apps.authz.resolve import effective_permissions
from safe.apps.core.exceptions import ConflictError
from safe.apps.crypto.models import CompanyKey, CompanyKeyGrant
from safe.apps.org.models import UserTeam

from . import services
from .filters import EventFilterSet, PersonFilterSet
from .models import Event, Person
from .serializers import (
    EventDetailSerializer,
    EventSerializer,
    EventWriteSerializer,
    PersonSerializer,
    PersonWriteSerializer,
    UnlockSerializer,
)

EVENT_SELECT = (
    "season",
    "team",
    "ski_area",
    "zone",
    "slope",
    "difficulty",
    "location_type",
    "cause",
    "weather",
    "snow_condition",
    "wind",
    "visibility",
    "created_by",
)
PERSON_SELECT = (
    "gender",
    "equipment",
    "equipment_owner",
    "insurance",
    "accommodation",
    "destination",
    "diagnosis",
    "gravest_injury",
    "injury_place",
    "responsibility",
    "role",
    "equipment_condition",
    "rescue_refusal",
    "event",
    "event__season",
    "event__team",
    "event__zone",
    "event__slope",
)
PERSON_PREFETCH = (
    "evacuation_means__mean",
    "secondary_diagnoses__diagnosis",
    "injuries__body_part",
    "person_protections__protection",
    "person_conditions__condition",
    "person_first_aid__first_aid",
)


def user_team_ids(user) -> list:  # noqa: ANN001
    return list(UserTeam.objects.filter(user=user).values_list("team_id", flat=True))


def scope_events(qs: QuerySet, user) -> QuerySet:  # noqa: ANN001
    perms = effective_permissions(user)
    if "events.view_own_teams_only" in perms:
        qs = qs.filter(team_id__in=user_team_ids(user))
    return qs


def assert_can_edit(event: Event, user) -> None:  # noqa: ANN001
    perms = effective_permissions(user)
    if "events.edit_any_team" in perms:
        return
    if event.team_id not in user_team_ids(user):
        raise PermissionDenied(["events.edit_any_team"])


class EventViewSet(viewsets.ModelViewSet):
    permission_classes = [HasPermission]
    permission_map = {
        "list": ("events.view",),
        "retrieve": ("events.view",),
        "create": ("events.create",),
        "update": ("events.edit",),
        "partial_update": ("events.edit",),
        "destroy": ("events.delete",),
        "lock": ("events.edit",),
        "unlock": ("events.unlock",),
        "persons": ("events.view", "persons.view"),
        "add_person": ("events.view", "persons.edit"),
    }
    filterset_class = EventFilterSet
    ordering_fields = [
        "dateandtime",
        "created_at",
        "updated_at",
        "team__name",
        "zone__name",
        "slope__name",
        "fully_valid",
        "locked_at",
    ]
    ordering = ["-dateandtime"]

    def get_queryset(self) -> QuerySet:
        qs = (
            Event.objects.filter(deleted_at__isnull=True)
            .select_related(*EVENT_SELECT)
            .annotate(persons_count=Count("persons", filter=Q(persons__deleted_at__isnull=True)))
        )
        return scope_events(qs, self.request.user)

    def get_serializer_class(self):  # noqa: ANN201
        if self.action in ("create", "update", "partial_update"):
            return EventWriteSerializer
        if self.action == "list":
            return EventSerializer
        return EventDetailSerializer

    def _detail(self, event: Event, status_code: int = 200) -> Response:
        event = self.get_queryset().get(pk=event.pk)
        return Response(
            EventDetailSerializer(event, context=self.get_serializer_context()).data, status=status_code
        )

    @extend_schema(
        request=EventWriteSerializer, responses={201: EventDetailSerializer, 200: EventDetailSerializer}
    )
    def create(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        client_uuid = request.data.get("client_uuid") if isinstance(request.data, dict) else None
        if client_uuid:
            existing = Event.objects.filter(client_uuid=client_uuid, deleted_at__isnull=True).first()
            if existing is not None:
                return self._detail(existing, 200)  # idempotenza mobile
        serializer = EventWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        team = serializer.validated_data["team"]
        if "events.edit_any_team" not in effective_permissions(request.user) and team.id not in user_team_ids(
            request.user
        ):
            raise PermissionDenied(["events.edit_any_team"])
        event = serializer.save()
        services.compute_event_validity(event)
        audit.record("event.create", "event", object_id=event.id, event_id=event.id, request=request)
        return self._detail(event, 201)

    def update(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        event = self.get_object()
        services.ensure_unlocked(event)
        assert_can_edit(event, request.user)
        serializer = EventWriteSerializer(
            event,
            data=request.data,
            partial=kwargs.get("partial", False),
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        services.compute_event_validity(event)
        audit.record(
            "event.update",
            "event",
            object_id=event.id,
            event_id=event.id,
            request=request,
            changed_fields=sorted(serializer.validated_data.keys()),
        )
        return self._detail(event)

    def destroy(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        event = self.get_object()
        services.ensure_unlocked(event)
        assert_can_edit(event, request.user)
        services.soft_delete(event, request.user, request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=EventDetailSerializer)
    @action(detail=True, methods=["post"])
    def lock(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        event = self.get_object()
        assert_can_edit(event, request.user)
        services.lock_event(event, request.user, request)
        return self._detail(event)

    @extend_schema(request=UnlockSerializer, responses=EventDetailSerializer)
    @action(detail=True, methods=["post"])
    def unlock(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        event = self.get_object()
        ser = UnlockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.unlock_event(event, request.user, ser.validated_data["reason"], request)
        return self._detail(event)

    @extend_schema(responses=PersonSerializer(many=True))
    @action(detail=True, methods=["get"])
    def persons(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        event = self.get_object()
        persons = (
            Person.objects.filter(event=event, deleted_at__isnull=True)
            .select_related(*PERSON_SELECT)
            .prefetch_related(*PERSON_PREFETCH)
        )
        return Response(PersonSerializer(persons, many=True).data)

    @extend_schema(request=PersonWriteSerializer, responses={201: PersonSerializer})
    @persons.mapping.post
    def add_person(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        event = self.get_object()
        services.ensure_unlocked(event)
        assert_can_edit(event, request.user)
        client_uuid = request.data.get("client_uuid") if isinstance(request.data, dict) else None
        if client_uuid:
            existing = Person.objects.filter(client_uuid=client_uuid, deleted_at__isnull=True).first()
            if existing is not None:
                return Response(PersonSerializer(self._person(existing.pk)).data, status=200)
        ser = PersonWriteSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        person = ser.save(event=event)
        services.compute_event_validity(event)
        audit.record(
            "person.create",
            "person",
            object_id=person.id,
            event_id=event.id,
            request=request,
            changed_fields=sorted(ser.validated_data.keys()),
        )
        return Response(PersonSerializer(self._person(person.pk)).data, status=201)

    @staticmethod
    def _person(pk) -> Person:  # noqa: ANN001
        return Person.objects.select_related(*PERSON_SELECT).prefetch_related(*PERSON_PREFETCH).get(pk=pk)


class PersonViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [HasPermission]
    permission_map = {
        "list": ("persons.view",),
        "retrieve": ("persons.view",),
        "update": ("persons.edit",),
        "partial_update": ("persons.edit",),
        "destroy": ("persons.edit",),
        "identity": ("persons.reveal_identity",),
        "anonymize": ("company.retention",),
    }
    filterset_class = PersonFilterSet
    ordering_fields = ["event__dateandtime", "age", "sequence", "created_at", "updated_at", "valid"]
    ordering = ["-event__dateandtime", "sequence"]
    serializer_class = PersonSerializer

    def get_queryset(self) -> QuerySet:
        qs = (
            Person.objects.filter(deleted_at__isnull=True, event__deleted_at__isnull=True)
            .select_related(*PERSON_SELECT)
            .prefetch_related(*PERSON_PREFETCH)
        )
        if "events.view_own_teams_only" in effective_permissions(self.request.user):
            qs = qs.filter(event__team_id__in=user_team_ids(self.request.user))
        return qs

    def update(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        person = self.get_object()
        services.ensure_unlocked(person.event)
        assert_can_edit(person.event, request.user)
        ser = PersonWriteSerializer(
            person,
            data=request.data,
            partial=kwargs.get("partial", False),
            context=self.get_serializer_context(),
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        services.compute_event_validity(person.event)
        audit.record(
            "person.update",
            "person",
            object_id=person.id,
            event_id=person.event_id,
            request=request,
            changed_fields=sorted(ser.validated_data.keys()),
        )
        return Response(PersonSerializer(EventViewSet._person(person.pk)).data)

    def destroy(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        person = self.get_object()
        services.ensure_unlocked(person.event)
        assert_can_edit(person.event, request.user)
        services.soft_delete(person, request.user, request)
        services.compute_event_validity(person.event)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_throttles(self):  # noqa: ANN201
        if getattr(self, "action", None) == "identity":
            self.throttle_scope = "identity"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def anonymize(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        """Anonimizzazione anticipata su richiesta dell'interessato (docs/07-dpia §3)."""
        from . import retention

        person = get_object_or_404(self.get_queryset(), pk=pk)
        if person.anonymized_at is None:
            retention.anonymize(
                person, request=request, reason=str(cast(dict, request.data).get("reason", "request"))[:120]
            )
        return Response(PersonSerializer(self.get_queryset().get(pk=person.pk)).data)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"])
    def identity(self, request: Request, pk=None) -> Response:  # noqa: ANN001
        """Ciphertext + chiave avvolta + grant dell'utente. Il server non decifra mai. Sempre in audit."""
        person = get_object_or_404(self.get_queryset(), pk=pk)
        if person.pii_ciphertext is None or person.anonymized_at is not None:
            return Response(
                {"code": "not_found", "detail": "Nessun dato identificativo disponibile."}, status=404
            )
        key = CompanyKey.objects.filter(status=CompanyKey.Status.ACTIVE).first()
        grant = (
            CompanyKeyGrant.objects.filter(
                user=request.user, company_key=key, revoked_at__isnull=True
            ).first()
            if key
            else None
        )
        audit.record(
            "person.identity_read",
            "person",
            object_id=person.id,
            event_id=person.event_id,
            request=request,
            metadata={"granted": grant is not None},
        )
        if grant is None:
            raise ConflictError(
                {"detail": "Non disponi della chiave di decifratura.", "code": "no_key_grant"}
            )
        return Response(
            {
                "person_id": str(person.id),
                "algorithm": "xchacha20poly1305-x25519sealedbox-v1",
                "ciphertext": base64.b64encode(bytes(person.pii_ciphertext)).decode(),
                "key_wrapped": base64.b64encode(bytes(person.pii_key_wrapped)).decode(),
                "key_version": person.pii_key_version,
                "fields": person.pii_fields,
                "grant": {
                    "company_key_id": str(grant.company_key_id),
                    "wrapped_private_key": base64.b64encode(bytes(grant.wrapped_private_key)).decode(),
                },
            }
        )
