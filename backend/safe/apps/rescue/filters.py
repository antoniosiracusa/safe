from __future__ import annotations

from django.db.models import Q, QuerySet
from django_filters import rest_framework as df

from safe.apps.core.filters import GlobalFilterSet

from .models import Event, Person


class EventFilterSet(GlobalFilterSet):
    slope = df.UUIDFilter(field_name="slope_id")
    cause = df.CharFilter(method="filter_cause")
    location_type = df.CharFilter(field_name="location_type__code")
    locked = df.BooleanFilter(method="filter_locked")
    updated_since = df.IsoDateTimeFilter(field_name="updated_at", lookup_expr="gte")
    search = df.CharFilter(method="filter_search")

    class Meta:
        model = Event
        fields: list[str] = []

    def filter_cause(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        codes = self.data.getlist("cause") if hasattr(self.data, "getlist") else [value]
        return queryset.filter(cause__code__in=codes)

    def filter_locked(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        return queryset.filter(locked_at__isnull=not value)

    def filter_search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        # solo campi non identificativi
        return queryset.filter(Q(location_description__icontains=value) | Q(note__icontains=value))


class PersonFilterSet(df.FilterSet):
    """Filtri globali applicati tramite l'evento + filtri propri della persona."""

    team = df.UUIDFilter(method="filter_team")
    season = df.CharFilter(field_name="event__season__code")
    date_from = df.DateFilter(field_name="event__dateandtime", lookup_expr="date__gte")
    date_to = df.DateFilter(field_name="event__dateandtime", lookup_expr="date__lte")
    ski_area = df.UUIDFilter(field_name="event__ski_area_id")
    zone = df.UUIDFilter(field_name="event__zone_id")
    valid_only = df.BooleanFilter(method="filter_valid_only")
    event = df.UUIDFilter(field_name="event_id")
    gender = df.CharFilter(field_name="gender__code")
    country_code = df.CharFilter(field_name="country_id")
    diagnosis = df.CharFilter(field_name="diagnosis__code")
    equipment = df.CharFilter(field_name="equipment__code")
    evacuation_mean = df.CharFilter(field_name="evacuation_means__mean__code", distinct=True)
    age_min = df.NumberFilter(field_name="age", lookup_expr="gte")
    age_max = df.NumberFilter(field_name="age", lookup_expr="lte")
    helmet = df.BooleanFilter(field_name="helmet")

    class Meta:
        model = Person
        fields: list[str] = []

    def filter_team(self, queryset: QuerySet, name: str, value: object) -> QuerySet:
        teams = self.data.getlist("team") if hasattr(self.data, "getlist") else [value]
        return queryset.filter(event__team_id__in=teams)

    def filter_valid_only(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        return queryset.filter(valid=True) if value else queryset
