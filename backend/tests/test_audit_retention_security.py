"""Audit log (consultazione, immutabilità, export), retention/anonimizzazione, hardening HTTP,
nessun dato personale in risposte, URL e audit."""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import DatabaseError, transaction
from rest_framework.test import APIClient

from safe.apps.audit.models import AuditLog
from safe.apps.rescue import retention
from safe.apps.tenancy.context import bypass_tenant, tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db
UTC = dt.UTC

PII_KEYS = {"firstname", "first_name", "surname", "last_name", "phone", "email", "birth_date", "address"}


# --- audit ---------------------------------------------------------------------------------------


def test_audit_list_filters_export_and_actor_email(as_admin, company, team, admin_user):
    with tenant_context(company.id):
        f.territory()
        ev = f.event(team)
    as_admin.patch(f"/api/v1/events/{ev.id}", {"note": "x"}, format="json")
    as_admin.post(f"/api/v1/events/{ev.id}/lock")
    body = as_admin.get("/api/v1/audit-logs").json()
    assert body["count"] >= 2
    row = next(r for r in body["results"] if r["action"] == "event.lock")
    assert row["actor"] == "admin@a.test" and row["event_id"] == str(ev.id) and row["object_type"] == "event"
    assert as_admin.get(f"/api/v1/audit-logs?action=event.lock&actor={admin_user.id}").json()["count"] == 1
    assert as_admin.get("/api/v1/audit-logs?date_to=2000-01-01").json()["count"] == 0
    assert "event.lock" in as_admin.get("/api/v1/audit-logs/actions").json()
    r = as_admin.get("/api/v1/audit-logs/export?action=event")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert text.startswith("created_at;actor;action") and "event.lock" in text
    with tenant_context(company.id):
        assert AuditLog.objects.filter(action="audit.export").exists()


def test_audit_requires_permission_and_is_tenant_scoped(api_client, company, other_company):
    viewer = create_user(company, "noaudit@a.test", roles=("analyst",))
    r = auth(APIClient(), viewer).get("/api/v1/audit-logs")
    assert r.status_code == 403 and r.json()["missing"] == ["audit.view"]
    other = create_user(other_company, "adm@b.test", roles=("company_admin",))
    assert auth(APIClient(), other).get("/api/v1/audit-logs").json()["count"] == 0


def test_audit_log_is_immutable(company, tenant):
    row = AuditLog.all_objects.create(company_id=company.id, action="test", object_type="x")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.all_objects.filter(pk=row.pk).update(action="tampered")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.all_objects.filter(pk=row.pk).delete()
    assert AuditLog.all_objects.get(pk=row.pk).action == "test"


# --- retention -------------------------------------------------------------------------------------


@pytest.fixture
def aged(company, team):  # noqa: ANN001, ANN201
    with bypass_tenant():
        company.retention_identity_years = 2
        company.retention_audit_years = 1
        company.save(update_fields=["retention_identity_years", "retention_audit_years"])
    with tenant_context(company.id):
        f.territory()
        old = f.event(team, when=dt.datetime(2020, 1, 10, 10, 0, tzinfo=UTC))
        p_old = f.person(old, age=44)
        p_old.pii_ciphertext = b"c"
        p_old.pii_key_wrapped = b"k"
        p_old.pii_key_version = 1
        p_old.pii_fields = ["surname"]
        p_old.age_class_snapshot = "41-50"
        p_old.save()
        recent = f.event(team, when=dt.datetime(2026, 1, 10, 10, 0, tzinfo=UTC))
        p_new = f.person(recent, age=30)
        AuditLog.all_objects.create(company_id=company.id, action="old", object_type="x")
    return {"p_old": p_old, "p_new": p_new}


