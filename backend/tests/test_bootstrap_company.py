"""bootstrap_company: società, squadra, amministratore (company_admin + key_custodian), invito opzionale."""

from __future__ import annotations

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from safe.apps.authz.models import UserRole
from safe.apps.org.models import AppUser
from safe.apps.tenancy.context import bypass_tenant
from safe.apps.tenancy.models import Company

pytestmark = pytest.mark.django_db


def _run(*extra: str) -> str:
    out = StringIO()
    call_command(
        "bootstrap_company",
        "--name",
        "Società Prova",
        "--slug",
        "prova",
        "--admin-email",
        "Admin@Prova.it",
        "--admin-first-name",
        "Mario",
        "--admin-last-name",
        "Rossi",
        *extra,
        stdout=out,
    )
    return out.getvalue()


def _roles(email: str) -> list[str]:
    with bypass_tenant():
        user = AppUser.all_objects.get(email=email)
        return sorted(UserRole.objects.filter(user=user).values_list("role__code", flat=True))


def test_bootstrap_creates_admin_with_custodian_role() -> None:
    with mock.patch("safe.apps.org.views.send_invite") as invite:
        out = _run()
    invite.assert_not_called()
    assert "creata" in out and "ruoli: company_admin, key_custodian" in out
    with bypass_tenant():
        company = Company.objects.get(slug="prova")
        user = AppUser.all_objects.get(email="admin@prova.it")
    assert user.company_id == company.id
    assert user.status == AppUser.Status.INVITED and user.mfa_required
    assert _roles("admin@prova.it") == ["company_admin", "key_custodian"]

    # idempotente
    out2 = _run()
    assert "esistente" in out2
    assert _roles("admin@prova.it") == ["company_admin", "key_custodian"]


def test_bootstrap_no_custodian_and_invite() -> None:
    with mock.patch("safe.apps.org.views.send_invite") as invite:
        out = _run("--no-custodian", "--invite")
    assert invite.call_count == 1
    assert invite.call_args.args[0].email == "admin@prova.it"
    assert "invito inviato" in out
    assert _roles("admin@prova.it") == ["company_admin"]
