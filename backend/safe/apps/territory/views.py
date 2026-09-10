"""Territorio: lettura (`territory.view`) e gestione (`territory.manage`) di comprensori, zone, piste,
impianti.
Le geometrie si scambiano come GeoJSON (confine MultiPolygon/Polygon, piste MultiLineString/LineString)."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.gis.geos import GEOSGeometry, LineString, MultiLineString, MultiPolygon, Polygon
from django.db.models import Count, Q, QuerySet
from django_filters import rest_framework as df
from rest_framework import serializers, viewsets

from safe.apps.authz.drf import HasPermission
from safe.apps.lookups.fields import LookupCodeField

from .models import Lift, SkiArea, Slope, Zone


def parse_geometry(value: Any, kinds: tuple[type, ...], wrap: type | None) -> GEOSGeometry | None:
    if value in (None, "", {}):
        return None
    try:
        geom = GEOSGeometry(json.dumps(value) if isinstance(value, dict) else str(value), srid=4326)
    except Exception as exc:  # noqa: BLE001
        raise serializers.ValidationError("Geometria GeoJSON non valida.") from exc
    if wrap is not None and isinstance(geom, kinds[-1]) and not isinstance(geom, wrap):
        geom = wrap(geom)
    if not isinstance(geom, kinds[0]):
        raise serializers.ValidationError(f"Tipo di geometria non ammesso: {geom.geom_type}.")
    return geom


class TenantPK(serializers.PrimaryKeyRelatedField):
    """PrimaryKeyRelatedField il cui queryset è valutato nella richiesta (manager tenant)."""

    def __init__(self, model: Any, **kw: Any) -> None:
        self.model = model
        kw["queryset"] = model.objects.none()
        super().__init__(**kw)

    def get_queryset(self) -> QuerySet:
        return self.model.objects.all()


class GeometryField(serializers.Field):
    def __init__(self, kinds: tuple[type, ...], wrap: type | None, **kw: Any) -> None:
        kw.setdefault("required", False)
        kw.setdefault("allow_null", True)
        super().__init__(**kw)
        self.kinds = kinds
        self.wrap = wrap

    def to_representation(self, value: GEOSGeometry | None) -> dict | None:
        return json.loads(value.geojson) if value is not None else None

    def to_internal_value(self, data: Any) -> GEOSGeometry | None:
        return parse_geometry(data, self.kinds, self.wrap)


class SkiAreaSerializer(serializers.ModelSerializer):
    has_boundary = serializers.SerializerMethodField()
    boundary = GeometryField((MultiPolygon, Polygon), MultiPolygon, write_only=True)
    zones_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = SkiArea
        fields = ["id", "name", "regional_code", "has_boundary", "boundary", "zones_count", "is_active"]
        read_only_fields = ["id"]

    def get_has_boundary(self, obj: SkiArea) -> bool:
        return obj.boundary is not None


class ZoneSerializer(serializers.ModelSerializer):
    ski_area = serializers.SerializerMethodField()
    ski_area_id = TenantPK(SkiArea, source="ski_area", write_only=True)
    slopes_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Zone
        fields = ["id", "name", "ski_area", "ski_area_id", "slopes_count", "is_active"]
        read_only_fields = ["id"]

    def get_ski_area(self, obj: Zone) -> dict:
        return {"id": str(obj.ski_area_id), "name": obj.ski_area.name}


class SlopeSerializer(serializers.ModelSerializer):
    zone = serializers.SerializerMethodField()
    zone_id = TenantPK(Zone, source="zone", write_only=True)
    difficulty = LookupCodeField("slope_difficulty", required=False, allow_null=True)
    has_geometry = serializers.SerializerMethodField()
    geom = GeometryField((MultiLineString, LineString), MultiLineString, write_only=True)
    events_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Slope
        fields = [
            "id",
            "name",
            "regional_code",
            "difficulty",
            "zone",
            "zone_id",
            "has_geometry",
            "geom",
            "events_count",
            "is_active",
        ]
        read_only_fields = ["id"]

    def get_zone(self, obj: Slope) -> dict:
        return {"id": str(obj.zone_id), "name": obj.zone.name, "ski_area": str(obj.zone.ski_area_id)}

    def get_has_geometry(self, obj: Slope) -> bool:
        return obj.geom is not None


class LiftSerializer(serializers.ModelSerializer):
    ski_area = serializers.SerializerMethodField()
    ski_area_id = TenantPK(SkiArea, source="ski_area", write_only=True)
    has_geometry = serializers.SerializerMethodField()
    geom = GeometryField((LineString,), None, write_only=True)

    class Meta:
        model = Lift
        fields = ["id", "name", "lift_type", "ski_area", "ski_area_id", "has_geometry", "geom", "is_active"]
        read_only_fields = ["id"]

    def get_ski_area(self, obj: Lift) -> dict:
        return {"id": str(obj.ski_area_id), "name": obj.ski_area.name}

    def get_has_geometry(self, obj: Lift) -> bool:
        return obj.geom is not None


class TerritoryViewSet(viewsets.ModelViewSet):
    """Liste complete (anagrafiche piccole). `?include_inactive=true` per la gestione.
    DELETE = disattivazione (gli eventi restano collegati)."""

    permission_classes = [HasPermission]
    permission_map = {
        "list": ("territory.view",),
        "retrieve": ("territory.view",),
        "*": ("territory.manage",),
    }
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def base(self) -> QuerySet:  # valutato per richiesta: i manager tenant filtrano alla creazione
        raise NotImplementedError

    def get_queryset(self) -> QuerySet:
        qs = self.base()
        if self.request.query_params.get("include_inactive") not in ("true", "1"):
            qs = qs.filter(is_active=True)
        return qs.order_by("name")

    def perform_destroy(self, instance: Any) -> None:
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class SkiAreaViewSet(TerritoryViewSet):
    serializer_class = SkiAreaSerializer

    def base(self) -> QuerySet:
        return SkiArea.objects.annotate(zones_count=Count("zones", filter=Q(zones__is_active=True)))


class ZoneFilter(df.FilterSet):
    ski_area = df.UUIDFilter(field_name="ski_area_id")


class ZoneViewSet(TerritoryViewSet):
    serializer_class = ZoneSerializer
    filterset_class = ZoneFilter

    def base(self) -> QuerySet:
        return Zone.objects.select_related("ski_area").annotate(
            slopes_count=Count("slopes", filter=Q(slopes__is_active=True))
        )


class SlopeFilter(df.FilterSet):
    zone = df.UUIDFilter(field_name="zone_id")
    ski_area = df.UUIDFilter(field_name="zone__ski_area_id")
    search = df.CharFilter(field_name="name", lookup_expr="icontains")


class SlopeViewSet(TerritoryViewSet):
    serializer_class = SlopeSerializer
    filterset_class = SlopeFilter

    def base(self) -> QuerySet:
        return Slope.objects.select_related("zone", "difficulty").annotate(
            events_count=Count("events", filter=Q(events__deleted_at__isnull=True))
        )


class LiftFilter(df.FilterSet):
    ski_area = df.UUIDFilter(field_name="ski_area_id")


class LiftViewSet(TerritoryViewSet):
    serializer_class = LiftSerializer
    filterset_class = LiftFilter

    def base(self) -> QuerySet:
        return Lift.objects.select_related("ski_area")
