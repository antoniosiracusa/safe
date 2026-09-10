# Runbook M2 · Eventi e persone (API + sezione Dati)

Perimetro: come da decisione del 10/09/2026 l'**import dello storico è escluso**.

## Cosa c'è

**API** (`docs/03-openapi.yaml`, tutte con `x-permissions` e filtri globali uniformi)

- `GET/POST /events`, `GET/PATCH/DELETE /events/{id}`, `POST /events/{id}/lock|unlock`,
  `GET/POST /events/{id}/persons`; `GET /persons`, `GET/PATCH/DELETE /persons/{id}`,
  `GET /persons/{id}/identity`; `GET /lookups`; `GET /ski-areas|zones|slopes`.
- Filtri: globali (`team`, `season` o `date_from`/`date_to`, `ski_area`, `zone`, `valid_only`)
  più specifici (eventi: `slope`, `cause`, `location_type`, `locked`, `search`, `updated_since`;
  persone: `gender`, `country_code`, `diagnosis`, `equipment`, `evacuation_mean`, `age_min/max`, `helmet`).
  Paginazione 50 (max 200), `ordering`.
- Regole: validità calcolata a ogni salvataggio (regole per società in `company.settings`);
  `fully_valid` richiede evento valido e almeno una persona valida; blocco alla chiusura o dopo
  `auto_lock_hours` (beat ogni 15 min); sblocco con motivo e audit; idempotenza mobile via
  `client_uuid`; soft delete; scoping per squadra (`events.view_own_teams_only`, `events.edit_any_team`).
- I dati identificativi viaggiano solo come blob cifrato (`pii`) e si leggono solo da
  `/persons/{id}/identity` (409 senza grant, sempre in audit). Nessuna risposta contiene nomi.

**Web**

- Dati · Eventi: tabella server-side (50/pagina, ordinamento, scroll orizzontale, colonne ID e data
  congelate), filtri specifici nella URL, drawer con schede Dati/Persone/Storico, modifica,
  blocca/sblocca con motivo, elimina, aggiunta e modifica persone, pulsante "Nuovo evento".
- Dati · Persone: tabella server-side con filtri propri; il clic apre il drawer dell'evento.
- Form evento e persona con vocabolari nella lingua attiva, cascata comprensorio → zona → pista
  (la pista imposta zona, comprensorio e difficoltà), tri-stato per i booleani ("Non classificato").
- Le persone registrano solo dati pseudonimizzati; nome, cognome e contatti arrivano con la
  cifratura in M7 (avviso nel form).

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 57 test
cd frontend && npm run build -- --configuration=production && npm test -- --watch=false --browsers=ChromeHeadless
```

Verificato nel browser con dati creati via API: tabella eventi e persone, drawer con evento
bloccato e due persone, form "Nuovo evento" (creazione dal form riuscita), nessun errore in console.

## Note

- Il PDF del rapporto (M5) è già presente come pulsante disabilitato con tooltip.
- La posizione si inserisce come latitudine/longitudine; la scelta sulla mappa arriva in M4.
- Lo storico modifiche nel drawer (audit) arriva in M7.
