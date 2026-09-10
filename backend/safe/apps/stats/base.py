"""Base delle rotte statistiche: filtri globali uniformi, scoping per squadra, lingua, cache per tenant.

Cache: chiave = (società, rotta, filtri normalizzati, squadre visibili, lingua, data_version).
`company.data_version` cambia a ogni scrittura su eventi/persone (signal): invalidazione implicita.
"""

from __future__ import annotations

import hashlib
import json
import zoneinfo
from typing import Any

from django.core.cache import cache
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.core.filters import GlobalFilterSet
from safe.apps.rescue.models import Event, Person
from safe.apps.rescue.views import scope_events
from safe.apps.tenancy.models import Company

from .chart import AGE_CLUSTERS

CACHE_SECONDS = 600
FILTER_PARAMS = [
    OpenApiParameter("team", str, many=True, required=False),
    OpenApiParameter("season", str, required=False),
    OpenApiParameter("date_from", str, required=False),
    OpenApiParameter("date_to", str, required=False),
    OpenApiParameter("ski_area", str, required=False),
    OpenApiParameter("zone", str, required=False),
    OpenApiParameter("valid_only", bool, required=False),
    OpenApiParameter("lang", str, required=False, description="it | en | de (default: lingua utente)"),
]


def stats_schema(summary: str, extra: list[OpenApiParameter] | None = None):  # noqa: ANN201
    return extend_schema(
        tags=["stats"],
        summary=summary,
        parameters=FILTER_PARAMS + (extra or []),
        responses={200: {"type": "object"}},
    )


class StatsView(APIView):
    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ("stats.view",)
    cache_seconds = CACHE_SECONDS

    # --- contesto -------------------------------------------------------------
    @property
    def company(self) -> Company:
        return self.request.user.company  # type: ignore[union-attr]

    @property
    def tz(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.company.timezone)

    @property
    def lang(self) -> str:
        lang = self.request.query_params.get("lang") or getattr(self.request.user, "locale", "it")
        return lang if lang in ("it", "en", "de") else "it"

    @property
    def age_cluster(self) -> str:
        cluster = self.request.query_params.get("age_cluster", "standard")
        return cluster if cluster in AGE_CLUSTERS else "standard"

    def events(self, *, apply_season: bool = True) -> QuerySet:
        """Eventi visibili, filtrati con i filtri globali (opzionalmente senza stagione)."""
        qs = scope_events(Event.objects.filter(deleted_at__isnull=True), self.request.user)
        params = self.request.query_params.copy()
        if not apply_season:
            params.pop("season", None)
        return GlobalFilterSet(params, queryset=qs).qs

    def persons(self, events: QuerySet | None = None) -> QuerySet:
        events = self.events() if events is None else events
        return Person.objects.filter(deleted_at__isnull=True, event__in=events.values("id"))

    # --- cache ----------------------------------------------------------------
    def cache_key(self) -> str:
        from safe.apps.rescue.views import user_team_ids

        raw = {
            "path": self.request.path,
            "q": sorted((k, sorted(self.request.query_params.getlist(k))) for k in self.request.query_params),
            "teams": sorted(str(t) for t in user_team_ids(self.request.user)),
            "lang": self.lang,
            "v": Company.objects.filter(id=self.company.id).values_list("data_version", flat=True).first(),
        }
        digest = hashlib.sha256(json.dumps(raw, default=str).encode()).hexdigest()[:32]
        return f"stats:{self.company.id}:{digest}"

    def get(self, request: Request) -> Response:
        key = self.cache_key()
        payload = cache.get(key)
        cached = payload is not None
        if not cached:
            payload = self.compute()
            cache.set(key, payload, self.cache_seconds)
        if isinstance(payload, dict) and "meta" in payload:
            payload["meta"]["cached"] = cached
        return Response(payload)

    def compute(self) -> Any:  # pragma: no cover - astratto
        raise NotImplementedError
