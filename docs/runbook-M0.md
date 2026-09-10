# Runbook M0 · Setup del progetto

## Cosa c'è

- Monorepo con `backend/` (Django 5.2, DRF, PostGIS, Celery, Channels), `frontend/` (Angular 20),
  `infra/` (Keycloak realm, TileServer-GL, init DB), `docs/`, `reference/`.
- `docker-compose.yml` con: `db` (PostGIS 16-3.4), `redis`, `keycloak` (realm `safe` importato
  all'avvio, con client `safe-web`, `safe-mobile`, `safe-api`, `safe-admin` e due utenti demo),
  `api`, `worker`, `beat`, `ws`, `tiles`, `minio`, `mailpit`.
- CI GitHub Actions: lint + test back-end con PostGIS e Redis di servizio, lint + test + build
  front-end, build delle immagini.
- Endpoint di verifica: `GET /api/v1/health` (stato DB e versione PostGIS), `GET /api/schema/`,
  `GET /api/docs/`.

## Prerequisiti su Windows

1. **Docker Desktop** con backend WSL2 (https://docs.docker.com/desktop/setup/install/windows-install/).
   Dopo l'installazione: `docker info` deve rispondere.
2. Node 24 e Python 3.13 (già presenti).

## Primo avvio

```bash
cp .env.example .env
docker compose up -d db redis keycloak minio mailpit
docker compose run --rm api python manage.py migrate
docker compose up -d api worker ws
curl http://localhost:8000/api/v1/health
```

Atteso:

```json
{"status":"ok","version":"0.1.0","database":"ok","postgis":"3.4.x","oidc_issuer":"http://keycloak:8080/realms/safe"}
```

Keycloak: http://localhost:8080 (admin/admin). Utenti demo del realm: `admin.demo` / `admin.demo`,
`rescuer.demo` / `rescuer.demo` (verranno collegati alle società in M1).

## Test back-end

```bash
docker compose run --rm api pytest
```

## Front-end

```bash
cd frontend
npm install
npm start
```

http://localhost:4200. La configurazione runtime è in `frontend/public/config/app-config.json`
(in produzione viene montata in `/usr/share/nginx/html/config/app-config.json`).

## Verificato in questa sessione (senza Docker)

- `ruff check` e `ruff format --check` sul back-end: verdi.
- Scaffold Angular 20 creato; `npm install` eseguito.
- I test back-end richiedono PostGIS e vengono eseguiti in CI o in Compose: **non ancora eseguiti
  localmente** perché Docker non è installato su questa macchina.
