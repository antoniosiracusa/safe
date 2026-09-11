"""Retention e anonimizzazione (docs/07-dpia §3, docs/02 §1): scaduti `retention_identity_years`
dalla data dell'evento, la persona perde dati cifrati, iniziali ed età (resta la classe di età);
l'audit log viene cancellato dopo `retention_audit_years`."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from safe.apps.audit import service as audit
from safe.apps.audit.models import AuditLog
from safe.apps.tenancy.models import Company

from .models import Person


def identity_cutoff(company: Company, now: dt.datetime | None = None) -> dt.datetime:
    now = now or timezone.now()
    return now - dt.timedelta(days=365 * company.retention_identity_years)


def due_persons(company: Company, now: dt.datetime | None = None) -> QuerySet:
    return Person.objects.filter(
        anonymized_at__isnull=True,
        event__dateandtime__lt=identity_cutoff(company, now),
    ).filter(
        Q(pii_ciphertext__isnull=False)
        | ~Q(initials_firstname="")
        | ~Q(initials_surname="")
        | Q(age__isnull=False)
    )


def anonymize(person: Person, *, actor: Any = None, request: Any = None, reason: str = "retention") -> None:
    fields = []
    if person.pii_ciphertext is not None:
        fields += ["pii_ciphertext", "pii_key_wrapped", "pii_key_version", "pii_fields"]
    if person.initials_firstname or person.initials_surname:
        fields += ["initials_firstname", "initials_surname"]
    if person.age is not None:
        fields.append("age")
    person.pii_ciphertext = None
    person.pii_key_wrapped = None
    person.pii_key_version = None
    person.pii_fields = []
    person.initials_firstname = ""
    person.initials_surname = ""
    person.age = None
    person.anonymized_at = timezone.now()
    person.save(update_fields=[*dict.fromkeys(fields), "anonymized_at", "updated_at"])
    audit.record(
        "person.anonymize",
        "person",
        object_id=person.id,
        event_id=person.event_id,
        actor=actor,
        request=request,
        changed_fields=sorted(set(fields)),
        metadata={"reason": reason},
    )


def run_for_company(company: Company, *, actor: Any = None) -> dict[str, int]:
    """Anonimizza le persone scadute e cancella l'audit oltre la retention. Da chiamare nel tenant."""
    count = 0
    for p in due_persons(company).iterator(chunk_size=500):
        anonymize(p, actor=actor)
        count += 1
    audit_cutoff = timezone.now() - dt.timedelta(days=365 * company.retention_audit_years)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.audit_purge = 'on'")
        purged, _ = AuditLog.objects.filter(created_at__lt=audit_cutoff).delete()
    if count or purged:
        audit.record(
            "retention.run",
            "company",
            object_id=company.id,
            actor=actor,
            metadata={"persons_anonymized": count, "audit_rows_purged": purged},
        )
    return {"persons_anonymized": count, "audit_rows_purged": purged}


def status_for(company: Company) -> dict[str, Any]:
    due = due_persons(company)
    last = AuditLog.objects.filter(action="retention.run").order_by("-created_at").first()
    return {
        "retention_identity_years": company.retention_identity_years,
        "retention_audit_years": company.retention_audit_years,
        "identity_cutoff": identity_cutoff(company),
        "persons_due": due.count(),
        "persons_anonymized_total": Person.objects.filter(anonymized_at__isnull=False).count(),
        "last_run": {"at": last.created_at, **last.metadata} if last else None,
    }
