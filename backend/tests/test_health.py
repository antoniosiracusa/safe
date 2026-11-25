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


def test_api_docs_closed_when_disabled(settings):
    """In produzione (API_DOCS_ENABLED=False) schema e Swagger non sono instradati."""
    import importlib

    from django.urls import Resolver404, clear_url_caches, resolve

    import safe.urls

    settings.API_DOCS_ENABLED = False
    try:
        importlib.reload(safe.urls)
        clear_url_caches()
        for path in ("/api/schema/", "/api/docs/"):
            with pytest.raises(Resolver404):
                resolve(path)
        assert resolve("/api/v1/health")
    finally:
        settings.API_DOCS_ENABLED = True
        importlib.reload(safe.urls)
        clear_url_caches()
