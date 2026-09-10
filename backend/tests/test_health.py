import pytest


@pytest.mark.django_db
def test_health_reports_postgis(api_client):
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["postgis"].startswith("3.")


def test_schema_is_generated(api_client):
    response = api_client.get("/api/schema/")
    assert response.status_code == 200
    assert b"openapi" in response.content
