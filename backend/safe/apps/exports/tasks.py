from __future__ import annotations

from safe.apps.jobs.models import AsyncJob, ExportRun
from safe.apps.jobs.runner import JobResult, register
from safe.apps.territory.models import IstatAdminUnit

from . import dataset, regional


@register(AsyncJob.Kind.EXPORT_DATASET)
def export_dataset(job: AsyncJob) -> JobResult:
    p = job.params
    data, name, mime = dataset.build(
        p["dataset"],
        p["format"],
        p.get("filters", {}),
        job.requested_by,
        p.get("lang", "it"),
        job.company.timezone,
    )
    ExportRun.objects.update_or_create(
        job=job,
        defaults={
            "template_code": f"dataset_{p['dataset']}",
            "format": p["format"],
            "filters": p.get("filters", {}),
            "row_count": data.count(b"\n") if p["format"] == "csv" else None,
        },
    )
    return JobResult(data=data, filename=name, mime=mime)


@register(AsyncJob.Kind.EXPORT_REGIONAL)
def export_regional(job: AsyncJob) -> JobResult:
    p = job.params
    area = None
    if p.get("administrative_area"):
        area = (
            IstatAdminUnit.objects.filter(
                level=p["administrative_area"]["level"], code=p["administrative_area"]["code"]
            )
            .order_by("-edition_year")
            .first()
        )
    sel = regional.select(
        job.requested_by,
        p["season"],
        area,
        p.get("team"),
        exclude_buildings=p.get("exclude_in_buildings", True),
        merge_duplicates=p.get("merge_duplicates", True),
    )
    tz = job.company.timezone
    fmt = p.get("format", "xlsx")
    data = (
        regional.build_xls(sel, job.company.name, tz)
        if fmt == "xls"
        else regional.build_xlsx(sel, job.company.name, tz)
    )
    mime = (
        "application/vnd.ms-excel"
        if fmt == "xls"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    pv = regional.preview(sel)
    ExportRun.objects.update_or_create(
        job=job,
        defaults={
            "template_code": regional.TEMPLATE,
            "format": fmt,
            "filters": {"season": p["season"], "team": p.get("team")},
            "administrative_area_code": area.code if area else "",
            "quality_preview": pv,
            "row_count": pv["exportable_persons"],
        },
    )
    return JobResult(data=data, filename=regional.filename(sel, fmt), mime=mime, extra={"preview": pv})
