# Runbook M3 · Statistiche

## Cosa c'è

**API** (`/api/v1/stats/...`, permesso `stats.view`; riepilogo stagione anche `stats.advanced`)

- 22 rotte che restituiscono payload Chart.js **già aggregati** (`{labels, datasets:[{label, data,
  backgroundColor}], meta}`) o tabelle pronte. Nessuna aggregazione lato client.
- "Non classificato" è sempre presente come ultima categoria, anche a zero; le etichette sono
  tradotte (`lang=it|en|de`, default lingua utente); il colore segue l'entità del vocabolario
  (palette categoriale a 8 slot validata per daltonismo, oltre 8 serie → "Altri").
- Filtri globali uniformi (`team`, `season` o `date_from`/`date_to`, `ski_area`, `zone`, `valid_only`)
  più `age_cluster=standard|veneto_a01`, `limit` (paesi, piste), `incremental` (cumulativo).
- Cache Redis per società (chiave: rotta + filtri + squadre visibili + lingua + `data_version`),
  invalidata implicitamente a ogni scrittura su eventi/persone. `meta.cached` indica l'esito.
- `python manage.py generate_synthetic --company demo --events 100000` genera un dataset sintetico
  (nessun dato reale) per benchmark e demo.

**Web**

- Sei pagine (Riepilogo zona, Demografia, Tipologia, Geografia, Meteo, Riepilogo stagione) con la
  stessa barra filtri; card grafico con schermo intero, download PNG e vista tabellare; selettore
  classi di età e slider "primi N" riflessi nella URL; stati vuoto/caricamento/errore/permesso mancante.
- Home con KPI da `/stats/general`.

## Benchmark (criterio: < 2 s su 100.000 eventi)

Dataset: 100.004 eventi, 114.862 persone (4 stagioni, 3 squadre, 10 piste), PostGIS in Docker su
questo PC. Tempo della prima chiamata senza cache (migliore di 3), poi con cache:

| Rotta | tutte le stagioni | stagione singola | con cache |
|---|---|---|---|
| typology/age-evacuation-mean (la più lenta) | 855 ms | 256 ms | 24 ms |
| typology/evacuation-means-total | 754 ms | 223 ms | 23 ms |
| typology/age-cause | 381 ms | 220 ms | 21 ms |
| demographics/age-gender | 346 ms | 146 ms | 22 ms |
| zone-summary/table | 260 ms | 270 ms | 22 ms |
| tutte le altre | 127–340 ms | 60–250 ms | 20–45 ms |

Peggiore senza cache: **855 ms**. Comando: `python scratch/bench_stats.py` (script nella cartella di
lavoro della sessione; da promuovere a job nightly in M7).

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 75 test, 14 sugli aggregatori con dataset noto
cd frontend && npm run build -- --configuration=production && npm test -- --watch=false --browsers=ChromeHeadless
```

Verificato nel browser sui 100k eventi: Demografia, Geografia (slider), Riepilogo zona (grafico +
tabella), Riepilogo stagione.

## Note

- Distribuzione annuale: serie = le ultime tre stagioni fino a quella selezionata, mesi giugno → maggio.
- Il cumulativo usa un grafico a linee; il resto barre (raggruppate o impilate) e ciambelle.
- Ogni grafico ha la vista tabellare per accessibilità e la legenda quando le serie sono più di una.
