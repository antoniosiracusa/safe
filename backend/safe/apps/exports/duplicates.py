"""Duplicati tra squadre (docs/00 Q3): stesso incidente registrato da due corpi (es. Carabinieri e Truppe
Alpine). Due persone sono duplicate se: eventi di squadre diverse, stessa data locale, stessa pista
(o entrambe senza), |Δ orario| ≤ N minuti, stesso genere, stessa classe d'età A01, stessa attrezzatura.
Parametri per società in company.settings.duplicate_rule."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from safe.apps.rescue.models import Person

from .common import age_class, local


@dataclass
class DuplicateGroup:
    kept_id: str
    merged_ids: list[str]
    teams: list[str]
    event_ids: list[str]
    dateandtime: str

    @property
    def joint(self) -> bool:
        return len(set(self.teams)) > 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "kept_person_id": self.kept_id,
            "merged_person_ids": self.merged_ids,
            "teams": self.teams,
            "event_ids": self.event_ids,
            "dateandtime": self.dateandtime,
            "joint": self.joint,
        }


@dataclass
class _Candidate:
    person: Person
    key: tuple
    when: dt.datetime
    team: str
    members: list[Person] = field(default_factory=list)


def _key(p: Person, fields: list[str], tz: str) -> tuple:
    e = p.event
    d = local(e.dateandtime, tz)
    parts: list[Any] = []
    for f in fields:
        if f == "date":
            parts.append(d.date().isoformat())
        elif f == "slope":
            parts.append(str(e.slope_id) if e.slope_id else None)
        elif f == "gender":
            parts.append(p.gender.code if p.gender else None)
        elif f == "age_class_a01":
            parts.append(age_class(p.age, "veneto_a01"))
        elif f == "equipment":
            parts.append(p.equipment.code if p.equipment else None)
        elif f == "zone":
            parts.append(str(e.zone_id) if e.zone_id else None)
    return tuple(parts)


def find_duplicates(persons: list[Person], rule: dict[str, Any], tz: str) -> list[DuplicateGroup]:
    minutes = int(rule.get("minutes", 30))
    fields = list(rule.get("fields", ["date", "slope", "gender", "age_class_a01", "equipment"]))
    window = dt.timedelta(minutes=minutes)
    by_key: dict[tuple, list[_Candidate]] = {}
    for p in persons:
        c = _Candidate(person=p, key=_key(p, fields, tz), when=p.event.dateandtime, team=str(p.event.team_id))
        by_key.setdefault(c.key, []).append(c)
    groups: list[DuplicateGroup] = []
    for cands in by_key.values():
        cands.sort(key=lambda c: c.when)
        open_groups: list[list[_Candidate]] = []
        for c in cands:
            placed = False
            for g in open_groups:
                if c.when - g[0].when <= window and all(m.team != c.team for m in g):
                    g.append(c)
                    placed = True
                    break
            if not placed:
                open_groups.append([c])
        for g in open_groups:
            if len(g) > 1:
                groups.append(
                    DuplicateGroup(
                        kept_id=str(g[0].person.id),
                        merged_ids=[str(m.person.id) for m in g[1:]],
                        teams=[m.person.event.team.name for m in g],
                        event_ids=[str(m.person.event_id) for m in g],
                        dateandtime=g[0].when.isoformat(),
                    )
                )
    return groups
