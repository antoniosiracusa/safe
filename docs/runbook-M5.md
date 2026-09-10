# Runbook M5 · Esportazioni, PDF e anteprima qualità

## Cosa c'è

**Job asincroni** (`safe/apps/jobs`)

- `AsyncJob` con handler registrati per tipo (`runner.register`), esecuzione su Celery (code `exports`, `pdf`),
  risultato su object storage S3/MinIO (`{company}/{kind}/{job}.{ext}`, bucket `S3_BUCKET`), scadenza
  (7 giorni per gli export, 30 per i PDF) con pulizia giornaliera da beat (`safe.apps.jobs.cleanup_expired`).
- `GET /jobs/{id}` (stato, `download_url`, `result`), `GET /jobs/{id}/download` (stream con
  `Content-Disposition`), `GET /jobs`. In test Celery è eager: il job è già completo nella risposta.

**PDF del rapporto evento** (`safe/apps/reports`, permesso `reports.pdf`)

- `GET /events/{id}/report.pdf`: se esiste un PDF già generato per l'ultima versione dell'evento
  (stesso `updated_at`, stessa lingua) risponde 200 con il file; altrimenti accoda il job e risponde
  **202 con il job** (il client fa polling e scarica). Ogni download è tracciato in audit (`report.pdf`).
- Layout che replica il rapporto di riferimento (griglie di caselle con la voce selezionata evidenziata,
  una pagina per persona) ma **pseudonimizzato**: solo iniziali, età, classe, mai dati identificativi.
  Mappa statica del luogo (Mapbox Static Images API, `MAPBOX_TOKEN` o `MAPBOX_SECRET_TOKEN` in `.env`);
  senza token il riquadro resta vuoto. Rendering WeasyPrint (dipendenze Pango nell'immagine `api`).
- Pulsanti PDF: tabella eventi, drawer evento, tabella persone, popup della mappa.

**Export dataset** (`POST /exports/dataset`, permesso `exports.dataset`)

- CSV (`;`, UTF-8 con BOM, apribile da Excel) o XLSX di **eventi** o **persone** con i filtri globali
  (`team`, `season`, `date_from/to`, `ski_area`, `zone`, `valid_only`) e i filtri locali ammessi;
  intestazioni localizzate (IT/EN/DE), vocabolari tradotti, classi di età; **nessun nome o contatto**.
- Pagina "Dataset CSV/XLSX": dataset, formato, riepilogo dei filtri attivi, storico con download.

**Export regionale A01 Veneto** (`exports.regional`)

- `POST /exports/regional/preview` → anteprima qualità: persone nel periodo, escluse perché in edifici
  (`location_type` con `mapping.regional_export_exclude`), escluse perché fuori dall'area amministrativa
  scelta (spatial join con i confini ISTAT), gruppi di duplicati tra squadre (regola per società
  `settings.duplicate_rule`: stessa data, pista, genere, classe d'età A01, attrezzatura entro N minuti),
  righe esportabili, avvisi (piste senza codice regionale, eventi senza posizione, confini non caricati).
- `POST /exports/regional` → job XLSX o XLS (Excel 97-2003, come il modello inviato alla Provincia):
  righe di titolo, una riga per persona con fasce orarie 08-11 / 11-14 / 14-17 / 17-08, sesso, classi di età
  A01, denominazione e codice regionale della pista, attrezzatura (Sci/Snowboard/Altro), tipologia
  (7 cause A01 tramite `mapping.veneto_a01` dei vocabolari), colonna "soccorso congiunto" per i gruppi uniti.
- `GET /exports/administrative-areas` (regioni/province ISTAT che intersecano i comprensori della società),
  `GET /exports` (storico con `ExportRun`). Pagina "Enti regionali": parametri → anteprima → generazione.

**Confini ISTAT** (tabella globale `istat_admin_unit`, aggiornamento annuale)

```bash
docker compose exec api python manage.py load_istat_boundaries --year 2025 \
  --url https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2025/Limiti01012025_g.zip
```

Finché non sono caricati, l'anteprima segnala `administrative_boundaries_not_loaded` e il filtro
territoriale della pagina resta disattivato.

## Configurazione

| Dove | Chiave | Note |
|---|---|---|
| `.env` | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` | MinIO in sviluppo (`safe-files`); il bucket è creato al primo uso |
| `.env` | `MAPBOX_TOKEN` (o `MAPBOX_SECRET_TOKEN`) | immagini statiche nei PDF; il token pubblico `pk.` basta |
| `company.settings.duplicate_rule` | `{"minutes": 30, "fields": [...]}` | campi ammessi: `date`, `slope`, `zone`, `gender`, `age_class_a01`, `equipment` |
| vocabolari | `mapping.veneto_a01`, `mapping.regional_export_exclude` | modificabili con `lookups.manage` (UI in M6) |

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 96 test
cd frontend && npm run build -- --configuration=production && npm test -- --watch=false --browsers=ChromeHeadless
```

Verificato nel browser il 10/09/2026 sulla società demo (stagione 2025/2026, 26.180 persone): anteprima in
circa 12 s (2.202 escluse in edifici, 81 gruppi di duplicati, 26.099 righe), generazione XLSX via job e
download, PDF del rapporto (202 → polling → download, poi 200 immediato dalla cache), pagina dataset.

Nota: i test nel container leggono `DJANGO_SETTINGS_MODULE` dall'ambiente (`dev`), che prevale sull'ini di
pytest; `--ds=safe.settings.test` è ora forzato negli `addopts`.

## Rinviato o diverso dal piano

- Notifica WebSocket `job.completed`: sostituita da polling (1-3 s) di `GET /jobs/{id}`; il canale
  WebSocket resta predisposto per M6/M7.
- A01 in formato PDF: non prodotto (la Provincia riceve il foglio Excel); XLSX e XLS sì.
- Flag manuale "non è un duplicato" (piano M5, R3): rinviato; oggi l'unione dei duplicati si può
  disattivare per l'intero export.
- L'anteprima elabora eventi e persone in Python: ~12 s su 26k persone. Accettabile per un'operazione
  annuale; se servisse, spostare esclusioni e raggruppamento in SQL.
