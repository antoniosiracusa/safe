from __future__ import annotations

from django.conf import settings
from django.db import models

from safe.apps.tenancy.models import TenantModel


class AsyncJob(TenantModel):
    class Kind(models.TextChoices):
        PDF_REPORT = "pdf_report", "PDF rapporto"
        EXPORT_DATASET = "export_dataset", "Export dataset"
        EXPORT_REGIONAL = "export_regional", "Export regionale"
        IMPORT_HISTORICAL = "import_historical", "Import storico"
        REBUILD_TILES = "rebuild_tiles", "Rigenerazione tile"
        ANONYMIZE = "anonymize", "Anonimizzazione"
        REENCRYPT = "reencrypt", "Ri-cifratura"

    class Status(models.TextChoices):
        QUEUED = "queued", "In coda"
        RUNNING = "running", "In esecuzione"
        DONE = "done", "Completato"
        FAILED = "failed", "Fallito"
        CANCELLED = "cancelled", "Annullato"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    params = models.JSONField(default=dict, blank=True)  # mai dati personali
    progress = models.PositiveSmallIntegerField(default=0)
    result_object_key = models.CharField(max_length=300, blank=True, default="")
    result_filename = models.CharField(max_length=200, blank=True, default="")
    result_mime = models.CharField(max_length=100, blank=True, default="")
    error_code = models.CharField(max_length=60, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "async_job"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status", "-created_at"], name="ix_job_company_status")]


class ExportRun(TenantModel):
    class Format(models.TextChoices):
        XLSX = "xlsx", "XLSX"
        XLS = "xls", "XLS"
        CSV = "csv", "CSV"
        PDF = "pdf", "PDF"

    job = models.OneToOneField(AsyncJob, on_delete=models.CASCADE, related_name="export_run")
    template_code = models.CharField(max_length=40)
    format = models.CharField(max_length=4, choices=Format.choices)
    filters = models.JSONField(default=dict)
    administrative_area_code = models.CharField(max_length=12, blank=True, default="")
    quality_preview = models.JSONField(null=True, blank=True)
    row_count = models.IntegerField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "export_run"
