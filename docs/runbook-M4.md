# Runbook M4 · Mappa (Mapbox)

Decisione del 10/09/2026: cartografia con **Mapbox** (Mapbox GL JS + stili Mapbox) al posto del
tile server self-hosted previsto in Fase 1 (TileServer-GL rimosso da Compose). Le immagini
statiche per i PDF (M5) useranno la Mapbox Static Images API.

## Configurazione

| Dove | Chiave | Valore |
|---|---|---|
| `frontend/public/config/app-config.json` | `map.mapboxToken` | token **pubblico** `pk.…` (Mapbox → Account → Tokens; limitare l'URL ai domini del portale) |
| `frontend/public/config/app-config.json` | `map.defaultCenter`, `map.defaultZoom` | centro iniziale se la società non ha confini |
| `.env` | `MAPBOX_STYLE_WINTER/SUMMER/SATELLITE` | stili (default: `mapbox/light-v11` + rilievo, `mapbox/outdoors-v12`, `mapbox/satellite-streets-v12`); si possono sostituire con stili personalizzati di Mapbox Studio |
| `.env` | `MAPBOX_SECRET_TOKEN` | token segreto `sk.…` solo server, per le immagini statiche dei PDF (M5) |

Senza token la pagina mostra "Mappa non configurata" con il percorso del file da compilare; il
resto dell'app funziona. I token non vengono mai salvati in storage del browser.

Uso e costi: Mapbox GL JS v3 conta i "map loads" (una per apertura della pagina mappa e per
selettore posizione nel form); la fascia gratuita mensile è ampia per un back-office. Verificare
i termini Mapbox per l'uso commerciale.

## Cosa c'è

**API** (`map.view`)

- `GET /map/events.geojson`: FeatureCollection di punti con **solo `id` e `dateandtime`**, filtri globali,
  scoping per squadra. `GET /map/ski-areas.geojson` (confini), `/map/slopes.geojson` (piste con
  difficoltà e codice regionale), `/map/lifts.geojson` (impianti), `GET /map/styles`.
- `seed_demo` aggiunge un confine, geometrie di piste e due impianti **sintetici** alla società demo.

**Web**

- Pagina Mappa: stili Inverno (base chiara + hillshade dal DEM Mapbox), Estate, Satellite; layer
  attivabili confini / piste e impianti / eventi (cluster con conteggio, zoom al clic) / heatmap;
  popup con id evento, data/ora, "Apri evento" (drawer) e PDF (M5); stile e layer nella URL
  (`style=`, `layers=`), filtri globali applicati; legenda difficoltà piste.
- Form evento: selettore posizione sulla mappa (clic o trascinamento del marker) collegato ai campi
  latitudine/longitudine.
- Mapbox GL è caricato in modo lazy (chunk separato): il bundle iniziale resta a 1,3 MB.

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 82 test
cd frontend && npm run build -- --configuration=production && npm test -- --watch=false --browsers=ChromeHeadless
```

Senza token Mapbox in questa sessione è stato verificato nel browser lo stato "mappa non configurata"
e il selettore posizione nel form; il rendering con tile va verificato dopo aver inserito il token.
