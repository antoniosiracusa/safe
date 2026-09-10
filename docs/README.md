# SAFE · Fase 1 — Pianificazione

Piattaforma multi-tenant per la raccolta, gestione e analisi statistica degli incidenti su piste da sci.

| # | Documento | Contenuto |
|---|---|---|
| 00 | [Domande e assunzioni](00-domande-e-assunzioni.md) | 22 punti da confermare, con l'assunzione usata nei documenti |
| 01 | [Architettura](01-architettura.md) | componenti, integrazioni, flussi, tenant, cifratura, cartografia, alternative |
| 02 | [Schema dati](02-schema-dati.md) · [DDL](02-ddl.sql) | ERD, regole di modellazione, dizionario dimensioni, DDL con indici, trigger, RLS, seed |
| 03 | [OpenAPI](03-openapi.yaml) | tutti gli endpoint `/api/v1`, esempi, `x-permissions`, WebSocket |
| 04 | [Matrice permessi](04-matrice-permessi.md) | catalogo, ruoli template, permessi per funzionalità, test derivati |
| 05 | [Schermate](05-schermate.md) | navigazione, stati standard, wireframe testuali, flussi |
| 06 | [Piano di rilascio](06-piano-rilascio.md) | milestone M0-M7, stime, dipendenze, rischi, DoD |
| 07 | [DPIA sintetica](07-dpia-sintetica.md) | trattamenti, basi giuridiche, misure, rischi residui, recupero chiavi |

Materiale di dominio usato come riferimento: `../reference/testo base.odt`, `../reference/report-evento-*.pdf`,
`../reference/export.xlsx`, `../reference/A01_*.xls`, `../reference/Lista soccorsi *.pdf`, `../reference/comunicazione elenco infortuni.docx`.

Fase 1 approvata il 10/09/2026 (assunzioni confermate). Runbook delle milestone:
[M0](runbook-M0.md) · [M1](runbook-M1.md) · [M2](runbook-M2.md) · [M3](runbook-M3.md).
