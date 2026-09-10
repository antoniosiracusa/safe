import datetime as dt

import pytest
from django.contrib.gis.geos import LineString, MultiLineString, MultiPolygon, Polygon

from safe.apps.tenancy.context import tenant_context
from safe.apps.territory.models import Lift

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def geo(company, team):  # noqa: ANN001, ANN201
    with tenant_context(company.id):
        area, zone, slope = f.territory()
        area.boundary = MultiPolygon(
            Polygon(((12.0, 46.4), (12.2, 46.4), (12.2, 46.5), (12.0, 46.5), (12.0, 46.4)))
        )
        area.save()
        slope.geom = MultiLineString(LineString((12.09, 46.46), (12.10, 46.45)))
        slope.save()
        Lift.objects.create(
            ski_area=area,
            name="Seggiovia Fertazza",
            lift_type="chairlift",
            geom=LineString((12.08, 46.45), (12.09, 46.47)),
        )
        e1 = f.event(team, when=dt.datetime(2026, 1, 18, 10, 5, tzinfo=dt.UTC))
        f.person(e1)
        f.event(team, when=dt.datetime(2026, 2, 1, 9, 0, tzinfo=dt.UTC), complete=False)  # senza geometria
        return {"e1": e1, "area": area}


def test_events_geojson_only_id_and_datetime(as_admin, geo):
    r = as_admin.get("/api/v1/map/events.geojson?season=2025/2026")
    assert r.status_code == 200 and r["Content-Type"].startswith("application/geo+json")
    body = r.json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 1
    feat = body["features"][0]
    assert feat["geometry"] == {"type": "Point", "coordinates": [12.0912, 46.4581]}
    assert set(feat["properties"]) == {"id", "dateandtime"}
    assert feat["properties"]["id"] == str(geo["e1"].id)


def test_events_geojson_respects_filters_and_tenant(as_admin, geo, other_company):
    assert as_admin.get("/api/v1/map/events.geojson?season=2024/2025").json()["features"] == []
    from safe.apps.org.models import Team

    with tenant_context(other_company.id):
        t = Team.objects.create(name="B1")
        f.event(t)
    assert len(as_admin.get("/api/v1/map/events.geojson").json()["features"]) == 1


def test_layers_geojson(as_admin, geo):
    areas = as_admin.get("/api/v1/map/ski-areas.geojson").json()
    assert areas["features"][0]["properties"]["name"] == "Civetta"
    assert areas["features"][0]["geometry"]["type"] == "MultiPolygon"
    slopes = as_admin.get("/api/v1/map/slopes.geojson").json()
    assert slopes["features"][0]["properties"] == {
        "id": slopes["features"][0]["id"],
        "name": "LE CIAUNE",
        "regional_code": "C.1.24",
        "difficulty": "blue",
        "zone": "Val Fiorentina",
    }
    lifts = as_admin.get("/api/v1/map/lifts.geojson").json()
    assert lifts["features"][0]["properties"]["lift_type"] == "chairlift"


def test_styles_and_permission(as_admin, api_client, company, team, geo):
    body = as_admin.get("/api/v1/map/styles").json()
    assert body["provider"] == "mapbox" and [s["code"] for s in body["styles"]] == [
        "winter",
        "summer",
        "satellite",
    ]
    assert all(s["url"].startswith("mapbox://styles/") for s in body["styles"])
    user = create_user(company, "nomap@a.test", roles=("key_custodian",), team=team)
    r = auth(api_client, user).get("/api/v1/map/events.geojson")
    assert r.status_code == 403 and r.json()["missing"] == ["map.view"]
