"""Chiavi E2E: chiave personale, inizializzazione chiave società, grant, identity, rotazione con
re-wrap, recupero. Il "browser" è simulato con PyNaCl (sealed box X25519); il server resta opaco."""

from __future__ import annotations

import base64

import pytest
from nacl.public import PrivateKey, PublicKey, SealedBox
from rest_framework.test import APIClient

from safe.apps.audit.models import AuditLog
from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


def b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def ub64(s: str) -> bytes:
    return base64.b64decode(s)


class Browser:
    """Stato client di un utente: coppia personale e, se custode, privata società."""

    def __init__(self, client: APIClient) -> None:
        self.c = client
        self.user_priv = PrivateKey.generate()
        self.company_priv: PrivateKey | None = None

    def create_user_key(self) -> None:
        r = self.c.put(
            "/api/v1/crypto/my-key",
            {
                "public_key": b64(bytes(self.user_priv.public_key)),
                "private_key_encrypted": b64(b"\x01" * 48),
                "kdf_params": {"alg": "argon2id", "salt": b64(b"\x02" * 16), "ops": 2, "mem": 67108864},
            },
            format="json",
        )
        assert r.status_code == 200, r.content

    def init_payload(self, company_priv: PrivateKey) -> dict:
        return {
            "public_key": b64(bytes(company_priv.public_key)),
            "wrapped_private_key": b64(SealedBox(self.user_priv.public_key).encrypt(bytes(company_priv))),
            "recovery": {
                "encrypted_private_key": b64(b"\x03" * 64),
                "kdf_params": {"alg": "argon2id", "salt": b64(b"\x04" * 16)},
            },
        }

    def open_grant(self, wrapped_b64: str) -> PrivateKey:
        return PrivateKey(SealedBox(self.user_priv).decrypt(ub64(wrapped_b64)))


@pytest.fixture
def admin_custodian(as_admin, admin_user, company):  # noqa: ANN001, ANN201
    """L'amministratore demo non è custode per template: gli aggiungiamo i permessi crypto."""
    from safe.apps.authz.models import Permission, UserPermission

    with tenant_context(company.id):
        for code in ("crypto.manage_keys", "crypto.recovery"):
            UserPermission.objects.create(
                user=admin_user, permission=Permission.objects.get(code=code), effect="grant"
            )
    return as_admin


@pytest.fixture
def custodian(admin_custodian):  # noqa: ANN001, ANN201
    as_admin = admin_custodian
    b = Browser(as_admin)
    b.create_user_key()
    b.company_priv = PrivateKey.generate()
    r = as_admin.post("/api/v1/crypto/company-key", b.init_payload(b.company_priv), format="json")
    assert r.status_code == 201, r.content
    return b


