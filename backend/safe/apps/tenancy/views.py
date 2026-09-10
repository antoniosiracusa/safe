"""Società corrente: lettura per tutti gli utenti, modifica con `company.settings`."""

from __future__ import annotations

import zoneinfo
from typing import Any, cast

from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authz.drf import HasPermission
from safe.apps.org.models import AppUser

from .models import Company

EVENT_FIELDS = (
    "dateandtime",
    "team",
    "ski_area",
    "zone",
    "slope",
    "location",
    "location_type",
    "cause",
    "geometry",
    "weather",
    "snow_condition",
    "difficulty",
)
PERSON_FIELDS = (
    "age",
    "gender",
    "country_code",
    "diagnosis",
    "injury_place",
    "equipment",
    "helmet",
    "evacuation_means",
    "destination",
)
DUP_FIELDS = ("date", "slope", "zone", "gender", "age_class_a01", "equipment")


def company_payload(c: Company) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "slug": c.slug,
        "tenant_type": c.tenant_type,
        "timezone": c.timezone,
        "default_locale": c.default_locale,
        "retention_identity_years": c.retention_identity_years,
        "retention_audit_years": c.retention_audit_years,
        "settings": {
            "auto_lock_hours": c.auto_lock_hours,
            "devices_need_authorization": c.devices_need_authorization,
            "validity_rules": c.validity_rules,
            "duplicate_rule": c.duplicate_rule,
            "export_templates": c.settings.get("export_templates", {}),
        },
        "created_at": c.created_at,
    }


class ValidityRulesSerializer(serializers.Serializer):
    event_required = serializers.ListField(
        child=serializers.ChoiceField(choices=EVENT_FIELDS), required=False
    )
    person_required = serializers.ListField(
        child=serializers.ChoiceField(choices=PERSON_FIELDS), required=False
    )


class DuplicateRuleSerializer(serializers.Serializer):
    minutes = serializers.IntegerField(min_value=1, max_value=1440, required=False)

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["fields"] = serializers.ListField(
            child=serializers.ChoiceField(choices=DUP_FIELDS), required=False
        )  # nome riservato in Serializer
        return fields


class SettingsSerializer(serializers.Serializer):
    auto_lock_hours = serializers.IntegerField(min_value=0, max_value=720, required=False)
    devices_need_authorization = serializers.BooleanField(required=False)
    validity_rules = ValidityRulesSerializer(required=False)
    duplicate_rule = DuplicateRuleSerializer(required=False)
    export_templates = serializers.DictField(required=False)


class CompanyPatchSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    default_locale = serializers.ChoiceField(choices=["it", "en", "de"], required=False)
    settings = SettingsSerializer(required=False)

    def validate_timezone(self, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("Fuso orario sconosciuto.") from exc
        return value


class CompanyView(APIView):
    permission_classes = [HasPermission]
    permission_map = {"get": (), "patch": ("company.settings",)}

    @extend_schema(tags=["company"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        return Response(company_payload(cast(AppUser, request.user).company))

    @extend_schema(tags=["company"], request=CompanyPatchSerializer, responses={200: {"type": "object"}})
    def patch(self, request: Request) -> Response:
        company = cast(AppUser, request.user).company
        ser = CompanyPatchSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        changed: list[str] = []
        for f in ("name", "timezone", "default_locale"):
            if f in d and getattr(company, f) != d[f]:
                setattr(company, f, d[f])
                changed.append(f)
        if "settings" in d:
            new = dict(company.settings)
            for k, v in d["settings"].items():
                if isinstance(v, dict) and isinstance(new.get(k), dict):
                    new[k] = {**new[k], **v}
                else:
                    new[k] = v
            company.settings = new
            changed.append("settings")
        if changed:
            company.save(update_fields=[*changed, "updated_at"])
            if "settings" in changed and "validity_rules" in d["settings"]:
                # le regole di validità cambiano gli aggregati "solo validi": invalida la cache statistiche
                Company.objects.filter(pk=company.pk).update(data_version=F("data_version") + 1)
                from safe.apps.rescue.tasks import recompute_validity

                recompute_validity.delay(str(company.pk))
            audit.record(
                "company.settings", "company", object_id=company.id, request=request, changed_fields=changed
            )
        company.refresh_from_db()
        return Response(company_payload(company))
