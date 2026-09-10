from django.db import migrations

from safe.apps.authz.catalog import PERMISSIONS, ROLE_TEMPLATES


def seed(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Role = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")
    with schema_editor.connection.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    for p in PERMISSIONS:
        Permission.objects.update_or_create(
            code=p.code, defaults={"module": p.module, "description": p.description, "is_audited": p.audited}
        )
    for code, spec in ROLE_TEMPLATES.items():
        names = spec["name"]
        role, _ = Role.objects.update_or_create(
            code=code, company=None,
            defaults={"name_it": names["it"], "name_en": names["en"], "name_de": names["de"], "is_system": True},
        )
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission_id=perm) for perm in spec["permissions"]]
        )


def unseed(apps, schema_editor):
    apps.get_model("authz", "Role").objects.filter(company=None).delete()
    apps.get_model("authz", "Permission").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("authz", "0001_initial"), ("tenancy", "0002_rls")]
    operations = [migrations.RunPython(seed, unseed)]
