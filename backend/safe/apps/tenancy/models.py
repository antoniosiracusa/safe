from __future__ import annotations

from typing import Any

from django.db import models

from safe.apps.core.ids import uuid7

from .context import get_current_company_id, is_bypass


class Company(models.Model):
    """Il tenant. Non è un TenantModel: la riga visibile è quella del tenant corrente (policy RLS)."""

    class TenantType(models.TextChoices):
        COMPANY = "company", "Società di gestione"
        AUTHORITY = "authority", "Ente pubblico"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    tenant_type = models.CharField(max_length=16, choices=TenantType.choices, default=TenantType.COMPANY)
    timezone = models.CharField(max_length=64, default="Europe/Rome")
    default_locale = models.CharField(max_length=5, default="it")
    settings = models.JSONField(default=dict, blank=True)
    retention_identity_years = models.PositiveSmallIntegerField(default=10)
    retention_audit_years = models.PositiveSmallIntegerField(default=10)
    data_version = models.BigIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company"
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name

    # --- impostazioni con default (docs/03-openapi.yaml CompanySettings) -------------
    @property
    def first_season(self) -> str | None:
        """Prima stagione mostrata nei filtri/statistiche ('2025/2026'); None = tutte le stagioni."""
        return self.settings.get("first_season") or None

    @property
    def auto_lock_hours(self) -> int:
        return int(self.settings.get("auto_lock_hours", 48))

    @property
    def devices_need_authorization(self) -> bool:
        return bool(self.settings.get("devices_need_authorization", True))

    @property
    def validity_rules(self) -> dict[str, list[str]]:
        rules = self.settings.get("validity_rules", {})
        return {
            "event_required": rules.get(
                "event_required", ["dateandtime", "zone", "location", "cause", "geometry"]
            ),
            "person_required": rules.get(
                "person_required", ["age", "gender", "diagnosis", "evacuation_means"]
            ),
        }

    @property
    def duplicate_rule(self) -> dict[str, Any]:
        rule = self.settings.get("duplicate_rule", {})
        return {
            "minutes": int(rule.get("minutes", 30)),
            "fields": rule.get("fields", ["date", "slope", "gender", "age_class_a01", "equipment"]),
        }


class TenantQuerySet(models.QuerySet):
    def for_current_tenant(self) -> TenantQuerySet:
        if is_bypass():
            return self
        company_id = get_current_company_id()
        if company_id is None:
            return self.none()
        return self.filter(company_id=company_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Manager di default: sempre filtrato sul tenant corrente (o vuoto se nessun tenant)."""

    def get_queryset(self) -> TenantQuerySet:
        return super().get_queryset().for_current_tenant()


class UnscopedManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Accesso non filtrato: solo per migrazioni, comandi di piattaforma e test. RLS resta attiva."""


class TenantModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = UnscopedManager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # company_id imposto dal contesto server, mai dal client
        if self.company_id is None:
            current = get_current_company_id()
            if current is None:
                raise RuntimeError("Nessun tenant nel contesto: impossibile salvare un oggetto tenant.")
            self.company_id = current
        super().save(*args, **kwargs)
