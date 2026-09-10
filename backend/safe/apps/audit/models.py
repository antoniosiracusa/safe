"""Audit log append-only: solo identificativi e nomi di campo, mai valori di dati personali.
Il partizionamento mensile e la revoca di UPDATE/DELETE al ruolo applicativo sono applicati in M7."""

from __future__ import annotations

from django.db import models

from safe.apps.tenancy.context import get_current_company_id, is_bypass


class AuditQuerySet(models.QuerySet):
    def for_current_tenant(self) -> AuditQuerySet:
        if is_bypass():
            return self
        company_id = get_current_company_id()
        return self.filter(company_id=company_id) if company_id else self.none()


class AuditManager(models.Manager.from_queryset(AuditQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> AuditQuerySet:
        return super().get_queryset().for_current_tenant()


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    company_id = models.UUIDField()
    actor_user_id = models.UUIDField(null=True, blank=True)
    actor_device_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=60)  # 'person.identity_read', 'event.unlock', ...
    object_type = models.CharField(max_length=40)
    object_id = models.UUIDField(null=True, blank=True)
    event_id = models.UUIDField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditManager()
    all_objects = models.Manager.from_queryset(AuditQuerySet)()

    class Meta:
        db_table = "audit_log"
        base_manager_name = "all_objects"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "-created_at"], name="ix_audit_company_time"),
            models.Index(fields=["company_id", "object_type", "object_id"], name="ix_audit_object"),
        ]
