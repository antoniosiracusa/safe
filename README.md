# SAFE

Piattaforma multi-tenant per la raccolta, la gestione e l'analisi statistica degli incidenti
sulle piste da sci: back-office web, API REST per il back-office e per la futura app mobile
dei soccorritori, esportazioni verso gli enti regionali.

Documentazione di progetto (Fase 1, approvata il 10/09/2026): [docs/](docs/README.md).

## Struttura del repository

```
backend/    Django 5 + DRF + PostGIS + Celery + Channels   (API, worker, WebSocket)
frontend/   Angular 20 + PrimeNG + Chart.js + MapLibre GL  (back-office SPA)
infra/      Keycloak realm, TileServer-GL, nginx, script di provisioning
docs/       architettura, schema dati, OpenAPI, permessi, schermate, piano, DPIA
reference/  materiale di dominio (tracciati regionali, report di riferimento)
```

## Avvio locale (sviluppo)

Prerequisiti: Docker Desktop (con WSL2 su Windows), Node 24, Python 3.13.

```bash
cp .env.example .env
docker compose up -d db redis keycloak minio mailpit
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py seed_demo
docker compose up -d api worker ws
```

Utenti demo (Keycloak): `admin.demo` / `admin.demo`, `rescuer.demo` / `rescuer.demo`.

- API: http://localhost:8000/api/v1/ (schema OpenAPI: http://localhost:8000/api/schema/, Swagger: http://localhost:8000/api/docs/)
- Keycloak: http://localhost:8080 (realm `safe`, admin `admin`/`admin` in sviluppo)
- Mailpit (email di invito): http://localhost:8025
- MinIO (PDF ed export): http://localhost:9001
- Mappa: inserire il token pubblico Mapbox in `frontend/public/config/app-config.json` (`map.mapboxToken`)

Front-end in modalità sviluppo (hot reload):

```bash
cd frontend && npm install && npm start
```

poi http://localhost:4200.

## Test

```bash
docker compose run --rm api pytest
cd frontend && npm test
```

La CI (GitHub Actions) esegue lint, test con PostGIS e Redis di servizio, e il build delle immagini.

## Milestone

| M | Contenuto | Stato |
|---|---|---|
| M0 | repository, Compose, Keycloak, CI | fatto ([runbook](docs/runbook-M0.md)) |
| M1 | autenticazione OIDC, multi-tenancy, modello dati, migrazioni, shell web | fatto ([runbook](docs/runbook-M1.md)) |
| M2 | CRUD eventi e persone, sezione Dati (import storico escluso su richiesta) | fatto ([runbook](docs/runbook-M2.md)) |
| M3 | statistiche (22 rotte aggregate, 6 pagine, benchmark 100k) | fatto ([runbook](docs/runbook-M3.md)) |
| M4 | mappa (Mapbox GL JS, stili, layer, cluster, heatmap, selettore posizione) | fatto ([runbook](docs/runbook-M4.md)) |
| M5 | job asincroni, PDF rapporto, export dataset CSV/XLSX, export regionale A01 con anteprima qualità | fatto ([runbook](docs/runbook-M5.md)) |
| M6 | utenti, squadre, dispositivi | |
| M7 | cifratura, audit, hardening | |
