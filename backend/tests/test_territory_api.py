import pytest

from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db


def test_territory_lists_scoped_and_filtered(as_admin, company, other_company):
    with tenant_context(company.id):
        area, zone, slope = f.territory()
        f.territory(zone_name="Val di Zoldo", slope_name="Lendina")
    with tenant_context(other_company.id):
        f.territory(area_name="Altrove", zone_name="Z", slope_name="S")
    assert [a["name"] for a in as_admin.get("/api/v1/ski-areas").json()] == ["Civetta"]
    zones = as_admin.get(f"/api/v1/zones?ski_area={area.id}").json()
    assert sorted(z["name"] for z in zones) == ["Val Fiorentina", "Val di Zoldo"]
    slopes = as_admin.get(f"/api/v1/slopes?zone={zone.id}").json()
    assert slopes == [
        {
            "id": str(slope.id),
            "name": "LE CIAUNE",
            "regional_code": "C.1.24",
            "difficulty": "blue",
            "zone": {"id": str(zone.id), "name": "Val Fiorentina", "ski_area": str(area.id)},
            "has_geometry": False,
            "is_active": True,
        }
    ]
    assert len(as_admin.get("/api/v1/slopes?search=lend").json()) == 1


def test_territory_requires_permission(api_client, company):
    user = create_user(company, "noterr@a.test", roles=("key_custodian",))
    r = auth(api_client, user).get("/api/v1/slopes")
    assert r.status_code == 403 and r.json()["missing"] == ["territory.view"]
