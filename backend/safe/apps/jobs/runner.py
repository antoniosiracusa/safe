"""Esecuzione dei job asincroni: un task Celery generico che carica il job, entra nel contesto tenant,
invoca l'handler registrato per `kind` e salva il risultato nello storage."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from celery import shared_task
from django.utils import timezone

from safe.apps.tenancy.context import bypass_tenant, tenant_context

from . import storage
from .models import AsyncJob

log = logging.getLogger(__name__)


@dataclass
class JobResult:
    data: bytes
    filename: str
    mime: str
    extra: dict[str, Any] | None = None


Handler = Callable[[AsyncJob], JobResult]
_HANDLERS: dict[str, Handler] = {}

EXTENSIONS = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
}


def register(kind: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return deco


def enqueue(
    *, company_id: Any, user: Any, kind: str, params: dict[str, Any], expires_days: int = 7
) -> AsyncJob:
    """Crea il job e lo mette in coda. In test (CELERY_TASK_ALWAYS_EAGER) viene eseguito subito."""
    job = AsyncJob.objects.create(
        company_id=company_id,
        requested_by=user,
        kind=kind,
        params=params,
        expires_at=timezone.now() + dt.timedelta(days=expires_days),
    )
    run_job.delay(str(job.id), str(company_id))
    job.refresh_from_db()
    return job


@shared_task(name="safe.apps.jobs.run", bind=True, max_retries=2)
def run_job(self, job_id: str, company_id: str) -> str:  # noqa: ANN001
    with tenant_context(uuid.UUID(company_id)):
        job = AsyncJob.objects.select_related("requested_by").get(pk=job_id)
        job.status = AsyncJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])
        try:
            handler = _HANDLERS[job.kind]
            result = handler(job)
            ext = EXTENSIONS.get(result.mime, "bin")
            key = f"{company_id}/{job.kind}/{job.id}.{ext}"
            storage.put(key, result.data, result.mime)
            job.result_object_key = key
            job.result_filename = result.filename
            job.result_mime = result.mime
            if result.extra:
                job.params = {**job.params, "result": result.extra}
            job.status = AsyncJob.Status.DONE
            job.progress = 100
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s (%s) fallito", job.id, job.kind)
            job.status = AsyncJob.Status.FAILED
            job.error_code = type(exc).__name__[:60]
        job.finished_at = timezone.now()
        job.save()
    return job.status


@shared_task(name="safe.apps.jobs.cleanup_expired")
def cleanup_expired() -> int:
    """Cancella i file dei job scaduti (beat, giornaliero)."""
    n = 0
    with bypass_tenant():
        for job in AsyncJob.objects.filter(expires_at__lt=timezone.now()).exclude(result_object_key=""):
            storage.delete(job.result_object_key)
            job.result_object_key = ""
            job.save(update_fields=["result_object_key", "updated_at"])
            n += 1
    return n
