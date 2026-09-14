"""Vocabolari "condizioni generali" e "primo soccorso prestato" (richiesta del Consorzio, 14/09/2026)."""

from django.db import migrations

from safe.apps.lookups.seed import SEED

NEW_DIMENSIONS = ("condition", "first_aid")


def seed(apps, schema_editor):
    LookupValue = apps.get_model("lookups", "LookupValue")
    with schema_editor.connection.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    for dimension in NEW_DIMENSIONS:
        for code, it, en, de, sort, mapping in SEED[dimension]:
            LookupValue.objects.update_or_create(
                dimension=dimension, code=code, company=None,
                defaults={"label_it": it, "label_en": en, "label_de": de, "sort_order": sort, "mapping": mapping},
            )


def unseed(apps, schema_editor):
    LookupValue = apps.get_model("lookups", "LookupValue")
    LookupValue.objects.filter(dimension__in=NEW_DIMENSIONS, company=None).delete()


class Migration(migrations.Migration):
    dependencies = [("lookups", "0002_seed")]
    operations = [migrations.RunPython(seed, unseed)]
