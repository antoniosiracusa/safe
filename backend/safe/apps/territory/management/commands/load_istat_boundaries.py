"""Carica i confini amministrativi ISTAT (regioni, province, comuni) in `istat_admin_unit`.

    python manage.py load_istat_boundaries --zip Limiti01012025_g.zip --year 2025
    python manage.py load_istat_boundaries --year 2025 \
        --url https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2025/Limiti01012025_g.zip

Lo zip ISTAT contiene tre shapefile (Reg…, ProvCM…, Com…) in EPSG:32632; le geometrie vengono
riproiettate in WGS84. Tabella globale (nessun tenant), aggiornamento annuale.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import requests
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from safe.apps.territory.models import IstatAdminUnit

LAYERS = (
    ("Reg", "region", ("COD_REG",), ("DEN_REG",), None),
    ("ProvCM", "province", ("COD_PROV", "COD_UTS"), ("DEN_UTS", "DEN_PROV", "DEN_CM"), "COD_REG"),
    ("Com", "municipality", ("PRO_COM_T", "PRO_COM"), ("COMUNE",), "COD_PROV"),
)


def _get(feat, names):  # noqa: ANN001, ANN201
    for n in names:
        if n in feat.fields:
            return feat.get(n)
    return None


class Command(BaseCommand):
    help = "Carica i confini amministrativi ISTAT"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--zip", help="percorso dello zip ISTAT")
        parser.add_argument("--url", help="URL dello zip ISTAT")
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--levels", default="region,province,municipality")

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        levels = set(options["levels"].split(","))
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(options["zip"]) if options.get("zip") else Path(tmp) / "istat.zip"
            if options.get("url"):
                self.stdout.write(f"scarico {options['url']} …")
                with requests.get(options["url"], stream=True, timeout=600) as r:
                    r.raise_for_status()
                    with open(zpath, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
            with zipfile.ZipFile(zpath) as z:
                z.extractall(tmp)
            shapefiles = list(Path(tmp).rglob("*.shp"))
            total = 0
            for prefix, level, code_fields, name_fields, parent_field in LAYERS:
                if level not in levels:
                    continue
                shp = next((s for s in shapefiles if s.name.startswith(prefix)), None)
                if shp is None:
                    self.stderr.write(f"shapefile {prefix}* non trovato")
                    continue
                layer = DataSource(str(shp))[0]
                rows = []
                for feat in layer:
                    g = GEOSGeometry(feat.geom.wkt, srid=layer.srs.srid or 32632)
                    g.transform(4326)
                    geom = MultiPolygon(g) if isinstance(g, Polygon) else g
                    assert isinstance(geom, MultiPolygon)
                    code = _get(feat, code_fields)
                    rows.append(
                        IstatAdminUnit(
                            level=level,
                            code=str(int(code)) if isinstance(code, float) else str(code),
                            name=str(_get(feat, name_fields) or ""),
                            parent_code=str(_get(feat, (parent_field,)) or "") if parent_field else "",
                            edition_year=options["year"],
                            geom=geom,
                        )
                    )
                with transaction.atomic():
                    IstatAdminUnit.objects.filter(level=level, edition_year=options["year"]).delete()
                    IstatAdminUnit.objects.bulk_create(rows, batch_size=500)
                self.stdout.write(f"  {level}: {len(rows)} unità")
                total += len(rows)
        self.stdout.write(self.style.SUCCESS(f"Caricate {total} unità amministrative ({options['year']})"))
