"""Le 22 rotte statistiche (docs/03-openapi.yaml, tag stats). Tutte restituiscono payload Chart.js
già aggregati; le tabelle restituiscono righe/colonne pronte."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter
from rest_framework.request import Request
from rest_framework.response import Response

from safe.apps.lookups.models import UNCLASSIFIED, Country
from safe.apps.rescue.models import Event, Person, Season
from safe.apps.territory.models import SkiArea, Slope

from . import queries as q
from .base import StatsView, stats_schema
from .chart import MONTHS, PALETTE, SEASON_MONTHS, WEEKDAYS, Axis, i18n, multi_series, single_series

AGE_PARAM = OpenApiParameter("age_cluster", str, required=False, description="standard | veneto_a01")
LIMIT_PARAM = OpenApiParameter("limit", int, required=False)

# ----------------------------------------------------------------------------- riepilogo zona


class AnnualDistributionView(StatsView):
    """Eventi per mese di stagione (giu→mag), una serie per stagione (le ultime 3 fino a quella filtrata)."""

    @stats_schema("Distribuzione annuale incidenti", [OpenApiParameter("incremental", bool, required=False)])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        lang = self.lang
        incremental = self.request.query_params.get("incremental") in ("true", "1")
        selected = self.request.query_params.get("season") or Season.current().code
        first = self.company.first_season or ""
        all_codes = [s.code for s in Season.objects.order_by("start_date") if first <= s.code <= selected]
        seasons = all_codes[-3:]
        events = self.events(apply_season=False).filter(season__code__in=seasons)
        counts = q.events_by_season_month(events, self.tz)
        labels = [MONTHS[lang][m - 1] for m in SEASON_MONTHS]
        datasets = []
        for k, code in enumerate(seasons):
            data, running = [], 0
            for m in SEASON_MONTHS:
                running = running + counts.get((code, m), 0) if incremental else counts.get((code, m), 0)
                data.append(running)
            datasets.append(
                {"label": code, "data": data, "backgroundColor": PALETTE[k % len(PALETTE)], "code": code}
            )
        return {
            "labels": labels,
            "datasets": datasets,
            "meta": {
                "unit": "events",
                "incremental": incremental,
                "seasons": seasons,
                "total": sum(counts.values()),
            },
        }


class ZoneTableView(StatsView):
    @stats_schema("Tabella zona × stagione")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        seasons, table, names = q.zone_season_table(self.events(apply_season=False))
        zone_ids = sorted({k[0] for k in table}, key=lambda z: (z is None, names.get(z) or ""))
        rows, totals = [], [{"events": 0, "persons": 0} for _ in seasons]
        for zid in zone_ids:
            cells = [dict(table.get((zid, s), {"events": 0, "persons": 0})) for s in seasons]
            for i, c in enumerate(cells):
                totals[i]["events"] += c["events"]
                totals[i]["persons"] += c["persons"]
            rows.append(
                {
                    "zone": {"id": zid, "name": names.get(zid) or i18n(UNCLASSIFIED, self.lang)},
                    "cells": cells,
                    "total": {
                        "events": sum(c["events"] for c in cells),
                        "persons": sum(c["persons"] for c in cells),
                    },
                }
            )
        return {"columns": seasons, "rows": rows, "totals": totals, "meta": {"unit": "events"}}


# ----------------------------------------------------------------------------- demografia


class AgeGenderView(StatsView):
    @stats_schema("Classe di età × genere", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        persons = self.persons()
        counts = q.count_by_two(persons, "_x", "gender__code", x_expr=q.age_class_expr(self.age_cluster))
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("gender", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class CountryView(StatsView):
    @stats_schema("Distribuzione per paese", [LIMIT_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        limit = min(max(int(self.request.query_params.get("limit", 10)), 1), 100)
        top, other, unclassified = q.top_countries(self.persons(), limit)
        names = {
            c.code: getattr(c, f"name_{self.lang}")
            for c in Country.objects.filter(code__in=[c for c, _ in top])
        }
        codes = [c for c, _ in top] + (["other"] if other else []) + [UNCLASSIFIED]
        labels = {
            **{c: names.get(c, c) for c, _ in top},
            "other": i18n("other", self.lang),
            UNCLASSIFIED: i18n(UNCLASSIFIED, self.lang),
        }
        axis = Axis(codes, labels)
        counts: dict = {c: n for c, n in top}
        counts["other"] = other
        counts[None] = unclassified
        return single_series(
            axis,
            counts,
            series_label=i18n("persons", self.lang),
            unit="persons",
            color_by_label=False,
            meta={"limit": limit},
        )


class NationalityWeekdayView(StatsView):
    @stats_schema("Connazionali vs stranieri per giorno della settimana")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        home = self.company.settings.get("country_code", "IT")
        counts = q.nationality_by_weekday(self.persons(), self.tz, home)
        x = Axis([str(i) for i in range(1, 8)], {str(i + 1): WEEKDAYS[self.lang][i] for i in range(7)})
        series = Axis.from_pairs(
            [("national", i18n("national", self.lang)), ("foreign", i18n("foreign", self.lang))], self.lang
        )
        return multi_series(
            x,
            series,
            {(str(wd), nat): n for (wd, nat), n in counts.items()},
            unit="persons",
            meta={"home_country": home, "lang": self.lang},
        )


class AgeDiagnosisView(StatsView):
    @stats_schema("Classe di età × diagnosi presunta", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.count_by_two(
            self.persons(), "_x", "diagnosis__code", x_expr=q.age_class_expr(self.age_cluster)
        )
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("diagnosis", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class AgeInjuryPlaceView(StatsView):
    @stats_schema("Classe di età × sede lesione", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.count_by_two(
            self.persons(), "_x", "injury_place__code", x_expr=q.age_class_expr(self.age_cluster)
        )
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("injury_place", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


# ----------------------------------------------------------------------------- tipologia


class AgeCauseView(StatsView):
    @stats_schema("Classe di età × causa", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.count_by_two(
            self.persons(), "_x", "event__cause__code", x_expr=q.age_class_expr(self.age_cluster)
        )
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("cause", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class CauseView(StatsView):
    @stats_schema("Distribuzione cause")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        return single_series(
            Axis.from_lookup("cause", self.lang),
            q.count_by(self.events(), "cause__code"),
            series_label=i18n("events", self.lang),
            unit="events",
        )


class AgeEquipmentView(StatsView):
    @stats_schema("Classe di età × attrezzatura", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.count_by_two(
            self.persons(), "_x", "equipment__code", x_expr=q.age_class_expr(self.age_cluster)
        )
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("equipment", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class AgeInsuranceView(StatsView):
    @stats_schema("Classe di età × assicurazione", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.count_by_two(
            self.persons(), "_x", "insurance__code", x_expr=q.age_class_expr(self.age_cluster)
        )
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("insurance", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class AgeEvacuationMeanView(StatsView):
    @stats_schema("Classe di età × mezzo di evacuazione (primo mezzo)", [AGE_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        counts = q.first_evacuation_mean_by_age(self.persons(), self.age_cluster)
        return multi_series(
            Axis.age_classes(self.age_cluster, self.lang),
            Axis.from_lookup("evacuation_mean", self.lang),
            counts,
            unit="persons",
            meta={"age_cluster": self.age_cluster, "lang": self.lang},
        )


class EvacuationMeansTotalView(StatsView):
    @stats_schema("Totale mezzi di evacuazione utilizzati")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        axis = Axis.from_lookup("evacuation_mean", self.lang, with_unclassified=False)
        return single_series(
            axis,
            q.evacuation_means_total(self.persons()),
            series_label=i18n("means", self.lang),
            unit="means",
        )


# ----------------------------------------------------------------------------- geografia


class SkiAreasView(StatsView):
    @stats_schema("Eventi per comprensorio")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        areas = list(SkiArea.objects.filter(is_active=True).order_by("name"))
        axis = Axis.from_pairs([(str(a.id), a.name) for a in areas], self.lang)
        counts = {str(k) if k else None: n for k, n in q.count_by(self.events(), "ski_area_id").items()}
        return single_series(
            axis, counts, series_label=i18n("events", self.lang), unit="events", color_by_label=False
        )


class SlopeDifficultyView(StatsView):
    @stats_schema("Eventi per difficoltà pista")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        return single_series(
            Axis.from_lookup("slope_difficulty", self.lang),
            q.count_by(self.events(), "difficulty__code"),
            series_label=i18n("events", self.lang),
            unit="events",
        )


class SlopesView(StatsView):
    @stats_schema("Eventi per singola pista (ordinati, slider limit)", [LIMIT_PARAM])
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        limit = min(max(int(self.request.query_params.get("limit", 20)), 1), 200)
        counts = {str(k) if k else None: n for k, n in q.count_by(self.events(), "slope_id").items()}
        slopes = Slope.objects.filter(id__in=[k for k in counts if k]).select_related("zone")
        axis = Axis.from_pairs([(str(s.id), s.name) for s in slopes], self.lang)
        return single_series(
            axis,
            counts,
            series_label=i18n("events", self.lang),
            unit="events",
            color_by_label=False,
            sort_desc=True,
            limit=limit,
            meta={"limit": limit},
        )


# ----------------------------------------------------------------------------- meteo


class _LookupCountView(StatsView):
    dimension = ""
    field = ""

    def compute(self) -> dict[str, Any]:
        return single_series(
            Axis.from_lookup(self.dimension, self.lang),
            q.count_by(self.events(), self.field),
            series_label=i18n("events", self.lang),
            unit="events",
        )


class WeatherView(_LookupCountView):
    dimension, field = "weather", "weather__code"

    @stats_schema("Eventi per condizione meteo")
    def get(self, request: Request) -> Response:
        return super().get(request)


class SnowView(_LookupCountView):
    dimension, field = "snow_condition", "snow_condition__code"

    @stats_schema("Eventi per tipologia neve")
    def get(self, request: Request) -> Response:
        return super().get(request)


class WindView(_LookupCountView):
    dimension, field = "wind", "wind__code"

    @stats_schema("Eventi per vento")
    def get(self, request: Request) -> Response:
        return super().get(request)


class VisibilityView(_LookupCountView):
    dimension, field = "visibility", "visibility__code"

    @stats_schema("Eventi per visibilità")
    def get(self, request: Request) -> Response:
        return super().get(request)


# ----------------------------------------------------------------------------- riepilogo stagione


class SeasonSummaryView(StatsView):
    required_permissions = ("stats.view", "stats.advanced")
    cache_seconds = 60

    @stats_schema("Riepilogo stagione per squadra")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        selected = self.request.query_params.get("season") or Season.current().code
        base = self.events(apply_season=False)
        season_events = base.filter(season__code=selected)
        rows = q.season_summary_by_team(base, season_events, timezone.now().astimezone(self.tz))
        keys = (
            "season_events",
            "last_week_events",
            "unlocked_events",
            "invalid_events",
            "helicopter_rescues",
        )
        totals = {k: sum(r[k] for r in rows) for k in keys}
        week = rows[0]["week"] if rows else None
        for r in rows:
            r.pop("week", None)
        return {
            "season": selected,
            "last_week": week,
            "rows": rows,
            "totals": totals,
            "meta": {"unit": "events"},
        }


class GeneralView(StatsView):
    required_permissions = ()

    @stats_schema("KPI per la home")
    def get(self, request: Request) -> Response:
        return super().get(request)

    def compute(self) -> dict[str, Any]:
        events = self.events(apply_season=False)
        current = Season.current().code
        return {
            "total_events": events.count(),
            "total_persons": Person.objects.filter(
                deleted_at__isnull=True, event__in=events.values("id")
            ).count(),
            "total_seasons": events.values("season").distinct().count(),
            "current_season": current,
            "current_season_events": events.filter(season__code=current).count(),
            "invalid_events": events.filter(fully_valid=False).count(),
            "meta": {"unit": "events"},
        }


__all__ = [n for n in dir() if n.endswith("View")]
_ = (Event,)
