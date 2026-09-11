from __future__ import annotations

from typing import cast

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authz.drf import HasPermission
from safe.apps.jobs import runner
from safe.apps.jobs.models import AsyncJob, ExportRun
from safe.apps.jobs.views import JobSerializer
from safe.apps.org.models import AppUser
from safe.apps.territory.models import IstatAdminUnit, SkiArea

from . import regional

FILTER_KEYS = (
    "team",
    "season",
    "date_from",
    "date_to",
    "ski_area",
    "zone",
    "valid_only",
    "gender",
    "country_code",
    "diagnosis",
    "equipment",
    "evacuation_mean",
    "age_min",
    "age_max",
    "slope",
    "cause",
    "locked",
    "search",
)


class AreaSerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=["region", "province", "municipality"])
    code = serializers.CharField(max_length=12)


class RegionalRequestSerializer(serializers.Serializer):
    template = serializers.ChoiceField(choices=[regional.TEMPLATE], default=regional.TEMPLATE)
    season = serializers.RegexField(r"^\d{4}/\d{4}$")
    administrative_area = AreaSerializer(required=False, allow_null=True)
    team = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)
    format = serializers.ChoiceField(choices=["xlsx", "xls"], default="xlsx")
    merge_duplicates = serializers.BooleanField(default=True)
    exclude_in_buildings = serializers.BooleanField(default=True)


class DatasetRequestSerializer(serializers.Serializer):
    dataset = serializers.ChoiceField(choices=["events", "persons"])
    format = serializers.ChoiceField(choices=["csv", "xlsx"], default="xlsx")
    filters = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
    lang = serializers.ChoiceField(choices=["it", "en", "de"], required=False)


def _area(data: dict) -> IstatAdminUnit | None:
    a = data.get("administrative_area")
    if not a:
        return None
    unit = IstatAdminUnit.objects.filter(level=a["level"], code=a["code"]).order_by("-edition_year").first()
    if unit is None:
        raise serializers.ValidationError(
            {"administrative_area": ["Area amministrativa non trovata (confini ISTAT non caricati?)."]}
        )
    return unit


class RegionalPreviewView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("exports.regional",)

    @extend_schema(tags=["exports"], request=RegionalRequestSerializer, responses={200: {"type": "object"}})
    def post(self, request: Request) -> Response:
        ser = RegionalRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        sel = regional.select(
            request.user,
            d["season"],
            _area(d),
            [str(t) for t in d.get("team") or []] or None,
            exclude_buildings=d["exclude_in_buildings"],
            merge_duplicates=d["merge_duplicates"],
        )
        return Response(regional.preview(sel))


class RegionalExportView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("exports.regional",)

    @extend_schema(tags=["exports"], request=RegionalRequestSerializer, responses={202: JobSerializer})
    def post(self, request: Request) -> Response:
        ser = RegionalRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        _area(d)
        user = cast(AppUser, request.user)
        params = {**d, "team": [str(t) for t in d.get("team") or []] or None}
        job = runner.enqueue(
            company_id=user.company_id,
            user=user,
            kind=AsyncJob.Kind.EXPORT_REGIONAL,
            params=params,
        )
        audit.record(
            "export.regional",
            "job",
            object_id=job.id,
            request=request,
            metadata={"season": d["season"], "area": d.get("administrative_area")},
        )
        return Response(JobSerializer(job).data, status=202)


class DatasetExportView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("exports.dataset",)

    @extend_schema(tags=["exports"], request=DatasetRequestSerializer, responses={202: JobSerializer})
    def post(self, request: Request) -> Response:
        ser = DatasetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        filters = {
            k: v for k, v in (d.get("filters") or {}).items() if k in FILTER_KEYS and v not in (None, "", [])
        }
        user = cast(AppUser, request.user)
        params = {
            "dataset": d["dataset"],
            "format": d["format"],
            "filters": filters,
            "lang": d.get("lang") or getattr(request.user, "locale", "it"),
        }
        job = runner.enqueue(
            company_id=user.company_id,
            user=user,
            kind=AsyncJob.Kind.EXPORT_DATASET,
            params=params,
        )
        audit.record("export.dataset", "job", object_id=job.id, request=request, metadata=params)
        return Response(JobSerializer(job).data, status=202)


class ExportListView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("exports.dataset",)

    @extend_schema(tags=["exports"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        jobs = AsyncJob.objects.filter(
            kind__in=[AsyncJob.Kind.EXPORT_DATASET, AsyncJob.Kind.EXPORT_REGIONAL]
        )[:100]
        runs = {r.job_id: r for r in ExportRun.objects.filter(job__in=[j.id for j in jobs])}
        out = []
        for j in jobs:
            data = JobSerializer(j).data
            r = runs.get(j.id)
            data["export"] = (
                {
                    "template": r.template_code,
                    "format": r.format,
                    "filters": r.filters,
                    "row_count": r.row_count,
                    "administrative_area_code": r.administrative_area_code,
                }
                if r
                else None
            )
            data["requested_by"] = j.requested_by.email if j.requested_by else None
            out.append(data)
        return Response({"count": len(out), "next": None, "previous": None, "results": out})


class AdministrativeAreasView(APIView):
    """Aree ISTAT disponibili: quelle che intersecano i comprensori della società (altrimenti tutte)."""

    permission_classes = [HasPermission]
    required_permissions = ("exports.regional",)

    @extend_schema(tags=["exports"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        if not IstatAdminUnit.objects.exists():
            return Response({"loaded": False, "areas": []})
        boundaries = [a.boundary for a in SkiArea.objects.filter(boundary__isnull=False)]
        qs = IstatAdminUnit.objects.filter(level__in=["region", "province"]).order_by("level", "name")
        if boundaries:
            # con i confini dei comprensori: regioni, province e anche i comuni intersecati
            from django.db.models import Q

            q = Q()
            for b in boundaries:
                q |= Q(geom__intersects=b)
            qs = IstatAdminUnit.objects.filter(q).order_by("level", "name")
        return Response(
            {
                "loaded": True,
                "areas": [
                    {"level": u.level, "code": u.code, "name": u.name, "edition_year": u.edition_year}
                    for u in qs
                ],
            }
        )
