"""Personalizzazione dei vocabolari (`lookups.manage`): valori di società e disattivazione dei globali."""

from __future__ import annotations

import re
from typing import Any, cast

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.core.exceptions import BusinessError
from safe.apps.org.models import AppUser
from safe.apps.tenancy.context import get_current_company_id

from .models import DIMENSIONS, CompanyLookupDisabled, LookupValue


def invalidate_cache() -> None:
    company_id = get_current_company_id()
    cache.delete(f"lookups:{company_id}:all")
    for d in DIMENSIONS:
        cache.delete(f"lookups:{company_id}:{d}")


def item(v: LookupValue, disabled_ids: set) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "dimension": v.dimension,
        "code": v.code,
        "labels": v.labels,
        "sort_order": v.sort_order,
        "is_custom": v.company_id is not None,
        "is_active": v.is_active,
        "disabled_for_company": v.id in disabled_ids,
        "parent": v.parent.code if v.parent else None,
        "color": v.color or None,
        "mapping": v.mapping,
    }


class LabelsSerializer(serializers.Serializer):
    it = serializers.CharField(max_length=120)
    en = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    de = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class LookupWriteSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60, required=False)
    labels = LabelsSerializer(required=False)
    sort_order = serializers.IntegerField(min_value=0, max_value=32767, required=False)
    color = serializers.RegexField(r"^#[0-9a-fA-F]{6}$", required=False, allow_blank=True, allow_null=True)
    mapping = serializers.DictField(required=False)
    is_active = serializers.BooleanField(required=False)

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["parent"] = serializers.CharField(required=False, allow_null=True)  # nome riservato in Field
        return fields

    def validate_code(self, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", value):
            raise serializers.ValidationError("Solo minuscole, cifre e underscore.")
        return value


class LookupAdminListView(APIView):
    """Tutti i valori della dimensione (anche inattivi/disattivati) per la pagina di gestione."""

    permission_classes = [HasPermission]
    permission_map = {"get": ("lookups.manage",), "post": ("lookups.manage",)}

    def _check(self, dimension: str) -> None:
        if dimension not in DIMENSIONS:
            raise serializers.ValidationError({"dimension": [f"Dimensione '{dimension}' sconosciuta."]})

    @extend_schema(tags=["lookups"], responses={200: {"type": "array"}})
    def get(self, request: Request, dimension: str) -> Response:
        self._check(dimension)
        disabled = set(
            CompanyLookupDisabled.objects.filter(lookup_value__dimension=dimension).values_list(
                "lookup_value_id", flat=True
            )
        )
        values = (
            LookupValue.objects.filter(dimension=dimension)
            .select_related("parent")
            .order_by("sort_order", "code")
        )
        return Response([item(v, disabled) for v in values])

    @extend_schema(tags=["lookups"], request=LookupWriteSerializer, responses={201: {"type": "object"}})
    def post(self, request: Request, dimension: str) -> Response:
        self._check(dimension)
        ser = LookupWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "code" not in d or "labels" not in d:
            raise serializers.ValidationError({"code": ["Obbligatorio."], "labels": ["Obbligatorio."]})
        if LookupValue.objects.filter(dimension=dimension, code=d["code"]).exists():
            return Response(
                {"code": "code_in_use", "detail": "Codice già presente nella dimensione."}, status=409
            )
        parent = None
        if d.get("parent"):
            parent = get_object_or_404(LookupValue.objects.filter(dimension=dimension), code=d["parent"])
        labels = d["labels"]
        v = LookupValue.objects.create(
            company_id=cast(AppUser, request.user).company_id,
            dimension=dimension,
            code=d["code"],
            label_it=labels["it"],
            label_en=labels.get("en") or labels["it"],
            label_de=labels.get("de") or labels["it"],
            sort_order=d.get("sort_order", 100),
            parent=parent,
            color=d.get("color") or "",
            mapping=d.get("mapping", {}),
        )
        invalidate_cache()
        return Response(item(v, set()), status=status.HTTP_201_CREATED)


class LookupAdminDetailView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("lookups.manage",)

    @extend_schema(tags=["lookups"], request=LookupWriteSerializer, responses={200: {"type": "object"}})
    def patch(self, request: Request, dimension: str, pk: str) -> Response:
        v = get_object_or_404(LookupValue.objects.filter(dimension=dimension).select_related("parent"), pk=pk)
        ser = LookupWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        company_id = cast(AppUser, request.user).company_id
        if v.company_id is None:
            # valore globale: la società può solo disattivarlo/riattivarlo per sé o aggiungere mapping
            allowed = {"is_active", "mapping"}
            if set(d) - allowed:
                raise BusinessError(
                    "global_value", "I valori standard si possono solo disattivare per la società."
                )
            if "is_active" in d:
                if d["is_active"]:
                    CompanyLookupDisabled.objects.filter(company_id=company_id, lookup_value=v).delete()
                else:
                    CompanyLookupDisabled.objects.get_or_create(company_id=company_id, lookup_value=v)
            if "mapping" in d:
                v.mapping = {**v.mapping, **d["mapping"]}
                v.save(update_fields=["mapping"])
        else:
            if "labels" in d:
                v.label_it = d["labels"]["it"]
                v.label_en = d["labels"].get("en") or v.label_it
                v.label_de = d["labels"].get("de") or v.label_it
            for f in ("sort_order", "is_active"):
                if f in d:
                    setattr(v, f, d[f])
            if "color" in d:
                v.color = d["color"] or ""
            if "mapping" in d:
                v.mapping = d["mapping"]
            if "parent" in d:
                v.parent = (
                    get_object_or_404(LookupValue.objects.filter(dimension=dimension), code=d["parent"])
                    if d["parent"]
                    else None
                )
            v.save()
        invalidate_cache()
        disabled = set(
            CompanyLookupDisabled.objects.filter(lookup_value=v).values_list("lookup_value_id", flat=True)
        )
        return Response(item(v, disabled))
