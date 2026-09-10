import pytest

from safe.apps.authz.catalog import ALL_CODES, ROLE_TEMPLATES
from safe.apps.authz.models import Permission, Role
from safe.apps.lookups.models import DIMENSIONS, LookupValue
from safe.apps.lookups.seed import SEED

pytestmark = pytest.mark.django_db


def test_all_dimensions_seeded():
    seeded = set(LookupValue.objects.values_list("dimension", flat=True).distinct())
    assert seeded == set(DIMENSIONS)
    for dimension, rows in SEED.items():
        assert LookupValue.objects.filter(dimension=dimension).count() == len(rows)


def test_body_parts_have_injury_place_parent():
    parts = LookupValue.objects.filter(dimension="body_part").select_related("parent")
    assert parts.exists()
    assert all(p.parent is not None and p.parent.dimension == "injury_place" for p in parts)


def test_permissions_and_roles_seeded():
    assert set(Permission.objects.values_list("code", flat=True)) == set(ALL_CODES)
    for code, spec in ROLE_TEMPLATES.items():
        role = Role.objects.get(code=code, company=None)
        assert set(role.permissions.values_list("code", flat=True)) == set(spec["permissions"])


def test_role_permissions_exist_in_catalog():
    for spec in ROLE_TEMPLATES.values():
        assert set(spec["permissions"]) <= set(ALL_CODES)
