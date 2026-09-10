from django.db import migrations

from safe.apps.lookups.seed import BODY_PARTS, COUNTRIES, SEED


def seed(apps, schema_editor):
    LookupValue = apps.get_model("lookups", "LookupValue")
    Country = apps.get_model("lookups", "Country")
    with schema_editor.connection.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    for dimension, rows in SEED.items():
        for code, it, en, de, sort, mapping in rows:
            LookupValue.objects.update_or_create(
                dimension=dimension, code=code, company=None,
                defaults={"label_it": it, "label_en": en, "label_de": de, "sort_order": sort, "mapping": mapping},
            )
    places = {v.code: v for v in LookupValue.objects.filter(dimension="injury_place", company=None)}
    for code, it, en, de, sort, parent in BODY_PARTS:
        LookupValue.objects.update_or_create(
            dimension="body_part", code=code, company=None,
            defaults={"label_it": it, "label_en": en, "label_de": de, "sort_order": sort, "parent": places[parent]},
        )
    for code, it, en, de, eu in COUNTRIES:
        Country.objects.update_or_create(code=code, defaults={"name_it": it, "name_en": en, "name_de": de, "is_eu": eu})


def unseed(apps, schema_editor):
    LookupValue = apps.get_model("lookups", "LookupValue")
    LookupValue.objects.filter(company=None).delete()


class Migration(migrations.Migration):
    dependencies = [("lookups", "0001_initial"), ("tenancy", "0002_rls")]
    operations = [migrations.RunPython(seed, unseed)]
