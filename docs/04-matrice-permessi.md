# 04 · Matrice dei permessi

## 1. Modello

- I permessi sono **codici stringa** (`modulo.azione`) registrati nella tabella `permission`
  e nel codice (`safe/authz/permissions.py`, sorgente unica; una migrazione li sincronizza).
- I **ruoli** sono template di permessi, globali (forniti dalla piattaforma) o definiti dalla
  società. Un utente può avere più ruoli più grant/deny diretti.
- Permessi effettivi = ⋃ permessi dei ruoli ∪ grant diretti − deny diretti.
- `GET /api/v1/me` restituisce `permissions` come mappa `{codice: bool}` con **tutti** i codici
  noti, così la UI sa cosa mostrare bloccato.
- Ogni rotta dichiara i permessi richiesti (`x-permissions` in OpenAPI). Un test parametrizzato
  chiama ogni rotta con un utente privo del permesso e verifica `403` e corpo vuoto.
- Scoping per squadra: `events.view_own_teams_only` (restrizione) e `events.edit_any_team`
  (estensione) modificano il queryset, non solo l'accesso.
- `crypto.holder` non è un permesso assegnabile: è **derivato** dall'esistenza di una
  `company_key_grant` attiva. Compare nella mappa per comodità della UI.

## 2. Catalogo permessi

| Codice | Modulo | Descrizione | Note |
|---|---|---|---|
| `stats.view` | statistiche | Vede tutte le pagine statistiche | |
| `stats.advanced` | statistiche | Riepilogo stagione per squadra, tabella duplicati | "pro" |
| `stats.cross_company` | statistiche | Aggregati su più società (tenant `authority`) | futuro |
| `map.view` | mappa | Mappa eventi, layer, GeoJSON | |
| `map.realtime` | mappa | Canale WebSocket posizioni mezzi | futuro |
| `events.view` | rescue | Lista/dettaglio eventi (pseudonimi) | |
| `events.view_own_teams_only` | rescue | Restringe `events.view` alle proprie squadre | restrizione |
| `events.create` | rescue | Crea eventi (web e mobile) | |
| `events.edit` | rescue | Modifica eventi delle proprie squadre non bloccati | |
| `events.edit_any_team` | rescue | Modifica eventi di qualsiasi squadra | |
| `events.delete` | rescue | Elimina (soft delete) eventi | |
| `events.unlock` | rescue | Sblocca eventi bloccati | audit |
| `persons.view` | rescue | Vede persone pseudonimizzate | |
| `persons.edit` | rescue | Crea/modifica persone (cifra lato client) | |
| `persons.reveal_identity` | rescue | Ottiene ciphertext + chiave avvolta (decifra solo se `crypto.holder`) | audit ogni lettura |
| `reports.pdf` | rescue | Genera/scarica PDF rapporto | audit |
| `exports.dataset` | export | Export CSV/XLSX dataset filtrati | audit |
| `exports.regional` | export | Anteprima e generazione export regionale | audit |
| `exports.view_duplicates` | export | Vede l'elenco dei duplicati raggruppati | |
| `import.historical` | rescue | Import storico CSV/XLSX | audit |
| `users.view` | organizzazione | Lista utenti, inviti, disattivati | |
| `users.invite` | organizzazione | Invita utenti via email | audit |
| `users.manage` | organizzazione | Disattiva/riattiva, cambia squadre | audit |
| `users.assign_permissions` | organizzazione | Assegna ruoli e grant | audit |
| `teams.view` | organizzazione | Lista squadre | |
| `teams.manage` | organizzazione | CRUD squadre | |
| `company.settings` | organizzazione | Impostazioni società (regole validità, lock, template export) | |
| `company.retention` | organizzazione | Politiche di retention, esecuzione anonimizzazione | audit |
| `territory.view` | territorio | Comprensori, zone, piste | |
| `territory.manage` | territorio | CRUD comprensori, zone, piste, confini | |
| `lookups.manage` | territorio | Personalizza vocabolari controllati | |
| `devices.view` | dispositivi | Lista dispositivi | |
| `devices.manage` | dispositivi | Rinomina, revoca | |
| `devices.authorize` | dispositivi | Approva dispositivi in attesa | |
| `crypto.manage_keys` | cifratura | Crea chiave società, concede/revoca grant, rotazione | audit, MFA |
| `crypto.recovery` | cifratura | Esegue procedura di recupero | audit, MFA |
| `audit.view` | audit | Consulta audit log | |
| `filter_by_administrative_area` | export | Filtro per area amministrativa ISTAT nelle statistiche | |
| `platform.admin` | piattaforma | Crea società, gestisce piattaforma | ruolo DB separato |

