"""Regole di dominio su eventi e persone: validità calcolata, blocco/sblocco, idempotenza."""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from safe.apps.audit import service as audit
from safe.apps.core.exceptions import ConflictError
from safe.apps.tenancy.models import Company

from .models import Event, Person

EVENT_CHECKS = {
    "dateandtime": lambda e: e.dateandtime is not None,
    "team": lambda e: e.team_id is not None,
    "zone": lambda e: e.zone_id is not None,
    "location": lambda e: e.slope_id is not None or e.location_type_id is not None,
    "cause": lambda e: e.cause_id is not None,
    "geometry": lambda e: e.geom is not None,
    "weather": lambda e: e.weather_id is not None,
    "snow_condition": lambda e: e.snow_condition_id is not None,
}

PERSON_CHECKS = {
    "age": lambda p: p.age is not None,
    "gender": lambda p: p.gender_id is not None,
    "country": lambda p: p.country_id is not None,
    "diagnosis": lambda p: p.diagnosis_id is not None,
    "injury_place": lambda p: p.injury_place_id is not None,
    "equipment": lambda p: p.equipment_id is not None,
    "evacuation_means": lambda p: p.evacuation_means.exists(),
    "destination": lambda p: p.destination_id is not None,
}


def _rules(company: Company) -> dict[str, list[str]]:
    return company.validity_rules


def compute_person_validity(person: Person, rules: dict[str, list[str]] | None = None) -> list[dict]:
    rules = rules or _rules(person.company)
    errors = [
        {"field": name, "code": "required"}
        for name in rules["person_required"]
        if name in PERSON_CHECKS and not PERSON_CHECKS[name](person)
    ]
    person.validation_errors = errors
    person.valid = not errors
    return errors


def compute_event_validity(event: Event, *, save: bool = True) -> None:
    """Ricalcola `valid` dell'evento, `valid` di ogni persona e `fully_valid` (evento valido,
    almeno una persona e tutte valide). Record incompleti restano: cambia solo lo stato."""
    rules = _rules(event.company)
    errors = [
        {"field": name, "code": "required"}
        for name in rules["event_required"]
        if name in EVENT_CHECKS and not EVENT_CHECKS[name](event)
    ]
    persons = list(event.persons.filter(deleted_at__isnull=True))
    all_persons_valid = True
    for p in persons:
        compute_person_validity(p, rules)
        all_persons_valid = all_persons_valid and p.valid
        if save:
            p.save(update_fields=["valid", "validation_errors", "updated_at"])
    if not persons:
        errors.append({"field": "persons", "code": "required"})
    event.validation_errors = errors
    event.valid = not [e for e in errors if e["field"] != "persons"]
    event.fully_valid = event.valid and bool(persons) and all_persons_valid
    if save:
        event.save(update_fields=["valid", "fully_valid", "validation_errors", "updated_at"])


def ensure_unlocked(event: Event) -> None:
    if event.is_locked:
        raise ConflictError({"detail": "L'evento è bloccato: richiedere lo sblocco.", "code": "event_locked"})


def lock_event(event: Event, user, request=None) -> Event:  # noqa: ANN001
    if not event.is_locked:
        event.locked_at = timezone.now()
        event.locked_by = user
        event.save(update_fields=["locked_at", "locked_by", "updated_at"])
        audit.record(
            "event.lock", "event", object_id=event.id, event_id=event.id, actor=user, request=request
        )
    return event


def unlock_event(event: Event, user, reason: str, request=None) -> Event:  # noqa: ANN001
    if event.is_locked:
        event.locked_at = None
        event.locked_by = None
        event.unlock_count += 1
        event.last_unlocked_at = timezone.now()
        event.save(update_fields=["locked_at", "locked_by", "unlock_count", "last_unlocked_at", "updated_at"])
        audit.record(
            "event.unlock",
            "event",
            object_id=event.id,
            event_id=event.id,
            actor=user,
            request=request,
            metadata={"reason": reason[:500]},
        )
    return event


def auto_lock_due_events(now: dt.datetime | None = None) -> int:
    """Blocca gli eventi più vecchi di `auto_lock_hours` (impostazione società). Chiamato dal beat."""
    now = now or timezone.now()
    count = 0
    with transaction.atomic():
        for event in Event.objects.filter(locked_at__isnull=True, deleted_at__isnull=True).select_related(
            "company"
        ):
            if event.created_at + dt.timedelta(hours=event.company.auto_lock_hours) <= now:
                event.locked_at = now
                event.save(update_fields=["locked_at", "updated_at"])
                count += 1
    return count


def soft_delete(obj: Event | Person, user, request=None) -> None:  # noqa: ANN001
    obj.deleted_at = timezone.now()
    obj.save(update_fields=["deleted_at", "updated_at"])
    kind = obj.__class__.__name__.lower()
    audit.record(
        f"{kind}.delete",
        kind,
        object_id=obj.id,
        event_id=getattr(obj, "event_id", obj.id),
        actor=user,
        request=request,
    )
