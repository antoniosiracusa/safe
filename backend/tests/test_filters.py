import pytest

pytestmark = pytest.mark.django_db


def test_filter_options_scoped_to_tenant(as_admin, other_company):
    r = as_admin.get("/api/v1/filters/options")
    assert r.status_code == 200
    body = r.json()
    assert [t["label"] for t in body["teams"]] == ["Squadra A"]
    assert any(s["is_current"] for s in body["seasons"])
    assert body["ski_areas"] == [] and body["zones"] == []


def test_filter_options_first_season(as_admin, company):
    import datetime as dt

    from safe.apps.rescue.models import Season

    for year in (2023, 2024, 2025):
        Season.for_date(dt.date(year, 12, 1))
    assert min(s["value"] for s in as_admin.get("/api/v1/filters/options").json()["seasons"]) <= "2023/2024"
    r = as_admin.patch("/api/v1/company", {"settings": {"first_season": "2025/2026"}}, format="json")
    assert r.status_code == 200 and r.json()["settings"]["first_season"] == "2025/2026"
    codes = [s["value"] for s in as_admin.get("/api/v1/filters/options").json()["seasons"]]
    assert codes and min(codes) == "2025/2026"


def test_filter_options_requires_auth(api_client, company):
    assert api_client.get("/api/v1/filters/options").status_code == 401
