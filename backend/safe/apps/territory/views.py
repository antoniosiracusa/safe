"""Lettura del territorio (comprensori, zone, piste). La gestione (CRUD) arriva in M6."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters import rest_framework as df
from rest_framework import mixins, serializers, viewsets

from safe.apps.authz.drf import HasPermission

from .models import SkiArea, Slope, Zone


class SkiAreaSerializer(serializers.ModelSerializer):
    has_boundary = serializers.SerializerMethodField()

    class Meta:
        model = SkiArea
        fields = ["id", "name", "regional_code", "has_boundary", "is_active"]

    def get_has_boundary(self, obj: SkiArea) -> bool:
        return obj.boundary is not None


class ZoneSerializer(serializers.ModelSerializer):
    ski_area = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = ["id", "name", "ski_area", "is_active"]

    def get_ski_area(self, obj: Zone) -> dict:
        return {"id": str(obj.ski_area_id), "name": obj.ski_area.name}


class SlopeSerializer(serializers.ModelSerializer):
    zone = serializers.SerializerMethodField()
    difficulty = serializers.SerializerMethodField()
    has_geometry = serializers.SerializerMethodField()

    class Meta:
        model = Slope
        fields = ["id", "name", "regional_code", "difficulty", "zone", "has_geometry", "is_active"]

    def get_zone(self, obj: Slope) -> dict:
        return {"id": str(obj.zone_id), "name": obj.zone.name, "ski_area": str(obj.zone.ski_area_id)}

    def get_difficulty(self, obj: Slope) -> str | None:
        return obj.difficulty.code if obj.difficulty else None

    def get_has_geometry(self, obj: Slope) -> bool:
        return obj.geom is not None


class ReadOnlyTenantViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [HasPermission]
    required_permissions = ("territory.view",)
    pagination_class = None  # anagrafiche piccole: liste complete per i form


class SkiAreaViewSet(ReadOnlyTenantViewSet):
    serializer_class = SkiAreaSerializer

    def get_queryset(self) -> QuerySet:
        return SkiArea.objects.filter(is_active=True).order_by("name")


class ZoneFilter(df.FilterSet):
    ski_area = df.UUIDFilter(field_name="ski_area_id")


class ZoneViewSet(ReadOnlyTenantViewSet):
    serializer_class = ZoneSerializer
    filterset_class = ZoneFilter

    def get_queryset(self) -> QuerySet:
        return Zone.objects.filter(is_active=True).select_related("ski_area").order_by("name")


class SlopeFilter(df.FilterSet):
    zone = df.UUIDFilter(field_name="zone_id")
    ski_area = df.UUIDFilter(field_name="zone__ski_area_id")
    search = df.CharFilter(field_name="name", lookup_expr="icontains")


class SlopeViewSet(ReadOnlyTenantViewSet):
    serializer_class = SlopeSerializer
    filterset_class = SlopeFilter

    def get_queryset(self) -> QuerySet:
        return Slope.objects.filter(is_active=True).select_related("zone", "difficulty").order_by("name")
