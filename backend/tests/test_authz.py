import pytest
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.resolve import effective_permissions

from .conftest import auth, create_user

pytestmark = [pytest.mark.django_db, pytest.mark.authz]


class _ProtectedView(APIView):
    required_permissions = ("events.unlock",)

    def get(self, request):  # noqa: ANN001, ANN201
        return Response({"secret": True})


def test_role_union_grant_deny(company, tenant):
    user = create_user(
        company, "x@a.test", roles=("rescuer",), grants=("exports.regional",), denies=("events.edit",)
    )
    perms = effective_permissions(user)
    assert "events.view" in perms  # dal ruolo
    assert "exports.regional" in perms  # grant diretto
    assert "events.edit" not in perms  # deny vince sul ruolo
    assert "users.invite" not in perms


def test_missing_permission_returns_403_without_data(api_client, rescuer_user, company, settings):
    from django.urls import path

    from safe import urls as root_urls

    root_urls.urlpatterns.append(path("api/v1/_test/protected", _ProtectedView.as_view()))
    try:
        from django.urls import clear_url_caches

        clear_url_caches()
        r = auth(api_client, rescuer_user).get("/api/v1/_test/protected")
        assert r.status_code == 403
        body = r.json()
        assert body["code"] == "permission_denied"
        assert body["missing"] == ["events.unlock"]
        assert "secret" not in body
    finally:
        root_urls.urlpatterns.pop()
        clear_url_caches()


def test_permission_cache_invalidated_on_change(company, tenant):
    from safe.apps.authz.models import Permission, UserPermission
    from safe.apps.authz.resolve import invalidate
    from safe.apps.tenancy.context import tenant_context

    user = create_user(company, "y@a.test", roles=("analyst",))
    assert "events.delete" not in effective_permissions(user)
    with tenant_context(company.id):
        UserPermission.objects.create(
            user=user, permission=Permission.objects.get(code="events.delete"), effect="grant"
        )
    invalidate(user.id)
    assert "events.delete" in effective_permissions(user)


def test_permissions_are_empty_outside_tenant_context(company):
    """Fuori dal contesto tenant (nessuna richiesta autenticata) la RLS non espone ruoli né grant."""
    user = create_user(company, "z@a.test", roles=("company_admin",))
    assert effective_permissions(user) == frozenset()
