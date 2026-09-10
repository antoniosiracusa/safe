# Runbook M1 · Autenticazione OIDC, multi-tenancy, modello dati, shell web

## Cosa c'è

**Back-end**

- Modello dati completo da `docs/02-ddl.sql` come modelli Django in 10 app
  (`tenancy`, `org`, `authz`, `lookups`, `territory`, `rescue`, `devices`, `crypto`, `jobs`, `audit`)
  con migrazioni `0001_initial` e migrazioni `0002` per Row Level Security, vincoli di dimensione
  dei vocabolari, seed di vocabolari (IT/EN/DE, mapping A01), ruoli template e stagioni.
- Isolamento tenant a tre livelli: `TenantMiddleware` (tenant dall'utente autenticato),
  `TenantManager` (queryset sempre filtrato), RLS PostgreSQL con `SET LOCAL app.company_id`.
  Il ruolo DB dell'applicazione non è superuser: la RLS vale anche per lui.
- Autenticazione: JWT di Keycloak validato con JWKS (firma, `iss`, `aud`, `exp`); utenti risolti
  per `sub`; un utente invitato viene attivato al primo accesso. Nessuna password nell'app.
- Autorizzazione: catalogo di 38 permessi, 6 ruoli template, grant/deny per utente,
  `HasPermission` su ogni vista, `GET /api/v1/me` con mappa completa dei permessi.
- `GET /api/v1/filters/options` per la barra filtri; `GlobalFilterSet` uniforme per le rotte successive.
- Comandi: `bootstrap_company`, `seed_demo`.

**Front-end (Angular 20)**

- Configurazione runtime da `config/app-config.json`; login OIDC Authorization Code + PKCE
  (`angular-oauth2-oidc`); interceptor Bearer; guard di sessione; pagina "utente non abilitato".
- `SessionService` (utente, società, squadre, permessi come signals) e direttiva `*safeCan`
  che mostra la funzione bloccata invece di nasconderla.
- Barra filtri globale (squadra, stagione o intervallo date, comprensorio, zona, solo validi, reset)
  sincronizzata con la query string: URL condivisibile, filtri persistenti tra le pagine.
- i18n IT/EN/DE con Transloco (rotte `/:lang/...`), layout con menu (voci bloccate con lucchetto),
  home con card dei moduli, pagine segnaposto per le milestone successive.

## Avvio

```bash
cp .env.example .env
docker compose up -d db redis keycloak minio mailpit
docker compose build api
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py seed_demo
docker compose up -d api worker ws
cd frontend && npm install && npm start
```

Poi http://localhost:4200 → redirect a Keycloak → utenti demo:

| Utente | Password | Ruolo |
|---|---|---|
| `admin.demo` | `admin.demo` | Amministratore della società demo |
| `rescuer.demo` | `rescuer.demo` | Soccorritore (vede le funzioni bloccate) |

Keycloak admin: http://localhost:8080 (`admin` / `admin`). Solo in sviluppo esiste il client
`safe-dev-cli` (password grant) per ottenere token da terminale:

```bash
curl -s -d client_id=safe-dev-cli -d username=admin.demo -d password=admin.demo -d grant_type=password \
  http://localhost:8080/realms/safe/protocol/openid-connect/token
```

## Test

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"
cd frontend && npm test -- --watch=false --browsers=ChromeHeadless
```

## Verificato in questa sessione

- 27 test back-end verdi (autenticazione, permessi, isolamento tenant ORM + RLS, seed, filtri), mypy pulito.
- `GET /me` con token reale di Keycloak: utente invitato attivato, 33 permessi per l'amministratore.
- SPA: caricamento configurazione, discovery OIDC, redirect al login Keycloak; con sessione valida
  la shell mostra menu, barra filtri sincronizzata con la URL, pagine segnaposto con i filtri attivi.
- 5 test front-end verdi.

## Note

- Il realm Keycloak dichiara esplicitamente gli scope `basic`, `profile`, `email`, `web-origins`:
  quando un file di import contiene `clientScopes`, Keycloak non crea quelli predefiniti.
- `OIDC_ISSUER` è l'issuer pubblico (claim `iss`), `OIDC_JWKS_URL` l'indirizzo interno di Compose.
- ESLint per il front-end non è ancora configurato (`ng add @angular-eslint` fallisce per un
  conflitto di versione): da aggiungere in M2.
