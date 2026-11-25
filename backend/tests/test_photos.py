"""Foto degli eventi: cifrate nel browser (qui simulato con PyNaCl), al massimo 6, contenuto solo a chi ha
la chiave della società, rotazione delle chiavi, cancellazione con l'evento e con la retention, PDF."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from nacl.public import PrivateKey, SealedBox
from nacl.secret import SecretBox

from safe.apps.audit.models import AuditLog
from safe.apps.rescue import retention
from safe.apps.rescue.models import Event, EventPhoto
from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user
from .test_crypto_api import admin_custodian, b64, custodian, ub64  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db


def encrypt_photo(public_key, jpeg: bytes) -> tuple[bytes, str]:  # noqa: ANN001
    """Come il browser: data key casuale, contenuto cifrato, data key sigillata per la società."""
    data_key = bytes(uuid.uuid4().bytes * 2)
    box = SecretBox(data_key).encrypt(jpeg)  # nonce || box (in produzione XChaCha20-Poly1305 di libsodium)
    return bytes(box), b64(SealedBox(public_key).encrypt(data_key))


def upload(client, event_id, public_key, *, jpeg=b"\xff\xd8JPEG" * 40, client_uuid=None, version=1):  # noqa: ANN001, ANN201
    content, wrapped = encrypt_photo(public_key, jpeg)
    data = {
        "file": SimpleUploadedFile("foto.bin", content, content_type="application/octet-stream"),
        "key_wrapped": wrapped,
        "key_version": version,
    }
    if client_uuid:
        data["client_uuid"] = client_uuid
    return client.post(f"/api/v1/events/{event_id}/photos", data, format="multipart")


@pytest.fixture
def event(company, team):  # noqa: ANN001, ANN201
    with tenant_context(company.id):
        f.territory()
        return f.event(team)


def test_upload_list_read_and_limit(as_admin, custodian, event, _fake_storage):  # noqa: F811
    pub = custodian.company_priv.public_key
    jpeg = b"\xff\xd8 foto del luogo " * 50
    r = upload(as_admin, event.id, pub, jpeg=jpeg, client_uuid="7d1c3a9e-1111-4222-8333-444455556666")
    assert r.status_code == 201, r.content
    photo = r.json()
    assert photo["event_id"] == str(event.id) and photo["key_version"] == 1
    # il server conserva solo contenuto cifrato, sotto il prefisso unico delle foto
    key = f"photos/{event.company_id}/{event.id}/{photo['id']}.bin"
    assert key in _fake_storage and jpeg not in _fake_storage[key]
    # stesso client_uuid (coda della modalità pista che ripete l'invio): nessun doppione
    again = upload(as_admin, event.id, pub, client_uuid="7d1c3a9e-1111-4222-8333-444455556666")
    assert again.status_code == 200 and again.json()["id"] == photo["id"]
    # il contenuto si apre con la chiave della società: come farebbe il browser
    r = as_admin.get(f"/api/v1/photos/{photo['id']}/content")
    assert r.status_code == 200 and r["Cache-Control"] == "private, no-store"
    data_key = SealedBox(custodian.company_priv).decrypt(ub64(photo["key_wrapped"]))
    assert SecretBox(data_key).decrypt(r.content) == jpeg
    with tenant_context(event.company_id):
        assert AuditLog.objects.filter(action="photo.read", object_id=photo["id"]).exists()
    assert as_admin.get(f"/api/v1/events/{event.id}").json()["photos_count"] == 1
    # al massimo 6 per evento
    for _ in range(5):
        assert upload(as_admin, event.id, pub).status_code == 201
    r = upload(as_admin, event.id, pub)
    assert r.status_code == 409 and r.json()["code"] == "photo_limit"
    listed = as_admin.get(f"/api/v1/events/{event.id}/photos").json()
    assert len(listed) == 6 and listed[0]["id"] == photo["id"] and listed[0]["created_by"]


def test_rejects_oversized_unknown_key_and_locked_event(as_admin, custodian, event):  # noqa: F811
    pub = custodian.company_priv.public_key
    r = upload(as_admin, event.id, pub, jpeg=b"x" * (2 * 1024 * 1024 + 10))
    assert r.status_code == 400 and "file" in r.json()["fields"]
    r = upload(as_admin, event.id, pub, version=9)
    assert r.status_code == 409 and r.json()["code"] == "key_version"
    as_admin.post(f"/api/v1/events/{event.id}/lock")
    r = upload(as_admin, event.id, pub)
    assert r.status_code == 409 and r.json()["code"] == "event_locked"


def test_content_requires_key_grant_and_permission(as_admin, api_client, custodian, event, company, team):  # noqa: F811
    photo = upload(as_admin, event.id, custodian.company_priv.public_key).json()
    # soccorritore abilitato a leggere ma senza grant sulla chiave: 409 e lettura tentata in audit
    rescuer = create_user(company, "senza-chiave@a.test", roles=("rescuer",), team=team)
    client = auth(api_client, rescuer)
    assert len(client.get(f"/api/v1/events/{event.id}/photos").json()) == 1
    r = client.get(f"/api/v1/photos/{photo['id']}/content")
    assert r.status_code == 409 and r.json()["code"] == "no_key_grant"
    # analista senza il permesso di leggere i dati identificativi: 403
    analyst = create_user(company, "analista@a.test", grants=("events.view",), team=team)
    r = auth(api_client, analyst).get(f"/api/v1/photos/{photo['id']}/content")
    assert r.status_code == 403 and r.json()["missing"] == ["persons.reveal_identity"]


def test_delete_photo_and_event_removes_content(as_admin, custodian, event, _fake_storage):  # noqa: F811
    pub = custodian.company_priv.public_key
    p1 = upload(as_admin, event.id, pub).json()
    upload(as_admin, event.id, pub)
    assert as_admin.delete(f"/api/v1/photos/{p1['id']}").status_code == 204
    assert not any(k.endswith(f"{p1['id']}.bin") for k in _fake_storage)
    assert len(as_admin.get(f"/api/v1/events/{event.id}/photos").json()) == 1
    # eliminando l'evento si eliminano anche le foto, dall'archivio compreso
    assert as_admin.delete(f"/api/v1/events/{event.id}").status_code == 204
    assert not [k for k in _fake_storage if k.startswith("photos/")]
    assert EventPhoto.all_objects.count() == 0


def test_retention_deletes_photos_of_old_events(as_admin, custodian, company, team, _fake_storage):  # noqa: F811
    with tenant_context(company.id):
        f.territory()
        old = f.event(team, when=dt.datetime(2019, 1, 10, 10, 0, tzinfo=dt.UTC))
        recent = f.event(team, when=dt.datetime(2026, 1, 10, 10, 0, tzinfo=dt.UTC))
    pub = custodian.company_priv.public_key
    upload(as_admin, old.id, pub)
    upload(as_admin, recent.id, pub)
    with tenant_context(company.id):
        company.retention_identity_years = 5
        company.save(update_fields=["retention_identity_years"])
        res = retention.run_for_company(company)
        assert res["photos_deleted"] == 1
        assert list(EventPhoto.objects.values_list("event_id", flat=True)) == [recent.id]
    assert len([k for k in _fake_storage if k.startswith("photos/")]) == 1


def test_rotation_rewraps_photos(as_admin, custodian, event):  # noqa: F811
    photo = upload(as_admin, event.id, custodian.company_priv.public_key).json()
    new_priv = PrivateKey.generate()
    r = as_admin.post("/api/v1/crypto/company-key/rotate", custodian.init_payload(new_priv), format="json")
    assert r.status_code == 201 and r.json()["photos_to_rewrap"] == 1
    batch = as_admin.get("/api/v1/crypto/company-key/rewrap").json()
    assert batch["remaining"] == 1 and batch["items"][0]["photo_id"] == photo["id"]
    data_key = SealedBox(custodian.company_priv).decrypt(ub64(batch["items"][0]["key_wrapped"]))
    item = {"photo_id": photo["id"], "key_wrapped": b64(SealedBox(new_priv.public_key).encrypt(data_key))}
    r = as_admin.post("/api/v1/crypto/company-key/rewrap", {"items": [item]}, format="json")
    assert r.json() == {"updated": 1, "remaining": 0, "active_version": 2}
    listed = as_admin.get(f"/api/v1/events/{event.id}/photos").json()[0]
    assert listed["key_version"] == 2
    assert SealedBox(new_priv).decrypt(ub64(listed["key_wrapped"])) == data_key
    # un elemento deve indicare la persona oppure la foto, non entrambe né nessuna
    r = as_admin.post(
        "/api/v1/crypto/company-key/rewrap", {"items": [{"key_wrapped": item["key_wrapped"]}]}, format="json"
    )
    assert r.status_code == 400


def test_pdf_has_photo_slots_only_in_full_document(as_admin, custodian, event, company):  # noqa: F811
    from safe.apps.reports import pdf

    pub = custodian.company_priv.public_key
    ids = [upload(as_admin, event.id, pub).json()["id"] for _ in range(2)]
    with tenant_context(company.id):
        ev = Event.objects.get(pk=event.pk)
        std = render_to_string(
            "reports/event_report.html", pdf.build_context(ev, "it", downloaded_by="t", with_map=False)
        )
        full = render_to_string(
            "reports/event_report.html",
            pdf.build_context(ev, "it", downloaded_by="t", with_map=False, full=True),
        )
    assert "photo__" not in std and "solo nel documento completo" in std
    for pid in ids:
        assert f'name="photo__{pid}" value=""' in full
    assert "Foto 2 di 2" in full
    # una foto nuova cambia il PDF in cache (l'evento risulta modificato)
    before = as_admin.get(f"/api/v1/events/{event.id}").json()["updated_at"]
    upload(as_admin, event.id, pub)
    assert as_admin.get(f"/api/v1/events/{event.id}").json()["updated_at"] != before
