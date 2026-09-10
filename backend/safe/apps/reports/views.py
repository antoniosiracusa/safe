"""GET /events/{id}/report.pdf: 200 con il PDF se già generato per l'ultima versione dell'evento,
altrimenti 202 con il job (in test/eager il job è già completo e si risponde 200)."""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authz.drf import HasPermission
from safe.apps.jobs import runner, storage
from safe.apps.jobs.models import AsyncJob
from safe.apps.jobs.views import JobSerializer
from safe.apps.rescue.models import Event
from safe.apps.rescue.views import scope_events


class EventReportView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("reports.pdf",)

    @extend_schema(
        tags=["events"], responses={200: {"type": "string", "format": "binary"}, 202: JobSerializer}
    )
    def get(self, request: Request, pk: str) -> HttpResponse:
        event = get_object_or_404(
            scope_events(Event.objects.filter(deleted_at__isnull=True), request.user), pk=pk
        )
        lang = request.query_params.get("lang") or getattr(request.user, "locale", "it")
        cached = (
            AsyncJob.objects.filter(
                kind=AsyncJob.Kind.PDF_REPORT,
                status=AsyncJob.Status.DONE,
                params__event_id=str(event.id),
                params__lang=lang,
                params__result__event_updated_at=event.updated_at.isoformat(),
            )
            .exclude(result_object_key="")
            .order_by("-created_at")
            .first()
        )
        job = cached
        if job is None:
            job = runner.enqueue(
                company_id=event.company_id,
                user=request.user,
                kind=AsyncJob.Kind.PDF_REPORT,
                params={"event_id": str(event.id), "lang": lang},
                expires_days=30,
            )
        audit.record(
            "report.pdf",
            "event",
            object_id=event.id,
            event_id=event.id,
            request=request,
            metadata={"job_id": str(job.id), "cached": cached is not None},
        )
        if job.status == AsyncJob.Status.DONE and storage.exists(job.result_object_key):
            resp = HttpResponse(storage.get(job.result_object_key), content_type="application/pdf")
            resp["Content-Disposition"] = f'attachment; filename="{job.result_filename}"'
            resp["Cache-Control"] = "private, no-store"
            return resp
        return Response(JobSerializer(job).data, status=202)