def test_company_key_requires_user_key_and_is_single(admin_custodian, company):
    as_admin = admin_custodian
    r = as_admin.post("/api/v1/crypto/company-key", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "user_key_missing"
    assert as_admin.get("/api/v1/crypto/company-key").status_code == 404


def test_init_grant_identity_roundtrip(as_admin, custodian, company, team, api_client):
    key = as_admin.get("/api/v1/crypto/company-key").json()
    assert key["version"] == 1 and ub64(key["public_key"]) == bytes(custodian.company_priv.public_key)
    me = as_admin.get("/api/v1/me").json()
    assert me["permissions"]["crypto.holder"] is True and me["key_status"] == {
        "user_key": "present",
        "company_key_version": 1,
        "grant": "active",
    }
    # un soccorritore cifra i dati con la pubblica della società (data key sigillata)
    with tenant_context(company.id):
        f.territory()
        ev = f.event(team)
    data_key = b"\x07" * 32
    wrapped = SealedBox(PublicKey(ub64(key["public_key"]))).encrypt(data_key)
    r = as_admin.post(
        f"/api/v1/events/{ev.id}/persons",
        {
            "age": 30,
            "pii": {
                "ciphertext": b64(b"cipher"),
                "key_wrapped": b64(wrapped),
                "key_version": 1,
                "fields": ["firstname"],
            },
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    pid = r.json()["id"]
    # il custode legge identity e apre la data key con la privata società ottenuta dalla grant
    ident = as_admin.get(f"/api/v1/persons/{pid}/identity").json()
    company_priv = custodian.open_grant(ident["grant"]["wrapped_private_key"])
    assert SealedBox(company_priv).decrypt(ub64(ident["key_wrapped"])) == data_key
    with tenant_context(company.id):
        assert AuditLog.objects.filter(action="crypto.company_key_init").exists()
    # /crypto/my-key espone le grant per il client
    mk = as_admin.get("/api/v1/crypto/my-key").json()
    assert mk["grants"][0]["key_version"] == 1 and mk["grants"][0]["company_public_key"] == key["public_key"]


def test_grant_other_user_and_revoke_rules(as_admin, custodian, company, team, admin_user):
    other = create_user(
        company, "custode2@a.test", roles=("rescue_manager",), grants=("persons.reveal_identity",), team=team
    )
    ob = Browser(auth(APIClient(), other))
    # senza chiave personale: candidato assente e grant rifiutata
    assert ob.c.get("/api/v1/me").json()["key_status"]["user_key"] == "missing"
    r = as_admin.post(
        "/api/v1/crypto/grants",
        {"user_id": str(other.id), "wrapped_private_key": b64(b"x" * 48)},
        format="json",
    )
    assert r.status_code == 400 and r.json()["code"] == "user_key_missing"
    ob.create_user_key()
    lst = as_admin.get("/api/v1/crypto/grants").json()
    assert [c["email"] for c in lst["candidates"]] == ["custode2@a.test"] and len(lst["grants"]) == 1
    pub = as_admin.get(f"/api/v1/crypto/users/{other.id}/public-key").json()
    wrapped = SealedBox(PublicKey(ub64(pub["public_key"]))).encrypt(bytes(custodian.company_priv))
    r = as_admin.post(
        "/api/v1/crypto/grants",
        {"user_id": str(other.id), "wrapped_private_key": b64(wrapped)},
        format="json",
    )
    assert r.status_code == 201 and r.json()["user"]["email"] == "custode2@a.test"
    assert ob.c.get("/api/v1/me").json()["key_status"]["grant"] == "active"
    assert bytes(
        ob.open_grant(ob.c.get("/api/v1/crypto/my-key").json()["grants"][0]["wrapped_private_key"])
    ) == bytes(custodian.company_priv)
    # revoca: mai l'ultimo custode
    assert as_admin.delete(f"/api/v1/crypto/grants/{other.id}").status_code == 204
    r = as_admin.delete(f"/api/v1/crypto/grants/{admin_user.id}")
    assert r.status_code == 409 and r.json()["code"] == "last_custodian"
    assert ob.c.get("/api/v1/me").json()["key_status"]["grant"] == "none"
    # rigenerare la propria chiave revoca le grant esistenti
    ob.c.put(
        "/api/v1/crypto/my-key",
        {"public_key": b64(b"\x09" * 32), "private_key_encrypted": b64(b"\x01" * 48), "kdf_params": {}},
        format="json",
    )
    assert ob.c.get("/api/v1/crypto/my-key").json()["grants"] == []


def test_rotation_with_rewrap(as_admin, custodian, company, team):
    with tenant_context(company.id):
        f.territory()
        ev = f.event(team)
    old_pub = custodian.company_priv.public_key
    pids = []
    for i in range(3):
        wrapped = SealedBox(old_pub).encrypt(bytes([i]) * 32)
        r = as_admin.post(
            f"/api/v1/events/{ev.id}/persons",
            {
                "age": 20 + i,
                "pii": {
                    "ciphertext": b64(b"c"),
                    "key_wrapped": b64(wrapped),
                    "key_version": 1,
                    "fields": ["surname"],
                },
            },
            format="json",
        )
        pids.append(r.json()["id"])
    new_priv = PrivateKey.generate()
    r = as_admin.post("/api/v1/crypto/company-key/rotate", custodian.init_payload(new_priv), format="json")
    assert r.status_code == 201 and r.json()["version"] == 2 and r.json()["persons_to_rewrap"] == 3
    batch = as_admin.get("/api/v1/crypto/company-key/rewrap?limit=2").json()
    assert batch["remaining"] == 3 and len(batch["items"]) == 2 and batch["active_version"] == 2
    items = []
    for it in batch["items"]:
        data_key = SealedBox(custodian.company_priv).decrypt(ub64(it["key_wrapped"]))
        items.append(
            {
                "person_id": it["person_id"],
                "key_wrapped": b64(SealedBox(new_priv.public_key).encrypt(data_key)),
            }
        )
    r = as_admin.post("/api/v1/crypto/company-key/rewrap", {"items": items}, format="json")
    assert r.json() == {"updated": 2, "remaining": 1, "active_version": 2}
    ident = as_admin.get(f"/api/v1/persons/{items[0]['person_id']}/identity").json()
    assert ident["key_version"] == 2
    assert SealedBox(new_priv).decrypt(ub64(ident["key_wrapped"])) in [bytes([i]) * 32 for i in range(3)]
    keys = as_admin.get("/api/v1/crypto/grants").json()
    assert keys["key"]["version"] == 2


def test_recovery_flow(as_admin, custodian, company, team):
    rec = as_admin.get("/api/v1/crypto/recovery").json()
    assert rec["key_version"] == 1 and rec["encrypted_private_key"] == b64(b"\x03" * 64)
    # un altro utente con crypto.recovery (che ha perso tutto) recupera: nuova grant per sé e nuovo kit
    rescuer = create_user(
        company, "recovery@a.test", roles=("key_custodian",), grants=("crypto.recovery",), team=team
    )
    rb = Browser(auth(APIClient(), rescuer))
    rb.create_user_key()
    payload = rb.init_payload(custodian.company_priv)  # stessa chiave società (decifrata dal codice)
    r = rb.c.post("/api/v1/crypto/recovery", payload, format="json")
    assert r.status_code == 201, r.content
    assert rb.c.get("/api/v1/me").json()["key_status"]["grant"] == "active"
    r = rb.c.post("/api/v1/crypto/recovery", {**payload, "public_key": b64(b"\x11" * 32)}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "public_key_mismatch"
    with tenant_context(company.id):
        assert AuditLog.objects.filter(action="crypto.recovery_used").count() == 1
        assert AuditLog.objects.filter(action="crypto.recovery_read").count() == 1


def test_recovery_read_is_throttled(as_admin, custodian):
    codes = [as_admin.get("/api/v1/crypto/recovery").status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
