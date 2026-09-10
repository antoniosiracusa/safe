from __future__ import annotations

from django.contrib.gis.db import models as gis
from django.db import models

from safe.apps.core.ids import uuid7
from safe.apps.lookups.models import lookup_fk
from safe.apps.tenancy.models import TenantModel


class SkiArea(TenantModel):
    name = models.CharField(max_length=120)
    regional_code = models.CharField(max_length=40, blank=True, default="")
    boundary = gis.MultiPolygonField(srid=4326, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        db_table = "ski_area"
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="ux_ski_area_company_name")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Zone(TenantModel):
    ski_area = models.ForeignKey(SkiArea, on_delete=models.CASCADE, related_name="zones")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        db_table = "zone"
        constraints = [models.UniqueConstraint(fields=["ski_area", "name"], name="ux_zone_area_name")]
        indexes = [models.Index(fields=["company", "ski_area"], name="ix_zone_company_area")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Slope(TenantModel):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="slopes")
    name = models.CharField(max_length=120)
    regional_code = models.CharField(max_length=40, blank=True, default="")  # es. 'C.1.24' (tracciato A01)
    difficulty = lookup_fk("slope_difficulty")
    geom = gis.MultiLineStringField(srid=4326, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        db_table = "slope"
        constraints = [models.UniqueConstraint(fields=["zone", "name"], name="ux_slope_zone_name")]
        indexes = [models.Index(fields=["company", "zone"], name="ix_slope_company_zone")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Lift(TenantModel):
    ski_area = models.ForeignKey(SkiArea, on_delete=models.CASCADE, related_name="lifts")
    name = models.CharField(max_length=120)
    lift_type = models.CharField(max_length=40, blank=True, default="")
    geom = gis.LineStringField(srid=4326, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        db_table = "lift"
        ordering = ["name"]


class IstatAdminUnit(models.Model):
    """Confini amministrativi ISTAT (regione, provincia, comune). Tabella globale."""

    class Level(models.TextChoices):
        REGION = "region", "Regione"
        PROVINCE = "province", "Provincia"
        MUNICIPALITY = "municipality", "Comune"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    level = models.CharField(max_length=12, choices=Level.choices)
    code = models.CharField(max_length=12)
    name = models.CharField(max_length=120)
    parent_code = models.CharField(max_length=12, blank=True, default="")
    edition_year = models.PositiveSmallIntegerField()
    geom = gis.MultiPolygonField(srid=4326)

    class Meta:
        db_table = "istat_admin_unit"
        constraints = [
            models.UniqueConstraint(fields=["level", "code", "edition_year"], name="ux_istat_unit")
        ]

    def __str__(self) -> str:
        return f"{self.level}:{self.code} {self.name}"
