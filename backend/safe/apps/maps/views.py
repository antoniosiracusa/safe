"""Rotte cartografiche. Il GeoJSON degli eventi espone SOLO id e data/ora (mai dati personali).
Stili: Mapbox (configurati per ambiente); il token pubblico vive nella configurazione del client."""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.db.models import FloatField, Func, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.core.filters import GlobalFilterSet
from safe.apps.rescue.models import Event
from safe.apps.rescue.views import scope_events
from safe.apps.territory.models import Lift, SkiArea, Slope

from .base import FILTER_PARAMS


class GeoJSONResponse(Response):
    def __init__(self, features: list[dict[str, Any]], **kwargs: Any) -> None:
        kwargs.setdefault("content_type", "application/geo+json")
        super().__init__({"type": "FeatureCollection", "features": features}, **kwargs)


def _geom(obj: Any) -> dict[str, Any] | None:
    return json.loads(obj.geojson) if obj is not None else None


class MapBase(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("map.view",)


class EventsGeoJSONView(MapBase):
    @extend_schema(
        tags=["map"],
        summary="Eventi con geometria: solo id e data/ora",
        parameters=FILTER_PARAMS,
        responses={200: {"type": "object"}},
    )
    def get(self, request: Request) -> Response:
        qs: QuerySet = scope_events(
            Event.objects.filter(deleted_at__isnull=True, geom__isnull=False), request.user
        )
        qs = GlobalFilterSet(request.query_params, queryset=qs).qs
        features = [
            {
                "type": "Feature",
                "id": str(pk),
                "geometry": {"type": "Point", "coordinates": [x, y]},
                "properties": {"id": str(pk), "dateandtime": when.isoformat()},
            }
            for pk, x, y, when in qs.annotate(
                lon=Func("geom", function="ST_X", output_field=FloatField()),
                lat=Func("geom", function="ST_Y", output_field=FloatField()),
            )
            .values_list("id", "lon", "lat", "dateandtime")
            .iterator(chunk_size=5000)
        ]
        return GeoJSONResponse(features)


class SkiAreasGeoJSONView(MapBase):
    @extend_schema(tags=["map"], summary="Confini dei comprensori", responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        features = [
            {
                "type": "Feature",
                "id": str(a.id),
                "geometry": _geom(a.boundary),
                "properties": {"id": str(a.id), "name": a.name},
            }
            for a in SkiArea.objects.filter(is_active=True, boundary__isnull=False)
        ]
        return GeoJSONResponse(features)


class SlopesGeoJSONView(MapBase):
    @extend_schema(tags=["map"], summary="Piste (layer proprietario)", responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        features = [
            {
                "type": "Feature",
                "id": str(s.id),
                "geometry": _geom(s.geom),
                "properties": {
                    "id": str(s.id),
                    "name": s.name,
                    "regional_code": s.regional_code or None,
                    "difficulty": s.difficulty.code if s.difficulty else None,
                    "zone": s.zone.name,
                },
            }
            for s in Slope.objects.filter(is_active=True, geom__isnull=False).select_related(
                "difficulty", "zone"
            )
        ]
        return GeoJSONResponse(features)


class LiftsGeoJSONView(MapBase):
    @extend_schema(tags=["map"], summary="Impianti (layer proprietario)", responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        features = [
            {
                "type": "Feature",
                "id": str(lf.id),
                "geometry": _geom(lf.geom),
                "properties": {"id": str(lf.id), "name": lf.name, "lift_type": lf.lift_type or None},
            }
            for lf in Lift.objects.filter(is_active=True, geom__isnull=False)
        ]
        return GeoJSONResponse(features)


class StylesView(MapBase):
    @extend_schema(
        tags=["map"], summary="Stili disponibili (provider e URL)", responses={200: {"type": "object"}}
    )
    def get(self, request: Request) -> Response:
        cfg = settings.MAP_STYLES
        return Response(
            {
                "provider": "mapbox",
                "styles": [
                    {"code": code, "label_key": f"map.style.{code}", "url": url, "terrain": code == "winter"}
                    for code, url in cfg.items()
                ],
                "static_images": "mapbox",
            }
        )