def test_retention_status_and_run(as_admin, company, aged):
    st = as_admin.get("/api/v1/company/retention").json()
    assert st["retention_identity_years"] == 2 and st["persons_due"] == 1 and st["last_run"] is None
    r = as_admin.patch("/api/v1/company/retention", {"retention_identity_years": 3}, format="json")
    assert r.status_code == 200 and r.json()["retention_identity_years"] == 3 and r.json()["persons_due"] == 1
    r = as_admin.post("/api/v1/company/retention/run")
    assert (
        r.status_code == 202
        and r.json()["status"] == "done"
        and r.json()["result"]["persons_anonymized"] == 1
    )
    p = as_admin.get(f"/api/v1/persons/{aged['p_old'].id}").json()
    assert (
        p["anonymized_at"] and p["age"] is None and p["initials_surname"] == "" and p["has_identity"] is False
    )
    assert p["age_class"] == "41-50"  # dato statistico conservato
    assert as_admin.get(f"/api/v1/persons/{aged['p_new'].id}").json()["age"] == 30
    st = as_admin.get("/api/v1/company/retention").json()
    assert (
        st["persons_due"] == 0
        and st["last_run"]["persons_anonymized"] == 1
        and st["persons_anonymized_total"] == 1
    )
    with tenant_context(company.id):
        assert AuditLog.objects.filter(action="person.anonymize").count() == 1


def test_retention_purges_old_audit_rows(company, aged, tenant):
    old_row = AuditLog.all_objects.get(action="old")
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SET LOCAL app.audit_purge = 'on'")
        cur.execute(
            "DELETE FROM audit_log WHERE id = %s", [old_row.pk]
        )  # verifica che il purge sia consentito
    assert not AuditLog.all_objects.filter(pk=old_row.pk).exists()
    res = retention.run_for_company(company)
    assert res["persons_anonymized"] == 1


def test_anonymize_on_request(as_admin, company, team, aged):
    p = aged["p_new"]
    r = as_admin.post(f"/api/v1/persons/{p.id}/anonymize", {"reason": "richiesta interessato"}, format="json")
    assert r.status_code == 200 and r.json()["anonymized_at"] and r.json()["age"] is None
    with tenant_context(company.id):
        log = AuditLog.objects.get(action="person.anonymize", object_id=p.id)
        assert log.metadata["reason"] == "richiesta interessato" and "age" in log.changed_fields


# --- hardening ------------------------------------------------------------------------------------


def test_security_headers_and_no_pii_in_url(as_admin, api_client):
    r = as_admin.get("/api/v1/me")
    assert r["X-Content-Type-Options"] == "nosniff" and r["Cache-Control"] == "no-store"
    assert r["Content-Security-Policy"].startswith("default-src 'none'") and r["X-Frame-Options"] == "DENY"
    r = as_admin.get("/api/v1/persons?surname=Rossi")
    assert r.status_code == 400 and r.json()["code"] == "pii_in_url"
    r = api_client.get("/api/v1/health")
    assert r["Referrer-Policy"] == "no-referrer"


def test_identity_endpoint_is_throttled(as_admin, company, team):
    with tenant_context(company.id):
        f.territory()
        p = f.person(f.event(team))
    codes = [as_admin.get(f"/api/v1/persons/{p.id}/identity").status_code for _ in range(31)]
    assert set(codes[:30]) == {404} and codes[30] == 429


def _walk(obj, path="") -> list[str]:  # noqa: ANN001
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PII_KEYS and v not in (None, "", [], {}):
                found.append(f"{path}.{k}")
            found += _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _walk(v, f"{path}[{i}]")
    return found


def test_no_pii_in_person_responses_or_audit(as_admin, company, team):
    """Le API restituiscono solo dati pseudonimizzati; l'audit non contiene valori personali."""
    with tenant_context(company.id):
        f.territory()
        ev = f.event(team)
    as_admin.post(
        f"/api/v1/events/{ev.id}/persons",
        {
            "age": 33,
            "initials_firstname": "MR",
            "pii": {
                "ciphertext": "AAEC",
                "key_wrapped": "AwQF",
                "key_version": 1,
                "fields": ["firstname", "phone"],
            },
        },
        format="json",
    )
    for url in (
        f"/api/v1/events/{ev.id}",
        "/api/v1/persons",
        f"/api/v1/events/{ev.id}/persons",
        "/api/v1/events",
    ):
        body = as_admin.get(url).json()
        leaks = [x for x in _walk(body) if not x.endswith(".pii_fields")]
        assert leaks == [], (url, leaks)
    with tenant_context(company.id):
        for row in AuditLog.objects.all():
            assert _walk(row.metadata) == [] and not (set(row.changed_fields) & {"pii_ciphertext_value"})
    # il serializer non accetta mai campi in chiaro
    r = as_admin.post(f"/api/v1/events/{ev.id}/persons", {"age": 1, "firstname": "Mario"}, format="json")
    assert r.status_code == 201 and "firstname" not in r.json()
