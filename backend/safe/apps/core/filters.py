"""Barra filtri globale: opzioni (squadre, stagioni, comprensori, zone) e FilterSet uniforme
usato da statistiche, dati, mappa ed export (docs/03-openapi.yaml, parametri StatsFilters)."""

from __future__ import annotations

import datetime as dt

from django.db.models import QuerySet
from django_filters import rest_framework as df
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.org.models import Team
from safe.apps.rescue.models import Season
from safe.apps.territory.models import SkiArea, Zone


class FilterOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["filters"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        today = dt.date.today()
        current = Season.code_for(today)
        seasons = [
            {
                "value": s.code,
                "label": s.code,
                "start_date": s.start_date.isoformat(),
                "end_date": s.end_date.isoformat(),
                "is_current": s.code == current,
            }
            for s in Season.objects.filter(start_date__lte=today).order_by("-start_date")
        ]
        return Response(
            {
                "teams": [{"value": str(t.id), "label": t.name} for t in Team.objects.filter(is_active=True)],
                "seasons": seasons,
                "ski_areas": [
                    {"value": str(a.id), "label": a.name} for a in SkiArea.objects.filter(is_active=True)
                ],
                "zones": [
                    {"value": str(z.id), "label": z.name, "ski_area": str(z.ski_area_id)}
                    for z in Zone.objects.filter(is_active=True).order_by("name")
                ],
            }
        )


class GlobalFilterSet(df.FilterSet):
    """Filtri uniformi su Event: team (multi), season | date_from/date_to, ski_area, zone, valid_only."""

    team = df.UUIDFilter(method="filter_team")
    season = df.CharFilter(field_name="season__code")
    date_from = df.DateFilter(field_name="dateandtime", lookup_expr="date__gte")
    date_to = df.DateFilter(field_name="dateandtime", lookup_expr="date__lte")
    ski_area = df.UUIDFilter(field_name="ski_area_id")
    zone = df.UUIDFilter(field_name="zone_id")
    valid_only = df.BooleanFilter(method="filter_valid_only")

    def filter_team(self, queryset: QuerySet, name: str, value: object) -> QuerySet:
        teams = self.data.getlist("team") if hasattr(self.data, "getlist") else [value]
        return queryset.filter(team_id__in=teams)

    def filter_valid_only(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        return queryset.filter(fully_valid=True) if value else queryset
