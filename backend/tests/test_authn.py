import pytest
from django.utils import timezone

from safe.apps.org.models import AppUser
from safe.apps.tenancy.context import tenant_context

from .conftest import make_token

pytestmark = pytest.mark.django_db


def test_me_returns_user_company_and_permission_map(as_admin, admin_user, company):
    r = as_admin.get("/api/v1/me")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["user"]["email"] == "admin@a.test"
    assert body["company"]["slug"] == "a"
    assert body["teams"][0]["name"] == "Squadra A"
    assert body["permissions"]["users.invite"] is True
    assert body["permissions"]["crypto.manage_keys"] is False
    assert body["permissions"]["crypto.holder"] is False
    assert "platform.admin" in body["permissions"]
    assert body["key_status"] == {"user_key": "missing", "company_key_version": None, "grant": "none"}


def test_missing_token_is_401(api_client, company):
    r = api_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "not_authenticated"


def test_expired_token_is_401(api_client, admin_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {make_token(admin_user.oidc_subject, admin_user.email, expired=True)}"
    )
    r = api_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "token_expired"


def test_wrong_audience_is_401(api_client, admin_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {make_token(admin_user.oidc_subject, admin_user.email, audience='other')}"
    )
    assert api_client.get("/api/v1/me").status_code == 401


def test_unknown_subject_is_403_not_provisioned(api_client, company):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token('sub-unknown', 'nobody@a.test')}")
    r = api_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "user_not_provisioned"


def test_invited_user_is_activated_on_first_login(api_client, company):
    with tenant_context(company.id):
        invited = AppUser.objects.create(
            email="new@a.test", status=AppUser.Status.INVITED, invited_at=timezone.now()
        )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token('sub-new', 'new@a.test')}")
    r = api_client.get("/api/v1/me")
    assert r.status_code == 200
    with tenant_context(company.id):
        invited.refresh_from_db()
    assert invited.status == AppUser.Status.ACTIVE
    assert invited.oidc_subject == "sub-new"


def test_disabled_user_is_rejected(api_client, admin_user, company):
    with tenant_context(company.id):
        admin_user.status = AppUser.Status.DISABLED
        admin_user.save()
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {make_token(admin_user.oidc_subject, admin_user.email)}"
    )
    r = api_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "user_disabled"


def test_patch_locale(as_admin):
    r = as_admin.patch("/api/v1/me", {"locale": "de"}, format="json")
    assert r.status_code == 200
    assert r.json()["user"]["locale"] == "de"
    assert as_admin.patch("/api/v1/me", {"locale": "xx"}, format="json").status_code == 400
