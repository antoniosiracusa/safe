"""I CHECK basati su assert_lookup_dimension() vengono ricreati NOT VALID: PostgreSQL li applica comunque a
ogni INSERT/UPDATE, ma pg_dump li emette dopo i dati (post-data) invece che nel CREATE TABLE. Senza questo
un ripristino da backup falliva: `event` viene caricata prima di `lookup_value` e il CHECK, che interroga
quella tabella, respingeva tutte le righe (visto nella prova di ripristino del 12/09/2026)."""

import importlib

from django.db import migrations

# stessa lista di vincoli della migrazione che li ha creati (il nome del modulo inizia con una cifra)
LOOKUP_CHECKS = importlib.import_module("safe.apps.tenancy.migrations.0002_rls").LOOKUP_CHECKS


def _sql(valid: bool) -> str:
    suffix = "" if valid else " NOT VALID"
    return "\n".join(
        f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "chk_{table}_{column}_dim";\n'
        f'ALTER TABLE "{table}" ADD CONSTRAINT "chk_{table}_{column}_dim" '
        f"CHECK (assert_lookup_dimension({column}, '{dimension}')){suffix};"
        for table, column, dimension in LOOKUP_CHECKS
    )


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0003_lookup_fn_search_path")]
    operations = [migrations.RunSQL(_sql(valid=False), _sql(valid=True))]
