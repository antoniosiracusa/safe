from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "safe.apps.audit"
    label = "audit"
    verbose_name = "SAFE audit log"
