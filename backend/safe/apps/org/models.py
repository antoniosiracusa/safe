from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from safe.apps.lookups.models import lookup_fk
from safe.apps.tenancy.models import TenantManager, TenantModel, UnscopedManager


class Team(TenantModel):
    name = models.CharField(max_length=120)
    body = lookup_fk("team_body")
    is_active = models.BooleanField(default=True)

    class Meta(TenantModel.Meta):
        db_table = "team"
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="ux_team_company_name")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AppUserManager(TenantManager):
    def get_by_natural_key(self, email: str):  # noqa: ANN201
        return self.get(email__iexact=email)


class AppUser(AbstractBaseUser, TenantModel):
    """Utente applicativo. L'identità (password, MFA) è in Keycloak: `password` resta inutilizzabile."""

    class Status(models.TextChoices):
        INVITED = "invited", "Invitato"
        ACTIVE = "active", "Attivo"
        DISABLED = "disabled", "Disattivato"

    oidc_subject = models.CharField(max_length=255, unique=True, null=True, blank=True)
    keycloak_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120, blank=True, default="")
    locale = models.CharField(max_length=5, default="it")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INVITED)
    is_platform_admin = models.BooleanField(default=False)
    mfa_required = models.BooleanField(default=False)
    invited_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    activated_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    teams = models.ManyToManyField(Team, through="UserTeam", related_name="users")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = AppUserManager()
    all_objects = UnscopedManager()

    class Meta(TenantModel.Meta):
        db_table = "app_user"
        indexes = [models.Index(fields=["company", "status"], name="ix_user_company_status")]

    def __str__(self) -> str:
        return self.email

    @property
    def is_active(self) -> bool:  # usato da Django auth
        return self.status == self.Status.ACTIVE

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def set_password(self, raw_password: str | None) -> None:  # pragma: no cover - mai usato
        self.set_unusable_password()


class UserTeam(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name="user_teams")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="user_teams")
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "user_team"
        constraints = [models.UniqueConstraint(fields=["user", "team"], name="pk_user_team")]
