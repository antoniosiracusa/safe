from celery import shared_task

from safe.apps.tenancy.context import bypass_tenant

from . import services


@shared_task(name="safe.apps.rescue.auto_lock_events")
def auto_lock_events() -> int:
    """Blocca gli eventi scaduti (auto_lock_hours per società). Eseguito dal beat ogni 15 minuti."""
    with bypass_tenant():
        return services.auto_lock_due_events()
