"""Chiavi per la cifratura end-to-end (docs/01-architettura.md §7). Il server conserva solo
chiavi pubbliche e chiavi private cifrate: non è mai in grado di decifrare."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from safe.apps.tenancy.models import TenantModel


class UserKey(TenantModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="key")
    algorithm = models.CharField(max_length=40, default="x25519-v1")
    public_key = models.BinaryField()
    private_key_encrypted = models.BinaryField()  # secretbox(privkey, Argon2id(passphrase))
    kdf_params = models.JSONField()
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "user_key"


class CompanyKey(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Attiva"
        RETIRED = "retired", "Ritirata"

    version = models.PositiveIntegerField()
    algorithm = models.CharField(max_length=40, default="x25519-sealedbox-v1")
    public_key = models.BinaryField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "company_key"
        constraints = [
            models.UniqueConstraint(fields=["company", "version"], name="ux_company_key_version"),
            models.UniqueConstraint(
                fields=["company"], condition=Q(status="active"), name="ux_company_key_active"
            ),
        ]


class CompanyKeyGrant(TenantModel):
    company_key = models.ForeignKey(CompanyKey, on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="key_grants")
    wrapped_private_key = models.BinaryField()  # sealed box verso user_key.public_key
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta(TenantModel.Meta):
        db_table = "company_key_grant"
        constraints = [
            models.UniqueConstraint(
                fields=["company_key", "user"], condition=Q(revoked_at__isnull=True), name="ux_grant_active"
            ),
        ]


class CompanyKeyRecovery(TenantModel):
    class Method(models.TextChoices):
        RECOVERY_CODE = "recovery_code", "Codice di recupero"
        SHAMIR_SHARE = "shamir_share", "Frazione Shamir"

    company_key = models.ForeignKey(CompanyKey, on_delete=models.CASCADE, related_name="recoveries")
    method = models.CharField(max_length=16, choices=Method.choices)
    share_index = models.PositiveSmallIntegerField(null=True, blank=True)
    share_threshold = models.PositiveSmallIntegerField(null=True, blank=True)
    encrypted_private_key = models.BinaryField()
    kdf_params = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "company_key_recovery"
