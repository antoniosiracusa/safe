"""Fixture comuni: società, utenti, token JWT firmati con una chiave di test (JWKS simulato)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from safe.apps.authn import jwt as authn_jwt
from safe.apps.authz.models import Permission, Role, UserPermission, UserRole
from safe.apps.org.models import AppUser, Team, UserTeam
from safe.apps.tenancy.context import bypass_tenant, tenant_context
from safe.apps.tenancy.models import Company

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_PEM = _PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)


@dataclass
class _FakeJWK:
    key: bytes


@pytest.fixture(autouse=True)
def _fake_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authn_jwt, "_signing_key", lambda token: _FakeJWK(key=_PUBLIC_PEM))


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    from django.core.cache import cache

    cache.clear()


def make_token(sub: str, email: str, *, expired: bool = False, audience: str | None = None) -> str:
    now = dt.datetime.now(dt.UTC)
    claims = {
        "iss": settings.OIDC_ISSUER,
        "aud": audience or settings.OIDC_AUDIENCE,
        "sub": sub,
        "email": email,
        "preferred_username": email,
        "iat": now - dt.timedelta(minutes=10),
        "exp": now + (dt.timedelta(minutes=-5) if expired else dt.timedelta(minutes=10)),
    }
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def company(db) -> Company:  # noqa: ANN001
    with bypass_tenant():
        return Company.objects.create(name="Società A", slug="a")


@pytest.fixture
def other_company(db) -> Company:  # noqa: ANN001
    with bypass_tenant():
        return Company.objects.create(name="Società B", slug="b")


def create_user(
    company: Company,
    email: str,
    *,
    roles: tuple[str, ...] = (),
    grants: tuple[str, ...] = (),
    denies: tuple[str, ...] = (),
    team: Team | None = None,
) -> AppUser:
    with tenant_context(company.id):
        user = AppUser.objects.create(
            email=email,
            oidc_subject=f"sub-{uuid.uuid4()}",
            status=AppUser.Status.ACTIVE,
            activated_at=timezone.now(),
        )
        for code in roles:
            UserRole.objects.create(user=user, role=Role.objects.get(code=code, company=None))
        for code in grants:
            UserPermission.objects.create(
                user=user, permission=Permission.objects.get(code=code), effect="grant"
            )
        for code in denies:
            UserPermission.objects.create(
                user=user, permission=Permission.objects.get(code=code), effect="deny"
            )
        if team is not None:
            UserTeam.objects.create(user=user, team=team, is_default=True)
        return user


@pytest.fixture
def team(company: Company) -> Team:
    with tenant_context(company.id):
        return Team.objects.create(name="Squadra A")


@pytest.fixture
def admin_user(company: Company, team: Team) -> AppUser:
    return create_user(company, "admin@a.test", roles=("company_admin",), team=team)


@pytest.fixture
def rescuer_user(company: Company, team: Team) -> AppUser:
    return create_user(company, "rescuer@a.test", roles=("rescuer",), team=team)


@pytest.fixture
def other_admin(other_company: Company) -> AppUser:
    return create_user(other_company, "admin@b.test", roles=("company_admin",))


def auth(client: APIClient, user: AppUser) -> APIClient:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(user.oidc_subject, user.email)}")
    return client


@pytest.fixture
def as_admin(api_client: APIClient, admin_user: AppUser) -> APIClient:
    return auth(api_client, admin_user)


@pytest.fixture
def as_rescuer(api_client: APIClient, rescuer_user: AppUser) -> APIClient:
    return auth(api_client, rescuer_user)


@pytest.fixture
def tenant(company: Company) -> Iterator[None]:
    with tenant_context(company.id):
        yield


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch):  # noqa: ANN001, ANN201
    """Nessun test tocca MinIO/S3: i job scrivono in memoria (vale anche per la mappa statica dei PDF)."""
    from safe.apps.jobs import runner, storage

    store: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: store.__setitem__(key, data))
    monkeypatch.setattr(storage, "get", lambda key: store[key])
    monkeypatch.setattr(storage, "exists", lambda key: key in store)
    monkeypatch.setattr(storage, "delete", lambda key: store.pop(key, None))
    monkeypatch.setattr(runner.storage, "put", storage.put)
    monkeypatch.setattr(runner.storage, "get", storage.get)
    monkeypatch.setattr("safe.apps.reports.static_map.static_map_data_uri", lambda *a, **k: None)
    return store
