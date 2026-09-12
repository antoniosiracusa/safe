import datetime as dt

import pytest

from safe.apps.audit.models import AuditLog
from safe.apps.org.models import Team
from safe.apps.rescue.models import Event
from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(company, team):  # noqa: ANN001, ANN201
    with tenant_context(company.id):
        area, zone, slope = f.territory()
        e1 = f.event(team)
        f.person(e1)
        e2 = f.event(team, when=dt.datetime(2025, 2, 1, 9, 0, tzinfo=dt.UTC), complete=False)
        return {"area": area, "zone": zone, "slope": slope, "e1": e1, "e2": e2}


def test_list_events_with_season_filter(as_admin, seeded):
    r = as_admin.get("/api/v1/events?season=2025/2026")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    ev = body["results"][0]
    assert ev["id"] == str(seeded["e1"].id)
    assert ev["season"] == "2025/2026"
    assert ev["slope"]["regional_code"] == "C.1.24"
    assert ev["cause"] == "collision_person"
    assert ev["persons_count"] == 1
    assert ev["has_geometry"] is True
    assert "geometry" not in ev  # solo nel dettaglio


def test_detail_event_with_persons_pseudonymized(as_admin, seeded):
    r = as_admin.get(f"/api/v1/events/{seeded['e1'].id}")
    assert r.status_code == 200
    body = r.json()
    assert body["geometry"] == {"type": "Point", "coordinates": [12.0912, 46.4581]}
    p = body["persons"][0]
    assert p["initials_surname"] == "C" and p["age"] == 26 and p["age_class"] == "25-34"
    assert p["evacuation_means"] == [{"mean": "akja", "order": 1}]
    assert p["has_identity"] is False
    assert "firstname" not in p and "surname" not in p and "pii_ciphertext" not in p


