"""Gestione territorio (CRUD con geometrie), vocabolari personalizzati, impostazioni società."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


# --- territorio ------------------------------------------------------------------------------


def test_territory_crud_with_geometry(as_admin, company):
    r = as_admin.post(
        "/api/v1/ski-areas",
        {
            "name": "Civetta",
            "regional_code": "C",
            "boundary": {
                "type": "Polygon",
                "coordinates": [[[12, 46], [12.1, 46], [12.1, 46.1], [12, 46.1], [12, 46]]],
            },
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    area = r.json()
    assert area["has_boundary"] is True
    r = as_admin.post("/api/v1/zones", {"name": "Val Fiorentina", "ski_area_id": area["id"]}, format="json")
    assert r.status_code == 201
    zone = r.json()
    r = as_admin.post(
        "/api/v1/slopes",
        {
            "name": "Le Ciaune",
            "regional_code": "C.1.24",
            "difficulty": "blue",
            "zone_id": zone["id"],
            "geom": {"type": "LineString", "coordinates": [[12.01, 46.01], [12.02, 46.02]]},
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    slope = r.json()
    assert (
        slope["has_geometry"] is True
        and slope["difficulty"] == "blue"
        and slope["zone"]["ski_area"] == area["id"]
    )
    r = as_admin.post(
        "/api/v1/lifts",
        {"name": "Seggiovia", "lift_type": "chairlift", "ski_area_id": area["id"]},
        format="json",
    )
    assert r.status_code == 201
    assert as_admin.get("/api/v1/ski-areas").json()[0]["zones_count"] == 1
    assert as_admin.get(f"/api/v1/zones?ski_area={area['id']}").json()[0]["slopes_count"] == 1
    assert (
        as_admin.patch(f"/api/v1/slopes/{slope['id']}", {"difficulty": "black"}, format="json").json()[
            "difficulty"
        ]
        == "black"
    )
    r = as_admin.post(
        "/api/v1/slopes",
        {"name": "X", "zone_id": zone["id"], "geom": {"type": "Point", "coordinates": [1, 2]}},
        format="json",
    )
    assert r.status_code == 400
    assert as_admin.delete(f"/api/v1/slopes/{slope['id']}").status_code == 204
    assert as_admin.get(f"/api/v1/slopes?zone={zone['id']}").json() == []
    assert (
        as_admin.get(f"/api/v1/slopes?zone={zone['id']}&include_inactive=true").json()[0]["is_active"]
        is False
    )
    # geometrie mai in lettura nelle liste (solo flag), disponibili via GeoJSON di mappa
    assert "geom" not in as_admin.get("/api/v1/slopes?include_inactive=true").json()[0]


def test_territory_manage_requires_permission_and_tenant(api_client, company, other_company):
    viewer = create_user(company, "tv@a.test", roles=("analyst",))
    c = auth(APIClient(), viewer)
    assert c.get("/api/v1/ski-areas").status_code == 200
    r = c.post("/api/v1/ski-areas", {"name": "Nuovo"}, format="json")
    assert r.status_code == 403 and r.json()["missing"] == ["territory.manage"]
    with tenant_context(company.id):
        area, zone, _ = f.territory()
    other = create_user(other_company, "adm3@b.test", roles=("company_admin",))
    r = auth(APIClient(), other).post(
        "/api/v1/zones", {"name": "Z", "ski_area_id": str(area.id)}, format="json"
    )
    assert r.status_code == 400  # comprensorio di un'altra società non visibile


# --- vocabolari --------------------------------------------------------------------------------


def test_lookups_custom_value_and_disable_global(as_admin, api_client, company, other_company):
    r = as_admin.post(
        "/api/v1/lookups/cause",
        {
            "code": "drone_strike",
            "labels": {"it": "Urto con drone", "en": "Drone strike"},
            "sort_order": 5,
            "mapping": {"veneto_a01": "Altro"},
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    v = r.json()
    assert v["is_custom"] is True and v["labels"]["de"] == "Urto con drone"
    assert (
        as_admin.post(
            "/api/v1/lookups/cause", {"code": "drone_strike", "labels": {"it": "x"}}, format="json"
        ).status_code
        == 409
    )
    assert (
        as_admin.post(
            "/api/v1/lookups/cause", {"code": "Bad Code", "labels": {"it": "x"}}, format="json"
        ).status_code
        == 400
    )
    codes = [x["code"] for x in as_admin.get("/api/v1/lookups?dimension=cause").json()["cause"]]
    assert codes[0] == "drone_strike"  # sort_order 5
    # altro tenant non lo vede
    other = create_user(other_company, "adm4@b.test", roles=("company_admin",))
    assert "drone_strike" not in [
        x["code"] for x in auth(APIClient(), other).get("/api/v1/lookups?dimension=cause").json()["cause"]
    ]
    # modifica del valore personalizzato
    r = as_admin.patch(
        f"/api/v1/lookups/cause/{v['id']}",
        {"labels": {"it": "Drone", "en": "Drone", "de": "Drohne"}, "color": "#112233"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["labels"]["de"] == "Drohne" and r.json()["color"] == "#112233"
    # valore globale: solo disattivazione per la società
    admin_list = as_admin.get("/api/v1/lookups/cause").json()
    illness = next(x for x in admin_list if x["code"] == "illness")
    assert admin_list and illness["disabled_for_company"] is False
    r = as_admin.patch(f"/api/v1/lookups/cause/{illness['id']}", {"labels": {"it": "x"}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "global_value"
    r = as_admin.patch(f"/api/v1/lookups/cause/{illness['id']}", {"is_active": False}, format="json")
    assert r.status_code == 200 and r.json()["disabled_for_company"] is True
    assert "illness" not in [
        x["code"] for x in as_admin.get("/api/v1/lookups?dimension=cause").json()["cause"]
    ]
    assert "illness" in [
        x["code"] for x in auth(APIClient(), other).get("/api/v1/lookups?dimension=cause").json()["cause"]
    ]
    r = as_admin.patch(f"/api/v1/lookups/cause/{illness['id']}", {"is_active": True}, format="json")
    assert r.json()["disabled_for_company"] is False


def test_lookups_manage_requires_permission(api_client, company):
    viewer = create_user(company, "lv@a.test", roles=("rescue_manager",))
    r = auth(APIClient(), viewer).get("/api/v1/lookups/cause")
    assert r.status_code == 403 and r.json()["missing"] == ["lookups.manage"]


# --- società -----------------------------------------------------------------------------------


def test_company_get_and_patch_settings(as_admin, api_client, company, rescuer_user):
    body = auth(APIClient(), rescuer_user).get("/api/v1/company").json()
    assert body["slug"] == "a" and body["settings"]["auto_lock_hours"] == 48
    assert (
        auth(APIClient(), rescuer_user).patch("/api/v1/company", {"name": "X"}, format="json").status_code
        == 403
    )
    r = as_admin.patch(
        "/api/v1/company",
        {
            "name": "Società A S.p.A.",
            "timezone": "Europe/Vienna",
            "default_locale": "de",
            "settings": {
                "auto_lock_hours": 24,
                "first_season": "2025/2026",
                "devices_need_authorization": False,
                "validity_rules": {"person_required": ["age", "gender"]},
                "duplicate_rule": {"minutes": 45},
            },
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    b = r.json()
    assert (
        b["name"] == "Società A S.p.A." and b["timezone"] == "Europe/Vienna" and b["default_locale"] == "de"
    )
    assert b["settings"]["auto_lock_hours"] == 24 and b["settings"]["devices_need_authorization"] is False
    assert b["settings"]["first_season"] == "2025/2026"
    assert b["settings"]["validity_rules"]["person_required"] == ["age", "gender"]
    assert b["settings"]["validity_rules"]["event_required"][0] == "dateandtime"  # default conservato
    assert b["settings"]["duplicate_rule"] == {
        "minutes": 45,
        "fields": ["date", "slope", "gender", "age_class_a01", "equipment"],
    }
    assert as_admin.patch("/api/v1/company", {"timezone": "Mars/Olympus"}, format="json").status_code == 400
    assert (
        as_admin.patch(
            "/api/v1/company", {"settings": {"validity_rules": {"event_required": ["nope"]}}}, format="json"
        ).status_code
        == 400
    )
