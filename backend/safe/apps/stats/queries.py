"""Aggregazioni SQL (una query per grafico). `None` nei risultati = non classificato."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from collections import Counter

from django.db.models import Case, CharField, Count, OuterRef, Q, QuerySet, Subquery, Value, When
from django.db.models.functions import ExtractIsoWeekDay, ExtractMonth

from .chart import AGE_CLUSTERS


def age_class_expr(cluster: str) -> Case:
    whens = []
    for upper, label in AGE_CLUSTERS[cluster]:
        cond = Q(age__lte=upper) if upper is not None else Q(age__isnull=False)
        whens.append(When(cond, then=Value(label)))
    return Case(*whens, default=Value(None), output_field=CharField())


def count_by(qs: QuerySet, field: str) -> dict:
    """{valore: n} per un campo (codice lookup via `field__code`)."""
    return {
        row[field]: row["n"] for row in qs.values(field).annotate(n=Count("id", distinct=True)).order_by()
    }


def count_by_two(qs: QuerySet, x: str, s: str, *, x_expr=None) -> dict:  # noqa: ANN001
    """{(x, serie): n}."""
    if x_expr is not None:
        qs = qs.annotate(_x=x_expr)
        x = "_x"
    rows = qs.values(x, s).annotate(n=Count("id", distinct=True)).order_by()
    return {(row[x], row[s]): row["n"] for row in rows}


# --- riepilogo zona ------------------------------------------------------------


def events_by_season_month(events: QuerySet, tz: zoneinfo.ZoneInfo) -> dict[tuple[str, int], int]:
    rows = (
        events.annotate(m=ExtractMonth("dateandtime", tzinfo=tz))
        .values("season__code", "m")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {(r["season__code"], r["m"]): r["n"] for r in rows}


def zone_season_table(
    events: QuerySet,
) -> tuple[list[str], dict[tuple[str | None, str], dict[str, int]], dict[str | None, str | None]]:
    """Restituisce (stagioni ordinate, {(zone_id, season): {events, persons}}, {zone_id: nome})."""
    ev_rows = events.values("zone_id", "zone__name", "season__code").annotate(n=Count("id")).order_by()
    pe_rows = (
        events.values("zone_id", "season__code")
        .annotate(p=Count("persons", filter=Q(persons__deleted_at__isnull=True)))
        .order_by()
    )
    table: dict[tuple[str | None, str], dict[str, int]] = {}
    names: dict[str | None, str | None] = {}
    for r in ev_rows:
        key = (str(r["zone_id"]) if r["zone_id"] else None, r["season__code"])
        table.setdefault(key, {"events": 0, "persons": 0})["events"] += r["n"]
        names[key[0]] = r["zone__name"]
    for r in pe_rows:
        key = (str(r["zone_id"]) if r["zone_id"] else None, r["season__code"])
        table.setdefault(key, {"events": 0, "persons": 0})["persons"] += r["p"]
    seasons = sorted({k[1] for k in table})
    return seasons, table, names


# --- demografia ----------------------------------------------------------------


def nationality_by_weekday(
    persons: QuerySet, tz: zoneinfo.ZoneInfo, home_country: str
) -> dict[tuple[int, str], int]:
    rows = (
        persons.annotate(
            wd=ExtractIsoWeekDay("event__dateandtime", tzinfo=tz),
            nat=Case(
                When(country_id__isnull=True, then=Value("unclassified")),
                When(country_id=home_country, then=Value("national")),
                default=Value("foreign"),
                output_field=CharField(),
            ),
        )
        .values("wd", "nat")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {(r["wd"], r["nat"]): r["n"] for r in rows}


def top_countries(persons: QuerySet, limit: int) -> tuple[list[tuple[str, int]], int, int]:
    """(top N [(code, n)], altri, non classificato)."""
    counts: Counter[str] = Counter()
    unclassified = 0
    for row in persons.values("country_id").annotate(n=Count("id")).order_by():
        if row["country_id"] is None:
            unclassified += row["n"]
        else:
            counts[row["country_id"]] += row["n"]
    ordered = counts.most_common()
    top = ordered[:limit]
    other = sum(n for _, n in ordered[limit:])
    return top, other, unclassified


# --- tipologia -----------------------------------------------------------------


def first_evacuation_mean_by_age(persons: QuerySet, cluster: str) -> dict[tuple[str | None, str | None], int]:
    """Primo mezzo (order=1) per classe di età; senza mezzi → non classificato. Una riga per persona."""
    from safe.apps.rescue.models import PersonEvacuationMean

    first = PersonEvacuationMean.objects.filter(person=OuterRef("pk"), order=1).values("mean__code")[:1]
    rows = (
        persons.annotate(_x=age_class_expr(cluster), first_mean=Subquery(first))
        .values("_x", "first_mean")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {(r["_x"], r["first_mean"]): r["n"] for r in rows}


def evacuation_means_total(persons: QuerySet) -> dict[str | None, int]:
    from safe.apps.rescue.models import PersonEvacuationMean

    rows = (
        PersonEvacuationMean.objects.filter(person__in=persons.values("id"))
        .values("mean__code")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {r["mean__code"]: r["n"] for r in rows}


# --- riepilogo stagione --------------------------------------------------------


def season_summary_by_team(events: QuerySet, season_events: QuerySet, now: dt.datetime) -> list[dict]:
    week_end = now.date() - dt.timedelta(days=now.weekday() + 1)  # domenica scorsa
    week_start = week_end - dt.timedelta(days=6)
    rows = (
        season_events.values("team_id", "team__name")
        .annotate(
            season_events=Count("id", distinct=True),
            last_week_events=Count(
                "id",
                filter=Q(dateandtime__date__gte=week_start, dateandtime__date__lte=week_end),
                distinct=True,
            ),
            unlocked_events=Count("id", filter=Q(unlock_count__gt=0), distinct=True),
            invalid_events=Count("id", filter=Q(fully_valid=False), distinct=True),
            helicopter_rescues=Count(
                "id",
                filter=Q(
                    persons__evacuation_means__mean__code="helicopter_118", persons__deleted_at__isnull=True
                ),
                distinct=True,
            ),
        )
        .order_by("team__name")
    )
    return [
        {
            "team": {"id": str(r["team_id"]), "name": r["team__name"]},
            "season_events": r["season_events"],
            "last_week_events": r["last_week_events"],
            "unlocked_events": r["unlocked_events"],
            "invalid_events": r["invalid_events"],
            "helicopter_rescues": r["helicopter_rescues"],
            "week": {"from": week_start.isoformat(), "to": week_end.isoformat()},
        }
        for r in rows
    ]
