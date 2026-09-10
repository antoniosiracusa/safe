"""Generazione SQL per Row Level Security, usata dalle migrazioni.

Policy: una riga è visibile/modificabile se `company_id` coincide con `app.company_id`
(impostato con SET LOCAL da tenant_context) oppure se `app.bypass_rls = 'on'`
(solo bypass_tenant, per migrazioni e comandi di piattaforma).
"""

from django.db.migrations.operations.special import RunSQL

FUNCTIONS_SQL = """
CREATE OR REPLACE FUNCTION current_company_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.company_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION rls_bypass() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(current_setting('app.bypass_rls', true), 'off') = 'on'
$$;
"""

FUNCTIONS_REVERSE_SQL = """
DROP FUNCTION IF EXISTS rls_bypass();
DROP FUNCTION IF EXISTS current_company_id();
"""


def tenant_table_sql(table: str) -> tuple[str, str]:
    forward = f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
  USING (rls_bypass() OR company_id = current_company_id())
  WITH CHECK (rls_bypass() OR company_id = current_company_id());
"""
    reverse = f"""
DROP POLICY IF EXISTS tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    return forward, reverse


def child_table_sql(table: str, parent_table: str, fk_column: str) -> tuple[str, str]:
    """Tabelle figlie senza company_id: visibili se la riga padre è visibile."""
    forward = f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS via_parent ON {table};
CREATE POLICY via_parent ON {table}
  USING (rls_bypass() OR EXISTS (SELECT 1 FROM {parent_table} p WHERE p.id = {table}.{fk_column}))
  WITH CHECK (rls_bypass() OR EXISTS (SELECT 1 FROM {parent_table} p WHERE p.id = {table}.{fk_column}));
"""
    reverse = f"""
DROP POLICY IF EXISTS via_parent ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    return forward, reverse


def global_or_tenant_table_sql(table: str) -> tuple[str, str]:
    """Tabelle con righe globali (company_id NULL) più righe di società."""
    forward = f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS global_or_tenant ON {table};
CREATE POLICY global_or_tenant ON {table}
  USING (rls_bypass() OR company_id IS NULL OR company_id = current_company_id())
  WITH CHECK (rls_bypass() OR company_id = current_company_id());
"""
    reverse = f"""
DROP POLICY IF EXISTS global_or_tenant ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    return forward, reverse


COMPANY_TABLE_SQL = (
    """
ALTER TABLE company ENABLE ROW LEVEL SECURITY;
ALTER TABLE company FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_self ON company;
CREATE POLICY tenant_self ON company
  USING (rls_bypass() OR id = current_company_id())
  WITH CHECK (rls_bypass() OR id = current_company_id());
""",
    """
DROP POLICY IF EXISTS tenant_self ON company;
ALTER TABLE company NO FORCE ROW LEVEL SECURITY;
ALTER TABLE company DISABLE ROW LEVEL SECURITY;
""",
)


def run_sql(pair: tuple[str, str]) -> RunSQL:
    return RunSQL(pair[0], reverse_sql=pair[1])
