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
