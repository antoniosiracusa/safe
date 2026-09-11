"""Matrice permessi: ogni rotta dichiarata risponde 403 (senza dati) a un utente che ha TUTTI
gli altri permessi tranne quelli richiesti. La lista cresce con le milestone."""

import pytest

from safe.apps.authz.catalog import ALL_CODES

from . import factories as f
from .conftest import auth, create_user

pytestmark = [pytest.mark.django_db, pytest.mark.authz]

ROUTES = [
    ("get", "/api/v1/events", ("events.view",)),
    ("post", "/api/v1/events", ("events.create",)),
    ("get", "/api/v1/events/{event}", ("events.view",)),
    ("patch", "/api/v1/events/{event}", ("events.edit",)),
    ("delete", "/api/v1/events/{event}", ("events.delete",)),
    ("post", "/api/v1/events/{event}/lock", ("events.edit",)),
    ("post", "/api/v1/events/{event}/unlock", ("events.unlock",)),
    ("get", "/api/v1/events/{event}/persons", ("events.view", "persons.view")),
    ("post", "/api/v1/events/{event}/persons", ("events.view", "persons.edit")),
    ("get", "/api/v1/persons", ("persons.view",)),
    ("get", "/api/v1/persons/{person}", ("persons.view",)),
    ("patch", "/api/v1/persons/{person}", ("persons.edit",)),
    ("delete", "/api/v1/persons/{person}", ("persons.edit",)),
    ("get", "/api/v1/persons/{person}/identity", ("persons.reveal_identity",)),
    ("get", "/api/v1/ski-areas", ("territory.view",)),
    ("get", "/api/v1/zones", ("territory.view",)),
    ("get", "/api/v1/slopes", ("territory.view",)),
    ("get", "/api/v1/stats/typology/cause", ("stats.view",)),
    ("get", "/api/v1/stats/demographics/age-gender", ("stats.view",)),
    ("get", "/api/v1/stats/geography/slopes", ("stats.view",)),
    ("get", "/api/v1/stats/season-summary/teams", ("stats.view", "stats.advanced")),
    ("get", "/api/v1/map/events.geojson", ("map.view",)),
    ("get", "/api/v1/map/ski-areas.geojson", ("map.view",)),
    ("get", "/api/v1/map/styles", ("map.view",)),
    ("get", "/api/v1/events/{event}/report.pdf", ("reports.pdf",)),
    ("post", "/api/v1/exports/dataset", ("exports.dataset",)),
    ("post", "/api/v1/exports/regional/preview", ("exports.regional",)),
    ("post", "/api/v1/exports/regional", ("exports.regional",)),
    ("get", "/api/v1/exports", ("exports.dataset",)),
    ("get", "/api/v1/exports/administrative-areas", ("exports.regional",)),
    ("get", "/api/v1/users", ("users.view",)),
    ("post", "/api/v1/users/invite", ("users.invite",)),
    ("get", "/api/v1/roles", ("users.view",)),
    ("post", "/api/v1/roles", ("users.assign_permissions",)),
    ("get", "/api/v1/teams", ("teams.view",)),
    ("post", "/api/v1/teams", ("teams.manage",)),
    ("get", "/api/v1/devices", ("devices.view",)),
    ("post", "/api/v1/devices/enrollment-code", ("devices.manage",)),
    ("post", "/api/v1/ski-areas", ("territory.manage",)),
    ("post", "/api/v1/zones", ("territory.manage",)),
    ("post", "/api/v1/slopes", ("territory.manage",)),
    ("get", "/api/v1/lifts", ("territory.view",)),
    ("get", "/api/v1/lookups/cause", ("lookups.manage",)),
    ("patch", "/api/v1/company", ("company.settings",)),
    ("get", "/api/v1/company/retention", ("company.retention",)),
    ("post", "/api/v1/company/retention/run", ("company.retention",)),
    ("post", "/api/v1/persons/{person}/anonymize", ("company.retention",)),
    ("get", "/api/v1/crypto/company-key", ("persons.edit",)),
    ("post", "/api/v1/crypto/company-key", ("crypto.manage_keys",)),
    ("post", "/api/v1/crypto/company-key/rotate", ("crypto.manage_keys",)),
    ("get", "/api/v1/crypto/grants", ("crypto.manage_keys",)),
    ("get", "/api/v1/crypto/recovery", ("crypto.recovery",)),
    ("get", "/api/v1/audit-logs", ("audit.view",)),
    ("get", "/api/v1/audit-logs/export", ("audit.view",)),
]


@pytest.fixture
def objects(company, team, tenant):  # noqa: ANN001, ANN201
    ev = f.event(team)
    p = f.person(ev)
    return {"event": ev.id, "person": p.id}


@pytest.mark.parametrize(("method", "path", "required"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_route_denied_without_required_permissions(
    api_client, company, team, objects, method, path, required
):
    for missing in required:
        # utente con tutti i permessi tranne `missing`
        grants = tuple(c for c in ALL_CODES if c != missing)
        user = create_user(company, f"m-{missing}-{method}@a.test", grants=grants, team=team)
        client = auth(api_client, user)
        url = path.format(**objects)
        r = getattr(client, method)(url, {}, format="json")
        assert r.status_code == 403, (missing, method, url, r.status_code, r.content[:200])
        body = r.json()
        assert body["code"] == "permission_denied" and missing in body["missing"]
        assert set(body.keys()) <= {"code", "detail", "missing"}
