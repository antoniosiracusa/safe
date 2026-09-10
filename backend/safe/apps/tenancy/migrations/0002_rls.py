"""Row Level Security su tutte le tabelle tenant + vincoli SQL non esprimibili con l'ORM.

Dipende dalle migrazioni iniziali di tutte le app: deve girare dopo la creazione delle tabelle.
"""

from django.db import migrations

from safe.apps.tenancy import rls

TENANT_TABLES = [
    "team", "app_user", "ski_area", "zone", "slope", "lift", "import_batch", "event", "person",
    "device_enrollment_code", "mobile_device", "user_key", "company_key", "company_key_grant",
    "company_key_recovery", "async_job", "export_run", "audit_log", "company_lookup_disabled",
]
CHILD_TABLES = [
    ("person_evacuation_mean", "person", "person_id"),
    ("person_diagnosis", "person", "person_id"),
    ("person_injury", "person", "person_id"),
    ("person_protection", "person", "person_id"),
    ("event_operator", "event", "event_id"),
    ("user_team", "app_user", "user_id"),
    ("user_role", "app_user", "user_id"),
    ("user_permission", "app_user", "user_id"),
]
GLOBAL_OR_TENANT_TABLES = ["lookup_value", "role"]

LOOKUP_DIMENSION_SQL = """
CREATE OR REPLACE FUNCTION assert_lookup_dimension(p_id uuid, p_dimension text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT p_id IS NULL OR EXISTS (SELECT 1 FROM lookup_value WHERE id = p_id AND dimension = p_dimension)
$$;
"""
LOOKUP_DIMENSION_REVERSE_SQL = "DROP FUNCTION IF EXISTS assert_lookup_dimension(uuid, text);"

LOOKUP_CHECKS = [
    ("team", "body_id", "team_body"),
    ("slope", "difficulty_id", "slope_difficulty"),
    ("event", "difficulty_id", "slope_difficulty"), ("event", "location_type_id", "location_type"),
    ("event", "cause_id", "cause"), ("event", "weather_id", "weather"),
    ("event", "snow_condition_id", "snow_condition"), ("event", "wind_id", "wind"),
    ("event", "visibility_id", "visibility"), ("event", "location_feature_id", "location_feature"),
    ("event", "traffic_id", "traffic"), ("event", "snow_making_id", "snow_making"),
    ("event", "event_type_id", "event_type"),
    ("person", "role_id", "person_role"), ("person", "gender_id", "gender"),
    ("person", "equipment_id", "equipment"), ("person", "equipment_owner_id", "equipment_owner"),
    ("person", "equipment_condition_id", "equipment_condition"), ("person", "insurance_id", "insurance"),
    ("person", "accommodation_id", "accommodation"), ("person", "destination_id", "destination"),
    ("person", "diagnosis_id", "diagnosis"), ("person", "gravest_injury_id", "body_part"),
    ("person", "injury_place_id", "injury_place"), ("person", "rescue_refusal_id", "rescue_refusal"),
    ("person", "responsibility_id", "responsibility"),
    ("person_evacuation_mean", "mean_id", "evacuation_mean"), ("person_diagnosis", "diagnosis_id", "diagnosis"),
    ("person_injury", "body_part_id", "body_part"), ("person_protection", "protection_id", "protection"),
]


def _check_ops():
    ops = []
    for table, column, dimension in LOOKUP_CHECKS:
        name = f"chk_{table}_{column}_dim"
        ops.append(migrations.RunSQL(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (assert_lookup_dimension({column}, '{dimension}'))",
            reverse_sql=f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}",
        ))
    return ops


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"), ("org", "0001_initial"), ("authz", "0001_initial"),
        ("lookups", "0001_initial"), ("territory", "0001_initial"), ("rescue", "0001_initial"),
        ("devices", "0001_initial"), ("crypto", "0001_initial"), ("jobs", "0001_initial"),
        ("audit", "0001_initial"),
    ]
    operations = [
        migrations.RunSQL(rls.FUNCTIONS_SQL, reverse_sql=rls.FUNCTIONS_REVERSE_SQL),
        rls.run_sql(rls.COMPANY_TABLE_SQL),
        *[rls.run_sql(rls.tenant_table_sql(t)) for t in TENANT_TABLES],
        *[rls.run_sql(rls.child_table_sql(t, p, c)) for t, p, c in CHILD_TABLES],
        *[rls.run_sql(rls.global_or_tenant_table_sql(t)) for t in GLOBAL_OR_TENANT_TABLES],
        migrations.RunSQL(LOOKUP_DIMENSION_SQL, reverse_sql=LOOKUP_DIMENSION_REVERSE_SQL),
        *_check_ops(),
    ]
