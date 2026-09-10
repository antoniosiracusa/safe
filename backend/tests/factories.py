"""Helper per creare dati di test nel tenant corrente."""

from __future__ import annotations

import datetime as dt

from django.contrib.gis.geos import Point

from safe.apps.lookups.models import LookupValue
from safe.apps.org.models import Team
from safe.apps.rescue.models import Event, Person, PersonEvacuationMean
from safe.apps.territory.models import SkiArea, Slope, Zone


def lv(dimension: str, code: str) -> LookupValue:
    return LookupValue.objects.get(dimension=dimension, code=code, company=None)


def territory(area_name: str = "Civetta", zone_name: str = "Val Fiorentina", slope_name: str = "LE CIAUNE"):  # noqa: ANN201
    area, _ = SkiArea.objects.get_or_create(name=area_name)
    zone, _ = Zone.objects.get_or_create(ski_area=area, name=zone_name)
    slope, _ = Slope.objects.get_or_create(
        zone=zone,
        name=slope_name,
        defaults={"regional_code": "C.1.24", "difficulty": lv("slope_difficulty", "blue")},
    )
    return area, zone, slope


def event(team: Team, *, when: dt.datetime | None = None, complete: bool = True, **extra) -> Event:  # noqa: ANN003
    when = when or dt.datetime(2026, 1, 18, 10, 5, tzinfo=dt.UTC)
    fields = {"dateandtime": when, "team": team}
    if complete:
        _, zone, slope = territory()
        fields.update(
            zone=zone,
            slope=slope,
            cause=lv("cause", "collision_person"),
            weather=lv("weather", "clear"),
            snow_condition=lv("snow_condition", "packed"),
            geom=Point(12.0912, 46.4581, srid=4326),
            location_type=lv("location_type", "open_slope"),
            service_report=True,
            witnesses=True,
        )
    fields.update(extra)
    return Event.objects.create(**fields)


def person(ev: Event, *, complete: bool = True, **extra) -> Person:  # noqa: ANN003
    fields = {
        "event": ev,
        "sequence": ev.persons.count() + 1,
        "initials_firstname": "S",
        "initials_surname": "C",
    }
    if complete:
        fields.update(
            age=26,
            gender=lv("gender", "female"),
            country_id="IT",
            diagnosis=lv("diagnosis", "closed_fracture"),
            equipment=lv("equipment", "ski"),
            helmet=True,
        )
    fields.update(extra)
    p = Person.objects.create(**fields)
    if complete:
        PersonEvacuationMean.objects.create(person=p, mean=lv("evacuation_mean", "akja"), order=1)
    return p
