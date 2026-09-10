# Runbook M6 · Gestione (utenti, squadre, dispositivi, territorio, vocabolari, impostazioni)

## Cosa c'è

**Utenti** (`users.view` / `users.invite` / `users.manage` / `users.assign_permissions`)

- `POST /users/invite`: crea l'utente in Keycloak tramite la **Admin REST API** (client di servizio
  `safe-admin`, credenziali in `.env`), gli invia l'email "imposta password" (+ "configura OTP" se
  `mfa_required`), crea l'`AppUser` in stato `invited` con squadre e ruoli; al primo login OIDC l'utente
  diventa `active` (già in M1). Se Keycloak fallisce, nulla viene salvato (transazione) e la risposta
  riporta `keycloak_unavailable`. Email già presente → 409 `email_in_use`.
- `PATCH /users/{id}` (nome, lingua, MFA, squadre e squadra predefinita), `POST …/resend-invite`,
  `POST …/disable` (utente disabilitato in Keycloak + sessioni revocate + cache di autenticazione
  invalidata: il token successivo riceve 401 `user_disabled`), `POST …/enable`.
- `PUT /users/{id}/permissions` `{roles, grants, denies}`: sostituisce ruoli e permessi diretti e invalida
  la cache dei permessi; non si può negare a sé stessi `users.assign_permissions`, né disattivarsi.
- `GET /roles` (template globali + ruoli della società), `POST /roles` (ruolo personalizzato).
- Pagina Utenti: tab Attivi / Inviti / Disattivati, ricerca, dialogo invito/modifica con squadre,
  ruoli e griglia dei permessi (Ruolo / Concedi / Nega per ogni codice, con evidenza di quelli già
  inclusi nei ruoli), reinvio invito, disattivazione con conferma.

**Squadre** (`teams.view` / `teams.manage`): CRUD con conteggio utenti ed eventi; la disattivazione è
bloccata (`team_has_events`) se la squadra ha eventi; nomi univoci per società.

**Dispositivi** (`devices.view` / `devices.manage` / `devices.authorize`)

- `POST /devices/enrollment-code` → codice monouso (15 minuti, salvato come SHA-256) e **QR** (SVG)
  con payload `{v, api, issuer, company, code}` per l'app mobile.
- `POST /devices/register` (utente autenticato dall'app con il proprio token + codice): il dispositivo nasce
  `pending` oppure `authorized` se la società ha `devices_need_authorization = false`.
  `POST /devices/heartbeat` aggiorna ultimo contatto e versioni (403 se revocato).
- `POST /devices/{id}/authorize`, `PATCH` (rinomina), `DELETE` (revoca, il record resta), `GET /devices/summary`.
- Pagina Dispositivi: contatori per stato (filtro al clic), tabella, QR in dialogo, autorizza/rinomina/revoca.

**Territorio** (`territory.view` / `territory.manage`): i viewset di comprensori, zone, piste diventano
CRUD (+ `/lifts`); `DELETE` = disattivazione; `?include_inactive=true`; geometrie in scrittura come
GeoJSON (confine Polygon/MultiPolygon, piste LineString/MultiLineString, impianti LineString),
mai restituite nelle liste (solo `has_boundary`/`has_geometry`; per la mappa restano i GeoJSON di M4).
Pagina a tre colonne comprensori → zone → piste (o impianti), con codice regionale e avviso se manca.

**Vocabolari** (`lookups.manage`): `GET/POST /lookups/{dimension}`, `PATCH /lookups/{dimension}/{id}`.
I valori standard si possono solo **disattivare per la società** (o arricchire di `mapping`); i valori
personalizzati hanno etichette IT/EN/DE, ordine, colore, mapping A01. La cache di `GET /lookups` viene
invalidata a ogni modifica. Pagina Vocabolari con selettore di dimensione.

**Società** (`company.settings`): `GET /company` (tutti), `PATCH /company` (nome, fuso, lingua,
`auto_lock_hours`, `devices_need_authorization`, `validity_rules`, `duplicate_rule`, `export_templates`).
Al cambio delle regole di validità la validità di tutti gli eventi viene ricalcolata da un task Celery e
la cache delle statistiche invalidata (`data_version`).

## Configurazione

| Dove | Chiave | Note |
|---|---|---|
| `.env` | `KEYCLOAK_ADMIN_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET` | client confidenziale `safe-admin` con service account (ruoli `manage-users`, `view-users` di `realm-management`, già nel realm importato) |
| `.env` | `KEYCLOAK_WEB_CLIENT_ID`, `PUBLIC_WEB_URL` | client e URL usati nel link dell'email di invito (`/{lingua}/home`) |
| `.env` | `PUBLIC_API_URL` | inserito nel payload del QR per l'app mobile |
| Keycloak realm | `smtpServer` | in sviluppo punta a Mailpit (`http://localhost:8025`) |

In produzione: cambiare il secret di `safe-admin`, configurare SMTP reale nel realm e limitare
`PUBLIC_WEB_URL` al dominio del portale.

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 128 test
cd frontend && npm run build -- --configuration=production && npm test -- --watch=false --browsers=ChromeHeadless
```

Verificato nel browser il 10/09/2026: invito end-to-end sulla società demo (utente creato nel realm
Keycloak di sviluppo, email "Modifica il tuo utente" ricevuta da Mailpit, utente nella tab Inviti),
codice QR di registrazione, pagine Squadre, Territorio (Civetta → zone → piste), Vocabolari, Impostazioni.

## Rinviato o diverso dal piano

- Le etichette dei permessi nella griglia sono i codici tecnici (`events.edit`…) raggruppati per
  modulo: sufficienti per un amministratore; traducibili in seguito.
- Nessuna UI per creare ruoli personalizzati (`POST /roles` esiste): i ruoli template coprono i casi
  della società pilota.
- Le geometrie del territorio si inseriscono come GeoJSON testuale; l'editor grafico sulla mappa non è
  previsto dal piano.
- Registrazione mobile: API pronte (`register`, `heartbeat`); l'app mobile non fa parte di questo
  progetto.
