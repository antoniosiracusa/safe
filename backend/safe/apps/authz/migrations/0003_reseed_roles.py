"""Riallinea i ruoli di sistema al catalogo (safe.apps.authz.catalog.ROLE_TEMPLATES) dopo la modifica del
12/09/2026: Responsabile soccorso e Analista vedono solo gli eventi delle proprie squadre
(events.view_own_teams_only), come il Soccorritore; il Responsabile perde events.edit_any_team.
Riesegue il seed della migrazione 0002 (idempotente: ricrea i permessi dei soli ruoli di sistema)."""

import importlib

from django.db import migrations

seed = importlib.import_module("safe.apps.authz.migrations.0002_seed").seed


class Migration(migrations.Migration):
    dependencies = [("authz", "0002_seed")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
