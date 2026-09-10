"""Gestione utenti (inviti via Keycloak simulato), permessi, ruoli, squadre."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from safe.apps.audit.models import AuditLog
from safe.apps.org import keycloak
from safe.apps.org.models import AppUser, Team
from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


class FakeKeycloak:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.emails: list[tuple[str, list[str], str]] = []
        self.logouts: list[str] = []
        self.fail = False

    def create_user(self, *, email, first_name, last_name, locale):  # noqa: ANN001, ANN202
        if self.fail:
            raise keycloak.KeycloakError("keycloak_unavailable", "giù")
        kc_id = f"kc-{len(self.users) + 1}"
        self.users[kc_id] = {"email": email, "enabled": True, "locale": locale}
        return kc_id

    def update_user(self, kc_id, **fields):  # noqa: ANN001, ANN202
        self.users[kc_id].update(fields)

    def send_actions_email(self, kc_id, *, actions, redirect_uri, lifespan):  # noqa: ANN001, ANN202
        self.emails.append((kc_id, actions, redirect_uri))

    def set_enabled(self, kc_id, enabled):  # noqa: ANN001, ANN202
        self.users[kc_id]["enabled"] = enabled
        if not enabled:
            self.logouts.append(kc_id)


@pytest.fixture
def kc(monkeypatch):  # noqa: ANN001, ANN201
    fake = FakeKeycloak()
    monkeypatch.setattr(keycloak, "get_client", lambda: fake)
    return fake


# --- inviti ----------------------------------------------------------------------------


def test_invite_creates_keycloak_user_and_sends_email(as_admin, company, team, kc):
    r = as_admin.post(
        "/api/v1/users/invite",
        {
            "email": "Nuovo@Esempio.it",
            "first_name": "Nuovo",
            "last_name": "Utente",
            "locale": "de",
            "teams": [str(team.id)],
            "roles": ["rescuer"],
            "mfa_required": True,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    u = r.json()
    assert u["email"] == "nuovo@esempio.it" and u["status"] == "invited" and u["roles"] == ["rescuer"]
    assert u["teams"] == [{"id": str(team.id), "name": "Squadra A", "is_default": True}]
    assert kc.users["kc-1"]["email"] == "nuovo@esempio.it"
    kc_id, actions, redirect = kc.emails[0]
    assert (
        kc_id == "kc-1" and actions == ["UPDATE_PASSWORD", "CONFIGURE_TOTP"] and redirect.endswith("/de/home")
    )
    with tenant_context(company.id):
        assert AppUser.objects.get(email="nuovo@esempio.it").keycloak_id == "kc-1"
        assert AuditLog.objects.filter(action="user.invite").exists()


def test_invite_duplicate_email_409_and_keycloak_failure_rolls_back(as_admin, company, kc, admin_user):
    r = as_admin.post("/api/v1/users/invite", {"email": admin_user.email}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "email_in_use"
    kc.fail = True
    r = as_admin.post("/api/v1/users/invite", {"email": "x@y.it"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "keycloak_unavailable"
    with tenant_context(company.id):
        assert not AppUser.objects.filter(email="x@y.it").exists()


def test_invite_requires_permission_and_is_tenant_scoped(api_client, company, other_company, team, kc):
    viewer = create_user(company, "viewer@a.test", roles=("analyst",))
    r = auth(APIClient(), viewer).post("/api/v1/users/invite", {"email": "a@b.it"}, format="json")
    assert r.status_code == 403 and r.json()["missing"] == ["users.invite"]
    other = create_user(other_company, "adm@b.test", roles=("company_admin",))
    r = auth(APIClient(), other).post(
        "/api/v1/users/invite", {"email": "b@b.it", "teams": [str(team.id)]}, format="json"
    )
    assert r.status_code == 400 and "teams" in r.json()["fields"]


def test_resend_invite_only_for_invited(as_admin, company, kc, rescuer_user):
    r = as_admin.post("/api/v1/users/invite", {"email": "inv@a.test"}, format="json")
    uid = r.json()["id"]
    assert as_admin.post(f"/api/v1/users/{uid}/resend-invite").status_code == 200 and len(kc.emails) == 2
    r = as_admin.post(f"/api/v1/users/{rescuer_user.id}/resend-invite")
    assert r.status_code == 400 and r.json()["code"] == "not_invited"


# --- lista, modifica, disattivazione -------------------------------------------------------


def test_list_filter_and_patch(as_admin, company, team, rescuer_user, kc):
    with tenant_context(company.id):
        other_team = Team.objects.create(name="Squadra B")
    users = as_admin.get("/api/v1/users").json()
    assert sorted(u["email"] for u in users) == ["admin@a.test", "rescuer@a.test"]
    assert as_admin.get("/api/v1/users?search=resc").json()[0]["email"] == "rescuer@a.test"
    r = as_admin.patch(
        f"/api/v1/users/{rescuer_user.id}",
        {
            "first_name": "Rita",
            "locale": "en",
            "teams": [str(team.id), str(other_team.id)],
            "default_team": str(other_team.id),
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    u = r.json()
    assert u["first_name"] == "Rita" and u["locale"] == "en"
    assert {t["name"]: t["is_default"] for t in u["teams"]} == {"Squadra A": False, "Squadra B": True}
    assert as_admin.get(f"/api/v1/users?team={other_team.id}").json()[0]["id"] == str(rescuer_user.id)


def test_disable_blocks_login_and_enable_restores(
    as_admin, api_client, company, rescuer_user, admin_user, kc
):
    with tenant_context(company.id):
        rescuer_user.keycloak_id = "kc-r"
        rescuer_user.save(update_fields=["keycloak_id"])
    kc.users["kc-r"] = {"enabled": True}
    r = as_admin.post(f"/api/v1/users/{rescuer_user.id}/disable")
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    assert kc.users["kc-r"]["enabled"] is False and kc.logouts == ["kc-r"]
    r = auth(APIClient(), rescuer_user).get("/api/v1/me")
    assert r.status_code == 401 and r.json()["code"] == "user_disabled"
    r = as_admin.post(f"/api/v1/users/{admin_user.id}/disable")
    assert r.status_code == 400 and r.json()["code"] == "self_disable"
    r = as_admin.post(f"/api/v1/users/{rescuer_user.id}/enable")
    assert r.status_code == 200 and r.json()["status"] == "active" and kc.users["kc-r"]["enabled"] is True
    assert auth(APIClient(), rescuer_user).get("/api/v1/me").status_code == 200


def test_manage_requires_permission(api_client, company, rescuer_user):
    viewer = create_user(company, "viewer2@a.test", roles=("analyst",), grants=("users.view",))
    c = auth(APIClient(), viewer)
    assert c.get("/api/v1/users").status_code == 200
    assert c.patch(f"/api/v1/users/{rescuer_user.id}", {"first_name": "X"}, format="json").status_code == 403
    assert c.post(f"/api/v1/users/{rescuer_user.id}/disable").status_code == 403


# --- permessi e ruoli ------------------------------------------------------------------------


def test_put_permissions_changes_effective_map(as_admin, api_client, company, rescuer_user, admin_user):
    c = auth(APIClient(), rescuer_user)
    assert c.get("/api/v1/me").json()["permissions"]["stats.view"] is False
    r = as_admin.put(
        f"/api/v1/users/{rescuer_user.id}/permissions",
        {"roles": ["rescuer", "analyst"], "grants": ["exports.dataset"], "denies": ["events.create"]},
        format="json",
    )
    assert r.status_code == 200, r.content
    u = r.json()
    assert (
        sorted(u["roles"]) == ["analyst", "rescuer"]
        and u["grants"] == ["exports.dataset"]
        and u["denies"] == ["events.create"]
    )
    perms = auth(APIClient(), rescuer_user).get("/api/v1/me").json()["permissions"]
    assert (
        perms["stats.view"] is True and perms["exports.dataset"] is True and perms["events.create"] is False
    )
    r = as_admin.put(f"/api/v1/users/{rescuer_user.id}/permissions", {"roles": ["boss"]}, format="json")
    assert r.status_code == 400 and "roles" in r.json()["fields"]
    r = as_admin.put(
        f"/api/v1/users/{admin_user.id}/permissions",
        {"roles": ["company_admin"], "denies": ["users.assign_permissions"]},
        format="json",
    )
    assert r.status_code == 400 and r.json()["code"] == "self_lockout"


def test_roles_list_and_custom_role(as_admin, api_client, company, other_company):
    roles = as_admin.get("/api/v1/roles").json()
    assert {r["code"] for r in roles} >= {"company_admin", "rescuer", "analyst"}
    assert "events.unlock" in next(r for r in roles if r["code"] == "company_admin")["permissions"]
    r = as_admin.post(
        "/api/v1/roles",
        {
            "code": "night_shift",
            "name_it": "Turno notte",
            "name_en": "Night shift",
            "name_de": "Nachtschicht",
            "permissions": ["events.view", "events.create", "map.view"],
        },
        format="json",
    )
    assert (
        r.status_code == 201
        and r.json()["is_custom"] is True
        and r.json()["permissions"] == ["events.create", "events.view", "map.view"]
    )
    other = create_user(other_company, "adm2@b.test", roles=("company_admin",))
    assert "night_shift" not in {x["code"] for x in auth(APIClient(), other).get("/api/v1/roles").json()}
    assert (
        as_admin.post(
            "/api/v1/roles",
            {"code": "rescuer", "name_it": "x", "name_en": "x", "name_de": "x", "permissions": []},
            format="json",
        ).status_code
        == 400
    )


# --- squadre ---------------------------------------------------------------------------------


def test_teams_crud_and_deactivation_rules(as_admin, company, team, rescuer_user):
    r = as_admin.post("/api/v1/teams", {"name": "Truppe Alpine", "body": "alpine_troops"}, format="json")
    assert r.status_code == 201 and r.json()["body"] == "alpine_troops"
    tid = r.json()["id"]
    assert as_admin.post("/api/v1/teams", {"name": "truppe alpine"}, format="json").status_code == 400
    teams = as_admin.get("/api/v1/teams").json()
    assert {t["name"]: t["users_count"] for t in teams} == {"Squadra A": 2, "Truppe Alpine": 0}
    assert (
        as_admin.patch(f"/api/v1/teams/{tid}", {"name": "Alpini"}, format="json").json()["name"] == "Alpini"
    )
    assert as_admin.delete(f"/api/v1/teams/{tid}").status_code == 204
    assert [t["name"] for t in as_admin.get("/api/v1/teams").json()] == ["Squadra A"]
    assert len(as_admin.get("/api/v1/teams?include_inactive=true").json()) == 2
    with tenant_context(company.id):
        f.territory()
        f.event(team)
    r = as_admin.delete(f"/api/v1/teams/{team.id}")
    assert r.status_code == 400 and r.json()["code"] == "team_has_events"
    assert as_admin.get("/api/v1/teams").json()[0]["events_count"] == 1
