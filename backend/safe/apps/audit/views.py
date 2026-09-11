"""Consultazione dell'audit log (`audit.view`): filtri per azione, utente, oggetto, periodo; export CSV.
Per costruzione il log non contiene dati personali (solo id, nomi di campo, metadati tecnici)."""

from __future__ import annotations

import csv
import io

from django.db.models import QuerySet
from django.http import HttpResponse
from django_filters import rest_framework as df
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.org.models import AppUser

from . import service as audit
from .models import AuditLog

EXPORT_LIMIT = 50_000


class AuditFilter(df.FilterSet):
    action = df.CharFilter(field_name="action", lookup_expr="istartswith")
    actor = df.UUIDFilter(field_name="actor_user_id")
    object_type = df.CharFilter(field_name="object_type")
    object_id = df.UUIDFilter(field_name="object_id")
    event = df.UUIDFilter(field_name="event_id")
    date_from = df.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = df.DateFilter(field_name="created_at", lookup_expr="date__lte")


class AuditSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "created_at",
            "actor_user_id",
            "actor",
            "actor_device_id",
            "action",
            "object_type",
            "object_id",
            "event_id",
            "changed_fields",
            "metadata",
            "ip",
            "user_agent",
        ]

    def get_actor(self, row: AuditLog) -> str | None:
        return self.context.get("actors", {}).get(row.actor_user_id)


def actors_map(rows: list[AuditLog]) -> dict:
    ids = {r.actor_user_id for r in rows if r.actor_user_id}
    return {u.id: u.email for u in AppUser.objects.filter(id__in=ids)} if ids else {}


class AuditListView(ListAPIView):
    permission_classes = [HasPermission]
    required_permissions = ("audit.view",)
    serializer_class = AuditSerializer
    filterset_class = AuditFilter
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet:
        return AuditLog.objects.all().order_by("-created_at", "-id")

    def list(self, request: Request, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        rows = list(page) if page is not None else list(qs[:200])
        ser = self.get_serializer(
            rows, many=True, context={**self.get_serializer_context(), "actors": actors_map(rows)}
        )
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)


class AuditActionsView(APIView):
    """Elenco delle azioni presenti (per il filtro della pagina)."""

    permission_classes = [HasPermission]
    required_permissions = ("audit.view",)

    @extend_schema(tags=["audit"], responses={200: {"type": "array"}})
    def get(self, request: Request) -> Response:
        return Response(sorted(AuditLog.objects.values_list("action", flat=True).distinct()))


class AuditExportView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("audit.view",)

    @extend_schema(tags=["audit"], responses={200: {"type": "string"}})
    def get(self, request: Request) -> HttpResponse:
        qs = AuditFilter(request.query_params, queryset=AuditLog.objects.all()).qs.order_by("-created_at")[
            :EXPORT_LIMIT
        ]
        rows = list(qs)
        actors = actors_map(rows)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(
            [
                "created_at",
                "actor",
                "action",
                "object_type",
                "object_id",
                "event_id",
                "changed_fields",
                "metadata",
                "ip",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.created_at.isoformat(),
                    actors.get(r.actor_user_id, ""),
                    r.action,
                    r.object_type,
                    r.object_id or "",
                    r.event_id or "",
                    ",".join(r.changed_fields),
                    str(r.metadata),
                    r.ip or "",
                ]
            )
        audit.record("audit.export", "audit_log", request=request, metadata={"rows": len(rows)})
        resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
        return resp
