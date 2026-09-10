from __future__ import annotations

from django.conf import settings
from django.db import models

from safe.apps.tenancy.models import TenantModel


class DeviceEnrollmentCode(TenantModel):
    code_hash = models.CharField(max_length=64, unique=True)  # SHA-256 del codice nel QR
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by_device = models.ForeignKey(
        "MobileDevice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta(TenantModel.Meta):
        db_table = "device_enrollment_code"


class MobileDevice(TenantModel):
    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    class Status(models.TextChoices):
        PENDING = "pending", "In attesa"
        AUTHORIZED = "authorized", "Autorizzato"
        REVOKED = "revoked", "Revocato"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    install_id = models.CharField(max_length=128)
    name = models.CharField(max_length=120)
    platform = models.CharField(max_length=8, choices=Platform.choices)
    os_version = models.CharField(max_length=40, blank=True, default="")
    app_version = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "mobile_device"
        constraints = [models.UniqueConstraint(fields=["company", "install_id"], name="ux_device_install")]
        indexes = [models.Index(fields=["company", "status"], name="ix_device_company_status")]

    def __str__(self) -> str:
        return self.name