## 3. Ruoli template

| Permesso | Amministratore | Responsabile soccorso | Soccorritore | Analista | Custode chiavi / DPO | Ente pubblico (futuro) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| stats.view | ● | ● | | ● | | ● |
| stats.advanced | ● | ● | | ● | | |
| stats.cross_company | | | | | | ● |
| map.view | ● | ● | ● | ● | | ● |
| map.realtime | ● | ● | | | | |
| events.view | ● | ● | ● | ● | ● | |
| events.view_own_teams_only | | | ● | | | |
| events.create | ● | ● | ● | | | |
| events.edit | ● | ● | ● | | | |
| events.edit_any_team | ● | ● | | | | |
| events.delete | ● | ● | | | | |
| events.unlock | ● | ● | | | | |
| persons.view | ● | ● | ● | ● | ● | |
| persons.edit | ● | ● | ● | | | |
| persons.reveal_identity | ● | ● | ●¹ | | ● | |
| reports.pdf | ● | ● | ● | ● | | |
| exports.dataset | ● | ● | | ● | | ● |
| exports.regional | ● | ● | | | | |
| exports.view_duplicates | ● | ● | | ● | | |
| import.historical | ● | | | | | |
| users.view / invite / manage | ● | | | | | |
| users.assign_permissions | ● | | | | | |
| teams.view | ● | ● | ● | ● | | |
| teams.manage | ● | ● | | | | |
| company.settings | ● | | | | | |
| company.retention | ● | | | | ● | |
| territory.view | ● | ● | ● | ● | | ● |
| territory.manage | ● | ● | | | | |
| lookups.manage | ● | | | | | |
| devices.view / manage / authorize | ● | ● | | | | |
| crypto.manage_keys | | | | | ● | |
| crypto.recovery | | | | | ● | |
| audit.view | ● | | | | ● | |
| filter_by_administrative_area | | | | | | ● |

¹ Il soccorritore ottiene ciphertext solo per persone di eventi delle proprie squadre e decifra solo se ha una grant (tipicamente per completare il rapporto del giorno).

## 4. Permessi per funzionalità (vista UI)

| Funzionalità / schermata | Permesso richiesto | Comportamento senza permesso |
|---|---|---|
| Home KPI | nessuno | mostra solo card bloccate dei moduli non abilitati |
| Statistiche · tutte le pagine | `stats.view` | pagina visibile, grafici sostituiti da pannello "Funzione non abilitata" |
| Statistiche · Riepilogo stagione | `stats.advanced` | tabella bloccata con messaggio |
| Dati · Eventi | `events.view` | tabella bloccata |
| Dati · Persone | `persons.view` | tabella bloccata |
| Dettaglio persona · "Mostra identità" | `persons.reveal_identity` + grant | pulsante disabilitato con tooltip ("chiave non disponibile" / "permesso mancante") |
| Pulsante PDF | `reports.pdf` | disabilitato |
| Mappa | `map.view` | pagina bloccata |
| Esportazioni · Regionale | `exports.regional` | wizard bloccato |
| Esportazioni · Dataset | `exports.dataset` | bloccato |
| Gestione · Utenti | `users.view` (+ `users.invite`, `users.manage`, `users.assign_permissions` per le azioni) | lista visibile o bloccata; azioni disabilitate |
| Gestione · Squadre | `teams.view` / `teams.manage` | idem |
| Gestione · Dispositivi | `devices.view` / `devices.manage` / `devices.authorize` | idem |
| Gestione · Territorio, Vocabolari | `territory.manage`, `lookups.manage` | idem |
| Impostazioni società | `company.settings` | bloccata |
| Chiavi di cifratura | `crypto.manage_keys` | la propria chiave utente è gestibile da chiunque; le grant no |
| Audit log | `audit.view` | bloccata |

## 5. Test automatici derivati

- `tests/authz/test_matrix.py`: per ogni operazione OpenAPI (letta dallo schema generato) ×
  per ogni permesso richiesto, crea un utente con **tutti gli altri** permessi e verifica
  `403` con corpo `{"detail": "...", "code": "permission_denied", "missing": ["…"]}` e nessun dato.
- `tests/authz/test_tenant.py`: per ogni rotta con `{id}`, chiama con l'id di un oggetto di
  un'altra società e verifica `404` (mai `403`, per non rivelare l'esistenza).
- `tests/authz/test_identity.py`: nessuna risposta contiene `firstname`/`surname` in chiaro,
  neppure per l'amministratore; `identity` restituisce solo ciphertext e chiavi avvolte.