def test_create_event_computes_validity_and_is_idempotent(as_admin, seeded, team):
    payload = {
        "client_uuid": "5f1c3a9e-1111-4222-8333-444455556666",
        "dateandtime": "2026-01-20T09:30:00Z",
        "team": str(team.id),
        "zone": str(seeded["zone"].id),
        "slope": str(seeded["slope"].id),
        "cause": "accidental_fall",
        "weather": "snow",
        "geometry": {"type": "Point", "coordinates": [12.09, 46.45]},
        "extended": {
            "caller": "MAESTRO DI SCI",
            "call_received_at": "11:02:00",
            "operators": [{"name": "G. Ben"}],
        },
    }
    r = as_admin.post("/api/v1/events", payload, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["season"] == "2025/2026"
    assert body["ski_area"]["name"] == "Civetta"  # derivato dalla zona
    assert body["difficulty"] == "blue"  # derivato dalla pista
    assert body["valid"] is True
    assert body["fully_valid"] is False  # nessuna persona
    assert {"field": "persons", "code": "required"} in body["validation_errors"]
    assert body["extended"]["caller"] == "MAESTRO DI SCI"
    assert body["extended"]["operators"] == [{"user_id": None, "name": "G. Ben"}]
    # stessa client_uuid → 200 con lo stesso oggetto
    r2 = as_admin.post("/api/v1/events", payload, format="json")
    assert r2.status_code == 200 and r2.json()["id"] == body["id"]


def test_create_event_rejects_wrong_lookup_and_territory(as_admin, seeded, team, company):
    with tenant_context(company.id):
        other_zone = f.territory(zone_name="Val di Zoldo", slope_name="Lendina")[1]
    r = as_admin.post(
        "/api/v1/events",
        {"dateandtime": "2026-01-20T09:30:00Z", "team": str(team.id), "cause": "nope"},
        format="json",
    )
    assert r.status_code == 400
    assert "cause" in r.json()["fields"]
    r = as_admin.post(
        "/api/v1/events",
        {
            "dateandtime": "2026-01-20T09:30:00Z",
            "team": str(team.id),
            "zone": str(other_zone.id),
            "slope": str(seeded["slope"].id),
        },
        format="json",
    )
    assert r.status_code == 400
    assert "slope" in r.json()["fields"]


def test_add_person_then_event_fully_valid(as_admin, seeded):
    e2 = seeded["e2"]
    r = as_admin.post(
        f"/api/v1/events/{e2.id}/persons",
        {
            "age": 16,
            "gender": "male",
            "country_code": "PL",
            "initials_firstname": "wk",
            "initials_surname": "b",
            "diagnosis": "unharmed",
            "evacuation_means": [{"mean": "autonomous", "order": 1}],
            "injuries": [{"body_part": "knee_left", "rank": "primary"}],
            "pii": {
                "ciphertext": "AAEC",
                "key_wrapped": "AwQF",
                "key_version": 1,
                "fields": ["firstname", "surname"],
            },
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    p = r.json()
    assert p["initials_firstname"] == "WK" and p["sequence"] == 1
    assert p["gravest_injury"] == "knee_left" and p["injury_place"] == "lower_limbs"
    assert p["has_identity"] is True and p["pii_fields"] == ["firstname", "surname"]
    assert p["valid"] is True
    detail = as_admin.get(f"/api/v1/events/{e2.id}").json()
    assert detail["valid"] is False  # evento incompleto (zona, causa, geometria mancanti)
    assert detail["fully_valid"] is False


def test_lock_blocks_edits_until_unlock_with_audit(as_admin, admin_user, seeded, company):
    e1 = seeded["e1"]
    assert as_admin.post(f"/api/v1/events/{e1.id}/lock").status_code == 200
    r = as_admin.patch(f"/api/v1/events/{e1.id}", {"cause_note": "x"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "event_locked"
    r = as_admin.post(f"/api/v1/events/{e1.id}/unlock", {"reason": "correzione pista"}, format="json")
    assert r.status_code == 200 and r.json()["unlock_count"] == 1 and r.json()["locked_at"] is None
    assert as_admin.patch(f"/api/v1/events/{e1.id}", {"cause_note": "x"}, format="json").status_code == 200
    with tenant_context(company.id):
        actions = list(AuditLog.objects.filter(object_id=e1.id).values_list("action", flat=True))
    assert "event.lock" in actions and "event.unlock" in actions and "event.update" in actions


def test_rescuer_sees_only_own_teams_and_cannot_edit_others(api_client, company, team, seeded):
    with tenant_context(company.id):
        other_team = Team.objects.create(name="Squadra B")
        f.event(other_team, when=dt.datetime(2026, 3, 1, 9, 0, tzinfo=dt.UTC))
    rescuer = create_user(company, "r2@a.test", roles=("rescuer",), team=team)
    client = auth(api_client, rescuer)
    r = client.get("/api/v1/events")
    assert r.status_code == 200 and r.json()["count"] == 2  # solo la squadra A
    r = client.post(
        "/api/v1/events", {"dateandtime": "2026-01-20T09:30:00Z", "team": str(other_team.id)}, format="json"
    )
    assert r.status_code == 403 and r.json()["missing"] == ["events.edit_any_team"]
    assert (
        client.post(f"/api/v1/events/{seeded['e1'].id}/unlock", {"reason": "x"}, format="json").status_code
        == 403
    )


@pytest.mark.parametrize("role", ["rescue_manager", "analyst"])
def test_manager_and_analyst_see_only_own_teams(api_client, as_admin, company, team, seeded, role):
    with tenant_context(company.id):
        other_team = Team.objects.create(name="Squadra C")
        f.event(other_team, when=dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC))
    assert as_admin.get("/api/v1/events").json()["count"] == 3  # l'amministratore vede tutto
    user = create_user(company, f"{role}@a.test", roles=(role,), team=team)
    r = auth(api_client, user).get("/api/v1/events")
    assert r.status_code == 200 and r.json()["count"] == 2  # solo la squadra A


def test_other_tenant_event_is_404(as_admin, other_company, seeded):
    with tenant_context(other_company.id):
        team_b = Team.objects.create(name="B1")
        foreign = f.event(team_b, complete=False)
    assert as_admin.get(f"/api/v1/events/{foreign.id}").status_code == 404
    assert as_admin.patch(f"/api/v1/events/{foreign.id}", {"note": "x"}, format="json").status_code == 404


def test_soft_delete_hides_event(as_admin, seeded, company):
    e2 = seeded["e2"]
    assert as_admin.delete(f"/api/v1/events/{e2.id}").status_code == 204
    assert as_admin.get(f"/api/v1/events/{e2.id}").status_code == 404
    with tenant_context(company.id):
        assert Event.objects.get(pk=e2.id).deleted_at is not None


def test_person_list_filters_and_identity_requires_grant(as_admin, seeded, company):
    r = as_admin.get("/api/v1/persons?season=2025/2026&gender=female")
    assert r.status_code == 200 and r.json()["count"] == 1
    p = r.json()["results"][0]
    assert p["event"]["slope_name"] == "LE CIAUNE" and p["event"]["team_name"] == "Squadra A"
    assert as_admin.get("/api/v1/persons?evacuation_mean=helicopter_118").json()["count"] == 0
    # nessun dato cifrato → 404; con dati cifrati ma senza grant → 409
    assert as_admin.get(f"/api/v1/persons/{p['id']}/identity").status_code == 404
    as_admin.patch(
        f"/api/v1/persons/{p['id']}",
        {"pii": {"ciphertext": "AAEC", "key_wrapped": "AwQF", "key_version": 1, "fields": ["surname"]}},
        format="json",
    )
    r = as_admin.get(f"/api/v1/persons/{p['id']}/identity")
    assert r.status_code == 409 and r.json()["code"] == "no_key_grant"
    with tenant_context(company.id):
        assert AuditLog.objects.filter(action="person.identity_read", object_id=p["id"]).exists()


def test_lookups_endpoint(as_admin):
    r = as_admin.get("/api/v1/lookups")
    assert r.status_code == 200
    body = r.json()
    assert body["cause"][0]["code"] == "accidental_fall"
    assert body["cause"][0]["labels"]["de"] == "Sturz"
    assert any(b["parent"] == "lower_limbs" for b in body["body_part"])
    assert any(c["code"] == "IT" for c in body["country"])
    assert as_admin.get("/api/v1/lookups?dimension=nope").status_code == 400
