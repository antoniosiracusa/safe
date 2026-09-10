import pytest

pytestmark = pytest.mark.django_db


def test_filter_options_scoped_to_tenant(as_admin, other_company):
    r = as_admin.get("/api/v1/filters/options")
    assert r.status_code == 200
    body = r.json()
    assert [t["label"] for t in body["teams"]] == ["Squadra A"]
    assert any(s["is_current"] for s in body["seasons"])
    assert body["ski_areas"] == [] and body["zones"] == []


def test_filter_options_requires_auth(api_client, company):
    assert api_client.get("/api/v1/filters/options").status_code == 401
