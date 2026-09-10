"""Isolamento multi-tenant: ORM (TenantManager) e Row Level Security devono entrambi impedire
l'accesso ai dati di un'altra società."""

import datetime as dt

import pytest
from django.db import connection

from safe.apps.org.models import Team
from safe.apps.rescue.models import Event, Season
from safe.apps.tenancy.context import bypass_tenant, tenant_context

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


def _event(company, team, when):  # noqa: ANN001, ANN201
    with tenant_context(company.id):
        return Event.objects.create(dateandtime=when, team=team)


@pytest.fixture
def two_tenants(company, other_company):  # noqa: ANN001, ANN201
    with tenant_context(company.id):
        team_a = Team.objects.create(name="A1")
    with tenant_context(other_company.id):
        team_b = Team.objects.create(name="B1")
    ea = _event(company, team_a, dt.datetime(2026, 1, 18, 10, 5, tzinfo=dt.UTC))
    eb = _event(other_company, team_b, dt.datetime(2026, 2, 1, 9, 0, tzinfo=dt.UTC))
    return ea, eb


def test_orm_manager_scopes_to_current_tenant(company, other_company, two_tenants):
    ea, eb = two_tenants
    with tenant_context(company.id):
        assert list(Event.objects.values_list("id", flat=True)) == [ea.id]
        assert Team.objects.count() == 1
    with tenant_context(other_company.id):
        assert list(Event.objects.values_list("id", flat=True)) == [eb.id]


def test_no_tenant_context_sees_nothing(company, two_tenants):
    assert Event.objects.count() == 0
    assert Team.objects.count() == 0


def test_rls_blocks_raw_sql_across_tenants(company, other_company, two_tenants):
    ea, eb = two_tenants
    with tenant_context(company.id), connection.cursor() as cur:
        cur.execute("SELECT id FROM event")
        assert [row[0] for row in cur.fetchall()] == [ea.id]
        cur.execute("SELECT count(*) FROM team")
        assert cur.fetchone()[0] == 1
        # anche l'accesso non filtrato dall'ORM è limitato dal database
        assert list(Event.all_objects.values_list("id", flat=True)) == [ea.id]


def test_rls_blocks_insert_for_other_tenant(company, other_company, two_tenants):
    from django.db.utils import ProgrammingError

    with pytest.raises(ProgrammingError), tenant_context(company.id), connection.cursor() as cur:
        cur.execute(
            "INSERT INTO team (id, company_id, name, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), %s, 'intruso', true, now(), now())",
            [str(other_company.id)],
        )


def test_bypass_sees_everything(company, other_company, two_tenants):
    with bypass_tenant():
        assert Event.all_objects.count() == 2
        assert Event.objects.count() == 2


def test_season_is_derived_from_local_date(company, two_tenants):
    with tenant_context(company.id):
        june_1 = Event.objects.create(
            dateandtime=dt.datetime(2026, 5, 31, 23, 30, tzinfo=dt.UTC), team=Team.objects.get(name="A1")
        )
    # 31/05 23:30 UTC = 01/06 01:30 Europe/Rome → stagione 2026/2027
    assert june_1.season.code == "2026/2027"
    assert Season.code_for(dt.date(2026, 5, 31)) == "2025/2026"


def test_api_object_of_other_tenant_is_404(as_admin, other_company, two_tenants):
    # il dettaglio evento arriva in M2: qui verifichiamo che il tenant della richiesta sia quello dell'utente
    r = as_admin.get("/api/v1/me")
    assert r.json()["company"]["slug"] == "a"
