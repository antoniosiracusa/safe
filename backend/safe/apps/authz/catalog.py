"""Catalogo dei permessi: sorgente unica (docs/04-matrice-permessi.md), sincronizzato in tabella."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Perm:
    code: str
    module: str
    description: str
    audited: bool = False


PERMISSIONS: tuple[Perm, ...] = (
    Perm("stats.view", "stats", "Vede tutte le pagine statistiche"),
    Perm("stats.advanced", "stats", "Riepilogo stagione per squadra, tabella duplicati"),
    Perm("stats.cross_company", "stats", "Aggregati su più società (tenant ente)"),
    Perm("map.view", "map", "Mappa eventi, layer, GeoJSON"),
    Perm("map.realtime", "map", "Canale WebSocket posizioni mezzi"),
    Perm("events.view", "rescue", "Lista e dettaglio eventi (pseudonimi)"),
    Perm("events.view_own_teams_only", "rescue", "Restringe la lettura alle proprie squadre"),
    Perm("events.create", "rescue", "Crea eventi"),
    Perm("events.edit", "rescue", "Modifica eventi delle proprie squadre non bloccati"),
    Perm("events.edit_any_team", "rescue", "Modifica eventi di qualsiasi squadra"),
    Perm("events.delete", "rescue", "Elimina eventi"),
    Perm("events.unlock", "rescue", "Sblocca eventi bloccati", audited=True),
    Perm("persons.view", "rescue", "Vede persone pseudonimizzate"),
    Perm("persons.edit", "rescue", "Crea e modifica persone"),
    Perm("persons.reveal_identity", "rescue", "Ottiene i dati identificativi cifrati", audited=True),
    Perm("reports.pdf", "rescue", "Genera e scarica il PDF del rapporto", audited=True),
    Perm("exports.dataset", "exports", "Export CSV/XLSX dei dataset", audited=True),
    Perm("exports.regional", "exports", "Anteprima e generazione export regionale", audited=True),
    Perm("exports.view_duplicates", "exports", "Vede i duplicati raggruppati"),
    Perm("import.historical", "rescue", "Import storico", audited=True),
    Perm("users.view", "org", "Lista utenti"),
    Perm("users.invite", "org", "Invita utenti", audited=True),
    Perm("users.manage", "org", "Disattiva, riattiva, cambia squadre", audited=True),
    Perm("users.assign_permissions", "org", "Assegna ruoli e permessi", audited=True),
    Perm("teams.view", "org", "Lista squadre"),
    Perm("teams.manage", "org", "Gestione squadre"),
    Perm("company.settings", "org", "Impostazioni società"),
    Perm("company.retention", "org", "Politiche di retention", audited=True),
    Perm("territory.view", "territory", "Comprensori, zone, piste"),
    Perm("territory.manage", "territory", "Gestione comprensori, zone, piste"),
    Perm("lookups.manage", "territory", "Personalizza i vocabolari"),
    Perm("devices.view", "devices", "Lista dispositivi"),
    Perm("devices.manage", "devices", "Rinomina e revoca dispositivi"),
    Perm("devices.authorize", "devices", "Autorizza dispositivi"),
    Perm("crypto.manage_keys", "crypto", "Chiave società, grant, rotazione", audited=True),
    Perm("crypto.recovery", "crypto", "Procedura di recupero chiavi", audited=True),
    Perm("audit.view", "audit", "Consulta l'audit log"),
    Perm("filter_by_administrative_area", "exports", "Filtro per area amministrativa ISTAT"),
    Perm("platform.admin", "platform", "Amministrazione della piattaforma"),
)

ALL_CODES: tuple[str, ...] = tuple(p.code for p in PERMISSIONS)

# Permessi derivati, non assegnabili: calcolati a runtime.
DERIVED_CODES: tuple[str, ...] = ("crypto.holder",)

# Ruoli template globali (docs/04-matrice-permessi.md §3)
ROLE_TEMPLATES: dict[str, dict[str, object]] = {
    "company_admin": {
        "name": {"it": "Amministratore", "en": "Administrator", "de": "Administrator"},
        "permissions": [
            "stats.view",
            "stats.advanced",
            "map.view",
            "map.realtime",
            "events.view",
            "events.create",
            "events.edit",
            "events.edit_any_team",
            "events.delete",
            "events.unlock",
            "persons.view",
            "persons.edit",
            "persons.reveal_identity",
            "reports.pdf",
            "exports.dataset",
            "exports.regional",
            "exports.view_duplicates",
            "import.historical",
            "users.view",
            "users.invite",
            "users.manage",
            "users.assign_permissions",
            "teams.view",
            "teams.manage",
            "company.settings",
            "company.retention",
            "territory.view",
            "territory.manage",
            "lookups.manage",
            "devices.view",
            "devices.manage",
            "devices.authorize",
            "audit.view",
        ],
    },
    "rescue_manager": {
        "name": {"it": "Responsabile soccorso", "en": "Rescue manager", "de": "Rettungsleiter"},
        "permissions": [
            "stats.view",
            "stats.advanced",
            "map.view",
            "map.realtime",
            "events.view",
            "events.view_own_teams_only",
            "events.create",
            "events.edit",
            "events.delete",
            "events.unlock",
            "persons.view",
            "persons.edit",
            "persons.reveal_identity",
            "reports.pdf",
            "exports.dataset",
            "exports.regional",
            "exports.view_duplicates",
            "teams.view",
            "teams.manage",
            "territory.view",
            "territory.manage",
            "devices.view",
            "devices.manage",
            "devices.authorize",
        ],
    },
    "rescuer": {
        "name": {"it": "Soccorritore", "en": "Rescuer", "de": "Retter"},
        "permissions": [
            "map.view",
            "events.view",
            "events.view_own_teams_only",
            "events.create",
            "events.edit",
            "persons.view",
            "persons.edit",
            "persons.reveal_identity",
            "reports.pdf",
            "teams.view",
            "territory.view",
        ],
    },
    "analyst": {
        "name": {"it": "Analista", "en": "Analyst", "de": "Analyst"},
        "permissions": [
            "stats.view",
            "stats.advanced",
            "map.view",
            "events.view",
            "events.view_own_teams_only",
            "persons.view",
            "reports.pdf",
            "exports.dataset",
            "exports.view_duplicates",
            "teams.view",
            "territory.view",
        ],
    },
    "key_custodian": {
        "name": {"it": "Custode chiavi / DPO", "en": "Key custodian / DPO", "de": "Schlüsselverwalter / DSB"},
        "permissions": [
            "events.view",
            "persons.view",
            "persons.reveal_identity",
            "company.retention",
            "crypto.manage_keys",
            "crypto.recovery",
            "audit.view",
        ],
    },
    "authority": {
        "name": {"it": "Ente pubblico", "en": "Public authority", "de": "Behörde"},
        "permissions": [
            "stats.view",
            "stats.cross_company",
            "map.view",
            "exports.dataset",
            "territory.view",
            "filter_by_administrative_area",
        ],
    },
}
