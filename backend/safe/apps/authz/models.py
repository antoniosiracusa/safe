from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from safe.apps.core.ids import uuid7
from safe.apps.tenancy.context import get_current_company_id, is_bypass
from safe.apps.tenancy.models import Company


class Permission(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    module = models.CharField(max_length=32)
    description = models.CharField(max_length=200)
    is_audited = models.BooleanField(default=False)

    class Meta:
        db_table = "permission"
        ordering = ["module", "code"]

    def __str__(self) -> str:
        return self.code


class RoleQuerySet(models.QuerySet):
    def visible(self) -> RoleQuerySet:
        if is_bypass():
            return self
        company_id = get_current_company_id()
        if company_id is None:
            return self.filter(company_id__isnull=True)
        return self.filter(Q(company_id__isnull=True) | Q(company_id=company_id))


class RoleManager(models.Manager.from_queryset(RoleQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> RoleQuerySet:
        return super().get_queryset().visible()


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    code = models.SlugField(max_length=60)
    name_it = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    name_de = models.CharField(max_length=120)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    objects = RoleManager()
    all_objects = models.Manager.from_queryset(RoleQuerySet)()

    class Meta:
        db_table = "role"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["code"], condition=Q(company__isnull=True), name="ux_role_global_code"
            ),
            models.UniqueConstraint(fields=["code", "company"], name="ux_role_company_code"),
        ]

    def __str__(self) -> str:
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")

    class Meta:
        db_table = "role_permission"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="pk_role_permission")]


class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        db_table = "user_role"
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="pk_user_role")]


class UserPermission(models.Model):
    class Effect(models.TextChoices):
        GRANT = "grant", "Concedi"
        DENY = "deny", "Nega"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_permissions"
    )
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")
    effect = models.CharField(max_length=5, choices=Effect.choices)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_permission"
        constraints = [models.UniqueConstraint(fields=["user", "permission"], name="pk_user_permission")]
