from __future__ import annotations

from safe.apps.jobs.models import AsyncJob
from safe.apps.jobs.runner import JobResult, register
from safe.apps.rescue.models import Event

from . import pdf


@register(AsyncJob.Kind.PDF_REPORT)
def pdf_report(job: AsyncJob) -> JobResult:
    event = Event.objects.select_related("company", "team", "zone", "slope").get(pk=job.params["event_id"])
    who = job.requested_by.email if job.requested_by else "sistema"
    full = job.params.get("variant") == "full"
    data = pdf.render_pdf(
        event,
        job.params.get("lang", "it"),
        downloaded_by=who,
        with_map=job.params.get("with_map", True),
        full=full,
    )
    return JobResult(
        data=data,
        filename=pdf.filename_for(event, full=full),
        mime="application/pdf",
        extra={"event_id": str(event.id), "event_updated_at": event.updated_at.isoformat()},
    )
