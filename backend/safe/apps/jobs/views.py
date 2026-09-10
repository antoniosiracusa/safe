from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission

from . import storage
from .models import AsyncJob


class JobSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()

    class Meta:
        model = AsyncJob
        fields = [
            "id",
            "kind",
            "status",
            "progress",
            "created_at",
            "started_at",
            "finished_at",
            "expires_at",
            "download_url",
            "result_filename",
            "result_mime",
            "error_code",
            "result",
        ]

    def get_download_url(self, job: AsyncJob) -> str | None:
        return (
            f"/api/v1/jobs/{job.id}/download"
            if job.status == AsyncJob.Status.DONE and job.result_object_key
            else None
        )

    def get_result(self, job: AsyncJob) -> dict | None:
        return job.params.get("result")


class JobView(APIView):
    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["jobs"], responses=JobSerializer)
    def get(self, request: Request, pk: str) -> Response:
        job = get_object_or_404(AsyncJob.objects.all(), pk=pk)
        return Response(JobSerializer(job).data)


class JobDownloadView(APIView):
    """Restituisce il file del job (stream dallo storage). Nessun dato personale nel nome file."""

    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["jobs"], responses={200: {"type": "string", "format": "binary"}})
    def get(self, request: Request, pk: str) -> HttpResponse:
        job = get_object_or_404(AsyncJob.objects.all(), pk=pk)
        if job.status != AsyncJob.Status.DONE or not job.result_object_key:
            return Response({"code": "job_not_ready", "detail": "Il job non è completato."}, status=409)
        data = storage.get(job.result_object_key)
        resp = HttpResponse(data, content_type=job.result_mime or "application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{job.result_filename or job.id}"'
        resp["Cache-Control"] = "private, no-store"
        return resp


class JobListView(APIView):
    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["jobs"], responses=JobSerializer(many=True))
    def get(self, request: Request) -> Response:
        kinds = request.query_params.getlist("kind")
        qs = AsyncJob.objects.all()
        if kinds:
            qs = qs.filter(kind__in=kinds)
        return Response(JobSerializer(qs[:100], many=True).data)
