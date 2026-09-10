"""Rapporto di intervento in PDF (WeasyPrint). Pseudonimizzato: iniziali, età, nazione. Mai nomi."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from typing import Any

from django.template.loader import render_to_string

from safe.apps.lookups.models import UNCLASSIFIED, LookupValue
from safe.apps.rescue.models import Event, Person

from .static_map import static_map_data_uri

LANG_LABELS = {
    "it": {"unclassified": "Non classificato", "yes": "Sì", "no": "No", "none": "—"},
    "en": {"unclassified": "Unclassified", "yes": "Yes", "no": "No", "none": "—"},
    "de": {"unclassified": "Nicht klassifiziert", "yes": "Ja", "no": "Nein", "none": "—"},
}


class Labeler:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in LANG_LABELS else "it"
        self.t = LANG_LABELS[self.lang]
        self._all = {(v.dimension, v.code): v for v in LookupValue.objects.active_for_tenant()}
        self.dimensions: dict[str, list[LookupValue]] = {}
        for v in LookupValue.objects.active_for_tenant().order_by("dimension", "sort_order"):
            self.dimensions.setdefault(v.dimension, []).append(v)

    def label(self, obj: LookupValue | None) -> str:
        return obj.label(self.lang) if obj else self.t["unclassified"]

    def yesno(self, v: bool | None) -> str:
        if v is None:
            return self.t["unclassified"]
        return self.t["yes"] if v else self.t["no"]

    def grid(self, dimension: str, selected: set[str]) -> list[dict[str, Any]]:
        """Griglia "a caselle" come nel rapporto di riferimento: tutti i valori, selezionati marcati."""
        return [
            {"label": v.label(self.lang), "checked": v.code in selected}
            for v in self.dimensions.get(dimension, [])
        ]


def person_context(p: Person, lb: Labeler) -> dict[str, Any]:
    means = [m.mean.label(lb.lang) for m in p.evacuation_means.select_related("mean").order_by("order")]
    secondary = {d.diagnosis.code for d in p.secondary_diagnoses.select_related("diagnosis")}
    injuries = [
        {"part": i.body_part.label(lb.lang), "rank": i.rank} for i in p.injuries.select_related("body_part")
    ]
    return {
        "p": p,
        "initials": f"{p.initials_surname or '·'} {p.initials_firstname or '·'}",
        "gender": lb.label(p.gender),
        "country": getattr(p.country, f"name_{lb.lang}", None) if p.country else lb.t["unclassified"],
        "role": lb.label(p.role),
        "helmet": lb.yesno(p.helmet),
        "equipment_grid": lb.grid("equipment", {p.equipment.code} if p.equipment else set()),
        "equipment_owner": lb.label(p.equipment_owner),
        "equipment_condition": lb.label(p.equipment_condition),
        "protections": [
            x.protection.label(lb.lang) for x in p.person_protections.select_related("protection")
        ],
        "insurance_grid": lb.grid("insurance", {p.insurance.code} if p.insurance else set()),
        "accommodation_grid": lb.grid("accommodation", {p.accommodation.code} if p.accommodation else set()),
        "destination_grid": lb.grid("destination", {p.destination.code} if p.destination else set()),
        "diagnosis_grid": lb.grid("diagnosis", ({p.diagnosis.code} if p.diagnosis else set()) | secondary),
        "primary_diagnosis": p.diagnosis.code if p.diagnosis else None,
        "injury_place": lb.label(p.injury_place),
        "injuries": injuries,
        "means": means,
        "responsibility_grid": lb.grid(
            "responsibility", {p.responsibility.code} if p.responsibility else set()
        ),
        "violations": lb.yesno(p.administrative_violations),
        "rescue_refusal": lb.label(p.rescue_refusal),
        "identity_note": bool(p.pii_ciphertext),
    }


def build_context(event: Event, lang: str, *, downloaded_by: str, with_map: bool = True) -> dict[str, Any]:
    lb = Labeler(lang)
    tz = zoneinfo.ZoneInfo(event.company.timezone)
    local = event.dateandtime.astimezone(tz)
    persons = (
        event.persons.filter(deleted_at__isnull=True)
        .select_related(
            "gender",
            "country",
            "equipment",
            "equipment_owner",
            "equipment_condition",
            "insurance",
            "accommodation",
            "destination",
            "diagnosis",
            "injury_place",
            "responsibility",
            "role",
            "rescue_refusal",
        )
        .order_by("sequence")
    )
    map_uri = (
        static_map_data_uri(event.geom.x, event.geom.y) if (with_map and event.geom is not None) else None
    )
    return {
        "lang": lb.lang,
        "event": event,
        "company": event.company,
        "local_dt": local,
        "team": event.team.name,
        "zone": event.zone.name if event.zone else lb.t["none"],
        "slope": event.slope.name if event.slope else lb.t["none"],
        "regional_code": event.slope.regional_code if event.slope else "",
        "location_type_grid": lb.grid(
            "location_type", {event.location_type.code} if event.location_type else set()
        ),
        "difficulty_grid": lb.grid(
            "slope_difficulty", {event.difficulty.code} if event.difficulty else set()
        ),
        "feature_grid": lb.grid(
            "location_feature", {event.location_feature.code} if event.location_feature else set()
        ),
        "snow_grid": lb.grid(
            "snow_condition", {event.snow_condition.code} if event.snow_condition else set()
        ),
        "cause_grid": lb.grid("cause", {event.cause.code} if event.cause else set()),
        "wind_grid": lb.grid("wind", {event.wind.code} if event.wind else set()),
        "visibility_grid": lb.grid("visibility", {event.visibility.code} if event.visibility else set()),
        "traffic_grid": lb.grid("traffic", {event.traffic.code} if event.traffic else set()),
        "snow_making_grid": lb.grid("snow_making", {event.snow_making.code} if event.snow_making else set()),
        "weather_grid": lb.grid("weather", {event.weather.code} if event.weather else set()),
        "event_type_grid": lb.grid("event_type", {event.event_type.code} if event.event_type else set()),
        "witnesses": lb.yesno(event.witnesses),
        "service_report": lb.yesno(event.service_report),
        "operators": [
            o.name or (o.user.full_name if o.user else "") for o in event.operators.select_related("user")
        ],
        "coords": f"{event.geom.y:.5f}, {event.geom.x:.5f}" if event.geom else None,
        "map_uri": map_uri,
        "persons": [person_context(p, lb) for p in persons],
        "downloaded_by": downloaded_by,
        "generated_at": dt.datetime.now(tz),
        "unclassified": lb.t["unclassified"],
        "log_id": str(event.id),
    }


def render_pdf(event: Event, lang: str, *, downloaded_by: str, with_map: bool = True) -> bytes:
    from weasyprint import HTML

    html = render_to_string(
        "reports/event_report.html",
        build_context(event, lang, downloaded_by=downloaded_by, with_map=with_map),
    )
    return HTML(string=html, base_url=".").write_pdf()


def filename_for(event: Event) -> str:
    return f"report-evento-{event.dateandtime:%Y-%m-%d}-{str(event.id)[-8:]}.pdf"


_ = UNCLASSIFIED
