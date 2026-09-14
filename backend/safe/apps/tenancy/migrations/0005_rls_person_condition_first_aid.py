"""RLS e vincoli di dimensione per le nuove tabelle figlie di `person`: condizioni generali e primo soccorso
prestato (rescue.0003). Stesse regole di 0002_rls (politiche tramite la persona) e di 0004 (CHECK NOT VALID)."""

from django.db import migrations

from safe.apps.tenancy import rls

CHILD_TABLES = [
    ("person_condition", "person", "person_id"),
    ("person_first_aid", "person", "person_id"),
]
LOOKUP_CHECKS = [
    ("person_condition", "condition_id", "condition"),
    ("person_first_aid", "first_aid_id", "first_aid"),
]


def _check_sql(valid: bool) -> str:
    suffix = "" if valid else " NOT VALID"
    return "\n".join(
        f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "chk_{table}_{column}_dim";\n'
        f'ALTER TABLE "{table}" ADD CONSTRAINT "chk_{table}_{column}_dim" '
        f"CHECK (assert_lookup_dimension({column}, '{dimension}')){suffix};"
        for table, column, dimension in LOOKUP_CHECKS
    )


def _drop_sql() -> str:
    return "\n".join(
        f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "chk_{table}_{column}_dim";'
        for table, column, _ in LOOKUP_CHECKS
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0004_lookup_checks_not_valid"),
        ("rescue", "0003_person_condition_first_aid"),
    ]
    operations = [
        *[rls.run_sql(rls.child_table_sql(t, p, c)) for t, p, c in CHILD_TABLES],
        migrations.RunSQL(_check_sql(valid=False), _drop_sql()),
    ]
