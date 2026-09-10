"""Dispositivi: codice QR, registrazione dall'app, autorizzazione, heartbeat, revoca."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from safe.apps.tenancy.context import bypass_tenant

from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


def test_enrollment_and_registration_flow(as_admin, api_client, company, rescuer_user):
    r = as_admin.post("/api/v1/devices/enrollment-code")
    assert r.status_code == 201
    body = r.json()
    assert body["qr_svg"].startswith("data:image/svg+xml;base64,") and body["code"] in body["qr_payload"]

    mobile = auth(APIClient(), rescuer_user)
    r = mobile.post(
        "/api/v1/devices/register",
        {
            "code": body["code"],
            "install_id": "inst-1",
            "name": "Pixel di Rita",
            "platform": "android",
            "app_version": "1.0",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    dev = r.json()
    assert dev["status"] == "pending" and dev["user"]["email"] == "rescuer@a.test"
    # codice monouso
    r = mobile.post("/api/v1/devices/register", {"code": body["code"], "install_id": "inst-2"}, format="json")
    assert r.status_code == 400
    # heartbeat prima dell'autorizzazione aggiorna comunque last_seen
    assert (
        mobile.post(
            "/api/v1/devices/heartbeat", {"install_id": "inst-1", "app_version": "1.1"}, format="json"
        ).status_code
        == 204
    )
    lst = as_admin.get("/api/v1/devices?status=pending").json()
    assert len(lst) == 1 and lst[0]["app_version"] == "1.1" and lst[0]["last_seen_at"]
    assert as_admin.get("/api/v1/devices/summary").json()["pending"] == 1

    r = as_admin.post(f"/api/v1/devices/{dev['id']}/authorize")
    assert r.status_code == 200 and r.json()["status"] == "authorized"
    assert (
        as_admin.patch(f"/api/v1/devices/{dev['id']}", {"name": "Pixel"}, format="json").json()["name"]
        == "Pixel"
    )
    assert as_admin.delete(f"/api/v1/devices/{dev['id']}").status_code == 204
    assert as_admin.get("/api/v1/devices?status=revoked").json()[0]["id"] == dev["id"]
    r = mobile.post("/api/v1/devices/heartbeat", {"install_id": "inst-1"}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "device_revoked"
    assert as_admin.post(f"/api/v1/devices/{dev['id']}/authorize").status_code == 400


def test_registration_without_authorization_setting(as_admin, api_client, company, rescuer_user):
    with bypass_tenant():
        company.settings = {"devices_need_authorization": False}
        company.save(update_fields=["settings"])
    code = as_admin.post("/api/v1/devices/enrollment-code").json()["code"]
    r = auth(APIClient(), rescuer_user).post(
        "/api/v1/devices/register", {"code": code, "install_id": "i9"}, format="json"
    )
    assert r.status_code == 201 and r.json()["status"] == "authorized"


def test_devices_permissions(api_client, company):
    viewer = create_user(company, "dv@a.test", roles=("analyst",), grants=("devices.view",))
    c = auth(APIClient(), viewer)
    assert c.get("/api/v1/devices").status_code == 200
    assert c.post("/api/v1/devices/enrollment-code").status_code == 403
    r = c.post("/api/v1/devices/register", {"code": "nope", "install_id": "x"}, format="json")
    assert r.status_code == 400  # autenticato ma codice non valido
