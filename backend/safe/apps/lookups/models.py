"""Vocabolari controllati: un'unica tabella con `dimension`, valori globali + valori di società.

"Non classificato" non è una riga: in archivio è NULL, e gli aggregatori lo espongono sempre
come categoria esplicita `unclassified` (docs/02-schema-dati.md §1.4).
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Q

from safe.apps.core.ids import uuid7
from safe.apps.tenancy.context import get_current_company_id, is_bypass
from safe.apps.tenancy.models import Company

UNCLASSIFIED = "unclassified"

DIMENSIONS = (
    "cause",
    "location_type",
    "slope_difficulty",
    "weather",
    "snow_condition",
    "wind",
    "visibility",
    "location_feature",
    "traffic",
    "snow_making",
    "event_type",
    "gender",
    "equipment",
    "equipment_owner",
    "equipment_condition",
    "protection",
    "insurance",
    "accommodation",
    "destination",
    "diagnosis",
    "injury_place",
    "body_part",
    "evacuation_mean",
    "responsibility",
    "person_role",
    "rescue_refusal",
    "team_body",
    "condition",  # condizioni generali dell'assistito (scelta multipla)
    "first_aid",  # primo soccorso prestato (scelta multipla)
)


class LookupQuerySet(models.QuerySet):
    def visible(self) -> LookupQuerySet:
        if is_bypass():
            return self
        company_id = get_current_company_id()
        if company_id is None:
            return self.filter(company_id__isnull=True)
        return self.filter(Q(company_id__isnull=True) | Q(company_id=company_id))

    def active_for_tenant(self) -> LookupQuerySet:
        company_id = get_current_company_id()
        qs = self.visible().filter(is_active=True)
        if company_id is not None:
            qs = qs.exclude(disabled_for__company_id=company_id)
        return qs

    def dimension(self, dimension: str) -> LookupQuerySet:
        return self.filter(dimension=dimension)


class LookupManager(models.Manager.from_queryset(LookupQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> LookupQuerySet:
        return super().get_queryset().visible()


class LookupValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    dimension = models.CharField(max_length=40, choices=[(d, d) for d in DIMENSIONS])
    code = models.SlugField(max_length=60)
    label_it = models.CharField(max_length=120)
    label_en = models.CharField(max_length=120)
    label_de = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    mapping = models.JSONField(default=dict, blank=True)
    color = models.CharField(max_length=9, blank=True, default="")

    objects = LookupManager()
    all_objects = models.Manager.from_queryset(LookupQuerySet)()

    class Meta:
        db_table = "lookup_value"
        base_manager_name = "all_objects"
        ordering = ["dimension", "sort_order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["dimension", "code"],
                condition=Q(company__isnull=True),
                name="ux_lookup_global_dim_code",
            ),
            models.UniqueConstraint(
                fields=["dimension", "code", "company"], name="ux_lookup_company_dim_code"
            ),
            models.CheckConstraint(condition=Q(code__regex=r"^[a-z0-9_]+$"), name="chk_lookup_code"),
        ]
        indexes = [models.Index(fields=["dimension", "sort_order"], name="ix_lookup_dim")]

    def __str__(self) -> str:
        return f"{self.dimension}:{self.code}"

    def label(self, locale: str = "it") -> str:
        return getattr(self, f"label_{locale}", None) or self.label_it

    @property
    def labels(self) -> dict[str, str]:
        return {"it": self.label_it, "en": self.label_en, "de": self.label_de}


class CompanyLookupDisabled(models.Model):
    """Disattiva, per una società, un valore globale."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="+")
    lookup_value = models.ForeignKey(LookupValue, on_delete=models.CASCADE, related_name="disabled_for")

    class Meta:
        db_table = "company_lookup_disabled"
        constraints = [
            models.UniqueConstraint(fields=["company", "lookup_value"], name="pk_company_lookup_disabled")
        ]


def lookup_fk(dimension: str, **kwargs: Any) -> models.ForeignKey:
    """FK verso un valore di una dimensione specifica. La coerenza della dimensione è verificata
    dai serializer (`LookupSlugField`) e da un CHECK a database (migrazione SQL)."""
    kwargs.setdefault("null", True)
    kwargs.setdefault("blank", True)
    kwargs.setdefault("on_delete", models.PROTECT)
    kwargs.setdefault("related_name", "+")
    kwargs.setdefault("limit_choices_to", {"dimension": dimension})
    fk = models.ForeignKey(LookupValue, **kwargs)
    fk.lookup_dimension = dimension  # type: ignore[attr-defined]
    return fk


class Country(models.Model):
    code = models.CharField(max_length=2, primary_key=True)
    name_it = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    name_de = models.CharField(max_length=120)
    is_eu = models.BooleanField(default=False)

    class Meta:
        db_table = "country"
        ordering = ["name_it"]

    def __str__(self) -> str:
        return self.code
