# 06 · Piano di rilascio

Stime in **giorni/persona** per un team di 2 (1 back-end senior, 1 front-end senior) più
il sottoscritto come architetto/lead che implementa; calendario indicativo con lavoro in
parallelo BE/FE. Ogni milestone chiude con: codice funzionante, test verdi in CI,
`docs/runbook-Mx.md` con istruzioni di avvio locale, demo.

| Milestone | Contenuto | BE gg | FE gg | Calendario | Criterio di uscita |
|---|---|---|---|---|---|
| **M0** Kick-off | approvazione Fase 1, risposte alle domande, repository, CI vuota, Compose base | 2 | 1 | settimana 1 | pipeline verde su commit vuoto |
| **M1** Fondamenta | Django/DRF, PostGIS, migrazioni da DDL, seed vocabolari/stagioni/ISTAT, Keycloak realm + client, JWT/JWKS, `/me`, permessi, tenant middleware + RLS, Angular shell con config runtime, login OIDC, i18n, layout, barra filtri (vuota), direttiva `*safeCan` | 10 | 8 | settimane 2-3 | test tenant/permessi verdi; login funzionante in Compose |
| **M2** Eventi e persone | CRUD eventi/persone, validità calcolata, lock/unlock, idempotenza, filtri uniformi, tabelle Dati con paginazione server-side, drawer evento/persona, form evento, import storico CSV/XLSX (eventi + persone) | 11 | 10 | settimane 4-6 | import di `export.xlsx` riuscito; tabelle e form completi |
| **M3** Statistiche | 22 endpoint aggregati, `ChartPayloadBuilder`, cache + `data_version`, dataset di riferimento con risultati attesi, generatore 100k, benchmark, 6 pagine statistiche, slider piste, export PNG, "mostra come tabella" | 12 | 10 | settimane 7-9 | tutti i grafici < 2 s su 100k in CI; test aggregatori su dataset noto |
| **M4** Mappa | TileServer-GL in Compose, pipeline Planetiler/terrain/contour (script), layer piste/impianti da PostGIS via tippecanoe, tre stili, GeoJSON eventi, confini, cluster, heatmap, popup con PDF | 6 | 8 | settimane 10-11 | mappa completa con dati reali della società pilota |
| **M5** Export e PDF | job framework + storage, PDF rapporto (WeasyPrint + mappa statica), export dataset CSV/XLSX, export regionale A01 (XLSX/XLS/PDF) con anteprima qualità (edifici, area, duplicati), storico export, WebSocket `job.completed` | 12 | 7 | settimane 12-14 | A01 generato coincide con la lista Carabinieri/Alpini della stagione 2025/2026 a meno dei duplicati |
| **M6** Gestione | utenti (inviti via Keycloak Admin API, disattivazione con revoca sessioni), ruoli e permessi, squadre, dispositivi + QR + registrazione mobile, territorio e vocabolari, impostazioni società | 8 | 8 | settimane 15-16 | invito end-to-end con Mailpit; matrice permessi UI completa |
| **M7** Cifratura e hardening | libsodium client/server, chiavi utente e società, grant, kit di recupero, rotazione, `identity` endpoint + audit, retention e anonimizzazione (beat), audit log UI, rate limiting, security headers, CSP, dependency scan, test di sicurezza (authz matrix, tenant, PII leak, OWASP ZAP baseline), DPIA finale, runbook recupero chiavi | 12 | 8 | settimane 17-19 | test di sicurezza verdi; nessuna PII in log/URL (test automatico); revisione DPO |
| **Buffer** | contingenza 15% | 12 | 10 | settimane 20-21 | |
| **Totale** | | **85** | **70** | **~21 settimane** | |

Con un solo sviluppatore full-stack il calendario diventa ~32 settimane.

## Dipendenze esterne e date

| Necessità | Entro | Da chi |
|---|---|---|
| Risposte alle domande Q1-Q22 | M0 | committente |
| Campione export persone del portale attuale | inizio M2 | committente |
| Anagrafica piste con codici regionali, confini comprensorio (GeoJSON/KML) | M2 | società pilota |
| Chiave MapTiler o fonte satellite alternativa | M4 | committente |
| Dominio, certificati, SMTP, host di staging | M5 | committente / IT |
| Validazione DPO su retention e informativa | M7 | DPO società |

## Rischi

| # | Rischio | Prob. | Impatto | Mitigazione |
|---|---|---|---|---|
| R1 | Cifratura client-side: perdita passphrase/chiavi da parte degli utenti → dati identificativi irrecuperabili | media | alto | kit di recupero obbligatorio all'inizializzazione, promemoria per ≥ 2 custodi, test della procedura in M7, documentazione per l'amministratore |
| R2 | Requisiti dell'ente regionale diversi dall'A01 osservato (altri formati/Regioni) | media | medio | motore a template; validare l'output con la Provincia sulla stagione 2025/2026 già inviata |
| R3 | Regola duplicati troppo aggressiva o troppo lasca | media | medio | parametri configurabili, anteprima con elenco, flag "non è un duplicato" manuale (M5) |
| R4 | Pipeline cartografica (Planetiler, terrain) onerosa su host modesto | media | medio | generazione offline una tantum, PMTiles su object storage; in emergenza stile fallback con tile OSM esterne |
| R5 | Prestazioni < 2 s non raggiunte su query multi-serie | bassa | medio | benchmark in CI da M3; fallback tabella `stats_fact` materializzata aggiornata da trigger |
| R6 | Licenze satellite | media | basso | scelta in M0; il layer satellite è opzionale e disattivabile da config |
| R7 | Keycloak Admin API per inviti: gestione errori/duplicati email tra società | bassa | medio | email univoca per realm: utente esistente in altra società → errore esplicito; valutare realm per società se serve |
| R8 | Import storico con dati identificativi in chiaro | media | alto | import esclusivamente da browser con cifratura locale; file sorgente mai caricato sul server in chiaro |
| R9 | Vocabolari estesi (report di riferimento) incompleti o ambigui | media | basso | seed iniziale da PDF di riferimento; modificabili con `lookups.manage` |
| R10 | Copertura test di autorizzazione che decade con nuove rotte | bassa | alto | test generato dallo schema OpenAPI: una rotta senza `x-permissions` fa fallire la CI |
| R11 | Dati sanitari: incidente di sicurezza | bassa | molto alto | E2E encryption limita l'impatto a dati pseudonimizzati; audit; procedura data breach nel DPIA |

## Definition of Done (ogni milestone)

- Test unitari e di integrazione verdi; copertura ≥ 85% sul back-end, ≥ 70% sul front-end.
- Test di autorizzazione e di isolamento tenant per ogni nuova rotta.
- Nessuna stringa hardcoded (lint) e traduzioni IT/EN/DE complete.
- Lighthouse accessibilità ≥ 90 sulle pagine nuove; navigazione da tastiera verificata.
- Migrazioni reversibili; `docker compose up` da zero funzionante; runbook aggiornato.
- Changelog e tag `vX.Y.0-mN`.
