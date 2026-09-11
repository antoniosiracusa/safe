from celery import shared_task

from safe.apps.tenancy.context import bypass_tenant, tenant_context

from . import services


@shared_task(name="safe.apps.rescue.auto_lock_events")
def auto_lock_events() -> int:
    """Blocca gli eventi scaduti (auto_lock_hours per società). Eseguito dal beat ogni 15 minuti."""
    with bypass_tenant():
        return services.auto_lock_due_events()


@shared_task(name="safe.apps.rescue.recompute_validity")
def recompute_validity(company_id: str) -> int:
    """Ricalcola la validità di tutti gli eventi della società (dopo un cambio delle regole)."""
    import uuid

    from .models import Event

    n = 0
    with tenant_context(uuid.UUID(company_id)):
        for ev in Event.objects.filter(deleted_at__isnull=True).iterator(chunk_size=1000):
            services.compute_event_validity(ev)
            n += 1
    return n


@shared_task(name="safe.apps.rescue.retention_run")
def retention_run() -> dict[str, int]:
    """Anonimizzazione periodica (beat, giornaliera) per tutte le società attive."""
    from safe.apps.tenancy.models import Company

    from . import retention

    totals = {"persons_anonymized": 0, "audit_rows_purged": 0}
    with bypass_tenant():
        companies = list(Company.objects.filter(is_active=True))
    for company in companies:
        with tenant_context(company.id):
            res = retention.run_for_company(company)
        for k in totals:
            totals[k] += res[k]
    return totals


def _register_anonymize_job() -> None:
    import json

    from safe.apps.jobs.models import AsyncJob
    from safe.apps.jobs.runner import JobResult, register

    @register(AsyncJob.Kind.ANONYMIZE)
    def anonymize_job(job: AsyncJob) -> JobResult:
        from . import retention

        res = retention.run_for_company(job.company, actor=job.requested_by)
        data = json.dumps(res).encode()
        return JobResult(data=data, filename="retention-run.json", mime="application/json", extra=res)


_register_anonymize_job()
