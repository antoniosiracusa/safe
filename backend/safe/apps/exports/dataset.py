"""Export CSV/XLSX dei dataset filtrati (eventi o persone), pseudonimizzati: mai nomi o contatti."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, QuerySet

from safe.apps.core.filters import GlobalFilterSet
from safe.apps.rescue.filters import PersonFilterSet
from safe.apps.rescue.models import Event, Person
from safe.apps.rescue.views import EVENT_SELECT, PERSON_PREFETCH, PERSON_SELECT, scope_events, user_team_ids

from .common import Labels, age_class, local, write_csv, write_xlsx

HEADERS = {
    "events": {
        "it": [
            "ID evento",
            "Stagione",
            "Data",
            "Ora",
            "Squadra",
            "Comprensorio",
            "Zona",
            "Pista",
            "Codice regionale",
            "Difficoltà",
            "Tipo di luogo",
            "Descrizione del luogo",
            "Latitudine",
            "Longitudine",
            "Causa",
            "Causa - testo",
            "Meteo",
            "Neve",
            "Vento",
            "Visibilità",
            "Relazione di servizio",
            "Testimoni",
            "Persone",
            "Valido",
            "Bloccato",
        ],
        "en": [
            "Event ID",
            "Season",
            "Date",
            "Time",
            "Team",
            "Ski area",
            "Zone",
            "Slope",
            "Regional code",
            "Difficulty",
            "Location type",
            "Location description",
            "Latitude",
            "Longitude",
            "Cause",
            "Cause - notes",
            "Weather",
            "Snow",
            "Wind",
            "Visibility",
            "Service report",
            "Witnesses",
            "Persons",
            "Valid",
            "Locked",
        ],
        "de": [
            "Ereignis-ID",
            "Saison",
            "Datum",
            "Uhrzeit",
            "Team",
            "Skigebiet",
            "Zone",
            "Piste",
            "Regionalcode",
            "Schwierigkeit",
            "Ortstyp",
            "Ortsbeschreibung",
            "Breitengrad",
            "Längengrad",
            "Ursache",
            "Ursache - Text",
            "Wetter",
            "Schnee",
            "Wind",
            "Sicht",
            "Dienstbericht",
            "Zeugen",
            "Personen",
            "Gültig",
            "Gesperrt",
        ],
    },
    "persons": {
        "it": [
            "ID evento",
            "Stagione",
            "Data",
            "Ora",
            "Squadra",
            "Zona",
            "Pista",
            "N.",
            "Iniziale cognome",
            "Iniziale nome",
            "Età",
            "Classe età",
            "Genere",
            "Nazione",
            "Casco",
            "Attrezzatura",
            "Proprietà attrezzatura",
            "Assicurazione",
            "Assicurazione - note",
            "Alloggio",
            "Destinazione",
            "Diagnosi presunta",
            "Diagnosi secondarie",
            "Sede lesione",
            "Lesione principale",
            "Mezzi di evacuazione",
            "Responsabilità",
            "Violazioni amministrative",
            "Valido",
        ],
        "en": [
            "Event ID",
            "Season",
            "Date",
            "Time",
            "Team",
            "Zone",
            "Slope",
            "No.",
            "Surname initial",
            "First name initial",
            "Age",
            "Age class",
            "Gender",
            "Country",
            "Helmet",
            "Equipment",
            "Equipment ownership",
            "Insurance",
            "Insurance - notes",
            "Accommodation",
            "Destination",
            "Presumed diagnosis",
            "Secondary diagnoses",
            "Injury site",
            "Main injury",
            "Evacuation means",
            "Responsibility",
            "Administrative violations",
            "Valid",
        ],
        "de": [
            "Ereignis-ID",
            "Saison",
            "Datum",
            "Uhrzeit",
            "Team",
            "Zone",
            "Piste",
            "Nr.",
            "Initiale Nachname",
            "Initiale Vorname",
            "Alter",
            "Altersklasse",
            "Geschlecht",
            "Land",
            "Helm",
            "Ausrüstung",
            "Eigentum Ausrüstung",
            "Versicherung",
            "Versicherung - Notizen",
            "Unterkunft",
            "Ziel",
            "Verdachtsdiagnose",
            "Nebendiagnosen",
            "Verletzungsstelle",
            "Hauptverletzung",
            "Evakuierungsmittel",
            "Verantwortung",
            "Verwaltungsverstöße",
            "Gültig",
        ],
    },
}


def _short(uuid) -> str:  # noqa: ANN001
    return str(uuid)[-8:].upper()


def event_rows(qs: QuerySet, lb: Labels, tz: str) -> list[list[Any]]:
    rows = []
    for e in qs.iterator(chunk_size=2000):
        d = local(e.dateandtime, tz)
        rows.append(
            [
                _short(e.id),
                e.season.code,
                d.strftime("%d/%m/%Y"),
                d.strftime("%H:%M"),
                e.team.name,
                e.ski_area.name if e.ski_area else "",
                e.zone.name if e.zone else "",
                e.slope.name if e.slope else "",
                e.slope.regional_code if e.slope else "",
                lb.of(e.difficulty),
                lb.of(e.location_type),
                e.location_description or "",
                round(e.geom.y, 6) if e.geom else None,
                round(e.geom.x, 6) if e.geom else None,
                lb.of(e.cause),
                e.cause_note or "",
                lb.of(e.weather),
                lb.of(e.snow_condition),
                lb.of(e.wind),
                lb.of(e.visibility),
                lb.yesno(e.service_report),
                lb.yesno(e.witnesses),
                e.persons_count,
                lb.yesno(e.fully_valid),
                lb.yesno(e.locked_at is not None),
            ]
        )
    return rows


def person_rows(qs: QuerySet, lb: Labels, tz: str) -> list[list[Any]]:
    rows = []
    for p in qs.iterator(chunk_size=2000):
        e = p.event
        d = local(e.dateandtime, tz)
        rows.append(
            [
                _short(e.id),
                e.season.code,
                d.strftime("%d/%m/%Y"),
                d.strftime("%H:%M"),
                e.team.name,
                e.zone.name if e.zone else "",
                e.slope.name if e.slope else "",
                p.sequence,
                p.initials_surname,
                p.initials_firstname,
                p.age,
                age_class(p.age) or "",
                lb.of(p.gender),
                getattr(p.country, f"name_{lb.lang}", "") if p.country else "",
                lb.yesno(p.helmet),
                lb.of(p.equipment),
                lb.of(p.equipment_owner),
                lb.of(p.insurance),
                p.insurance_note or "",
                lb.of(p.accommodation),
                lb.of(p.destination),
                lb.of(p.diagnosis),
                ", ".join(d.diagnosis.label(lb.lang) for d in p.secondary_diagnoses.all()),
                lb.of(p.injury_place),
                lb.of(p.gravest_injury),
                " → ".join(
                    m.mean.label(lb.lang) for m in sorted(p.evacuation_means.all(), key=lambda m: m.order)
                ),
                lb.of(p.responsibility),
                lb.yesno(p.administrative_violations),
                lb.yesno(p.valid),
            ]
        )
    return rows


def build(
    dataset: str, fmt: str, filters: dict[str, Any], user, lang: str, tz: str
) -> tuple[bytes, str, str]:  # noqa: ANN001
    lb = Labels(lang)
    headers = HEADERS[dataset][lb.lang]
    if dataset == "events":
        qs = scope_events(Event.objects.filter(deleted_at__isnull=True), user).select_related(*EVENT_SELECT)
        qs = (
            GlobalFilterSet(filters, queryset=qs)
            .qs.annotate(persons_count=Count("persons", filter=Q(persons__deleted_at__isnull=True)))
            .order_by("-dateandtime")
        )
        rows = event_rows(qs, lb, tz)
    else:
        qs = Person.objects.filter(deleted_at__isnull=True, event__deleted_at__isnull=True)
        if "events.view_own_teams_only" in getattr(user, "_perm_cache", ()):  # pragma: no cover - vedi sotto
            qs = qs.filter(event__team_id__in=user_team_ids(user))
        from safe.apps.authz.resolve import effective_permissions

        if "events.view_own_teams_only" in effective_permissions(user):
            qs = qs.filter(event__team_id__in=user_team_ids(user))
        qs = (
            PersonFilterSet(filters, queryset=qs)
            .qs.select_related(*PERSON_SELECT)
            .prefetch_related(*PERSON_PREFETCH)
        )
        qs = qs.order_by("-event__dateandtime", "sequence")
        rows = person_rows(qs, lb, tz)
    if fmt == "csv":
        return write_csv(headers, rows), f"safe-{dataset}.csv", "text/csv"
    return (
        write_xlsx(headers, rows, sheet=dataset),
        f"safe-{dataset}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
