"""Dataset sintetico per benchmark e demo (nessun dato reale, nessun dato identificativo).

python manage.py generate_synthetic --company demo --events 100000 --seed 42
"""

from __future__ import annotations

import datetime as dt
import random
import time

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandParser

from safe.apps.lookups.models import LookupValue
from safe.apps.org.models import Team
from safe.apps.rescue.models import Event, Person, PersonEvacuationMean, Season
from safe.apps.tenancy.context import bypass_tenant, tenant_context
from safe.apps.tenancy.models import Company
from safe.apps.territory.models import Slope

COUNTRIES = (
    ["IT"] * 60 + ["DE"] * 12 + ["AT"] * 5 + ["PL"] * 6 + ["CZ"] * 4 + ["NL"] * 3 + ["GB"] * 3 + [None] * 7
)


class Command(BaseCommand):
    help = "Genera eventi e persone sintetici per benchmark"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--company", required=True, help="slug della società")
        parser.add_argument("--events", type=int, default=100000)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--seasons", type=int, default=4)

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        rnd = random.Random(options["seed"])  # noqa: S311 - dati sintetici
        with bypass_tenant():
            company = Company.objects.get(slug=options["company"])
        with tenant_context(company.id):
            teams = list(Team.objects.filter(is_active=True))
            slopes = list(Slope.objects.select_related("zone", "difficulty"))
            lv = {
                d: list(LookupValue.objects.active_for_tenant().dimension(d))
                for d in (
                    "cause",
                    "weather",
                    "snow_condition",
                    "wind",
                    "visibility",
                    "location_type",
                    "gender",
                    "equipment",
                    "insurance",
                    "diagnosis",
                    "injury_place",
                    "evacuation_mean",
                    "destination",
                    "accommodation",
                )
            }
            if not teams or not slopes:
                raise SystemExit("Servono squadre e piste: eseguire prima seed_demo.")
            seasons = list(Season.objects.order_by("-start_date")[: options["seasons"]])

            def pick(dim: str, p_null: float = 0.08):  # noqa: ANN202
                return None if rnd.random() < p_null else rnd.choice(lv[dim])

            t0 = time.time()
            total = options["events"]
            batch_events: list[Event] = []
            for i in range(total):
                season = rnd.choice(seasons)
                day = season.start_date + dt.timedelta(days=180 + int(rnd.gauss(60, 35)) % 150)
                when = dt.datetime.combine(
                    day,
                    dt.time(hour=rnd.choice([9, 10, 11, 11, 12, 13, 14, 15, 16]), minute=rnd.randrange(60)),
                    tzinfo=dt.UTC,
                )
                slope = rnd.choice(slopes) if rnd.random() > 0.1 else None
                batch_events.append(
                    Event(
                        company_id=company.id,
                        season=Season.for_date(day),
                        dateandtime=when,
                        team=rnd.choice(teams),
                        slope=slope,
                        zone=slope.zone if slope else None,
                        ski_area_id=slope.zone.ski_area_id if slope else None,
                        difficulty=slope.difficulty if slope else None,
                        cause=pick("cause"),
                        weather=pick("weather"),
                        snow_condition=pick("snow_condition"),
                        wind=pick("wind"),
                        visibility=pick("visibility"),
                        location_type=pick("location_type"),
                        service_report=rnd.random() < 0.3,
                        witnesses=rnd.choice([True, False, None]),
                        geom=Point(12.05 + rnd.random() * 0.1, 46.40 + rnd.random() * 0.1, srid=4326),
                        valid=True,
                        fully_valid=rnd.random() < 0.9,
                        unlock_count=1 if rnd.random() < 0.03 else 0,
                        locked_at=when + dt.timedelta(days=2),
                    )
                )
                if len(batch_events) >= 2000 or i == total - 1:
                    Event.objects.bulk_create(batch_events)
                    persons: list[Person] = []
                    for ev in batch_events:
                        for seq in range(1, 1 + (1 if rnd.random() < 0.85 else 2)):
                            age = None if rnd.random() < 0.05 else max(3, min(90, int(rnd.gauss(34, 18))))
                            persons.append(
                                Person(
                                    company_id=company.id,
                                    event=ev,
                                    sequence=seq,
                                    age=age,
                                    gender=pick("gender"),
                                    country_id=rnd.choice(COUNTRIES),
                                    initials_firstname="X",
                                    initials_surname="Y",
                                    helmet=rnd.choice([True, True, False, None]),
                                    equipment=pick("equipment"),
                                    insurance=pick("insurance", 0.3),
                                    diagnosis=pick("diagnosis"),
                                    injury_place=pick("injury_place", 0.2),
                                    destination=pick("destination", 0.3),
                                    accommodation=pick("accommodation", 0.4),
                                    valid=True,
                                )
                            )
                    Person.objects.bulk_create(persons)
                    means: list[PersonEvacuationMean] = []
                    for p in persons:
                        n = rnd.choice([0, 1, 1, 1, 2])
                        chosen = rnd.sample(lv["evacuation_mean"], n)
                        means.extend(
                            PersonEvacuationMean(person=p, mean=m, order=k + 1) for k, m in enumerate(chosen)
                        )
                    PersonEvacuationMean.objects.bulk_create(means)
                    batch_events = []
                    self.stdout.write(f"  {i + 1}/{total} eventi ({time.time() - t0:.0f}s)")
            Company.objects.filter(id=company.id).update(data_version=company.data_version + 1)
        self.stdout.write(self.style.SUCCESS(f"Generati {total} eventi in {time.time() - t0:.0f}s"))
