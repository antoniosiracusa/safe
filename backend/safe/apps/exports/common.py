"""Utilità comuni agli export: etichette, classi di età, scrittura CSV/XLSX/XLS."""

from __future__ import annotations

import csv
import io
import zoneinfo
from typing import Any

from safe.apps.lookups.models import LookupValue
from safe.apps.stats.chart import AGE_CLUSTERS

UNCLASSIFIED = {"it": "Non classificato", "en": "Unclassified", "de": "Nicht klassifiziert"}


def age_class(age: int | None, cluster: str = "standard") -> str | None:
    if age is None:
        return None
    for upper, label in AGE_CLUSTERS[cluster]:
        if upper is None or age <= upper:
            return label
    return None


class Labels:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in ("it", "en", "de") else "it"
        self.values = {(v.dimension, v.code): v for v in LookupValue.objects.active_for_tenant()}

    def of(self, obj: LookupValue | None) -> str:
        return obj.label(self.lang) if obj else UNCLASSIFIED[self.lang]

    def yesno(self, v: bool | None) -> str:
        if v is None:
            return UNCLASSIFIED[self.lang]
        return {"it": ("Sì", "No"), "en": ("Yes", "No"), "de": ("Ja", "Nein")}[self.lang][0 if v else 1]

    def mapping(self, obj: LookupValue | None, template: str, default: str = "Altro") -> str:
        return (obj.mapping.get(template) if obj else None) or default


def local(dt, tz: str):  # noqa: ANN001, ANN201
    return dt.astimezone(zoneinfo.ZoneInfo(tz))


def write_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(headers)
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def write_xlsx(headers: list[str], rows: list[list[Any]], *, sheet: str = "Dati") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = sheet[:31]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDE6F0")
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, start=1):
        width = (
            max(
                len(str(h)),
                *(len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r) and r[i - 1] is not None),
            )
            if rows
            else len(str(h))
        )
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 50)
    ws.auto_filter.ref = ws.dimensions
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
