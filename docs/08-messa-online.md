# SAFE · Piano di messa online

Stato di partenza (11/09/2026): milestone M0-M7 complete, stack verificato solo in sviluppo locale
(Docker Compose su Windows, Keycloak dev, dati sintetici). Manca tutto ciò che riguarda l'esercizio:
ambiente server, TLS, posta reale, backup, monitoraggio, dati della società pilota.

Il piano è in 7 passi. I passi 1-2 sono lavoro sul repository (posso farli io); i passi 0 e 3-6
richiedono decisioni, accessi o azioni del committente.

## 0. Decisioni preliminari (committente)

| Decisione | Opzioni | Nota |
|---|---|---|
| **Hosting** | VPS in UE (es. Hetzner Falkenstein/Norimberga, Aruba Cloud, OVH) da 4 vCPU / 8 GB / 80 GB SSD; oppure server del committente | Tutti i dati restano in UE (DPIA). Una macchina basta per staging + produzione all'inizio; meglio due |
| **Dominio** | es. `safe.<societa>.it` con sottodomini `auth.` (Keycloak) e `api.` | DNS gestito dal committente; certificati Let's Encrypt automatici via Traefik |
| **Posta in uscita** | SMTP del committente, oppure servizio transazionale UE (es. Brevo, Mailjet) | Serve a Keycloak per inviti, reset password, OTP |
| **Mapbox** | account della società con token pubblico limitato al dominio e token segreto per i PDF | Fascia gratuita ampia; verificare i termini per uso commerciale |
| **Titolare e DPO** | società di gestione pilota; nomina DPO/referente privacy | Revisione DPIA, informativa, contratto art. 28 con il fornitore hosting |
| **Custodi delle chiavi** | almeno 2 persone della società | Riceveranno le 24 parole di recupero; nessuno del fornitore |
| **Società pilota e stagione di avvio** | es. stagione 2026/2027 | Definisce la data di go-live (prima dell'apertura impianti) |

## 1. Preparazione del repository per la produzione (sviluppo, ~3-4 giorni)

Da costruire, oggi assente:

- `docker-compose.prod.yml`: Traefik (TLS Let's Encrypt, redirect HTTPS, HSTS), `web` (nginx con
  la SPA, CSP e header di sicurezza), `api` (gunicorn), `ws` (daphne), `worker`, `beat`, `db`
  (PostGIS con volume), `redis`, `keycloak` (modalità produzione, `--optimized`, DB dedicato),
  `minio` (o S3 esterno). Nessuna porta esposta tranne 80/443.
- Pubblicazione immagini: la CI costruisce `safe-api` e `safe-web` su GHCR con tag `sha` e `vX.Y.Z`;
  il server scarica le immagini, non compila.
- Configurazione: `.env.production.example` con tutte le variabili (segreti generati, `DEBUG=0`,
  `ALLOWED_HOSTS`, `CORS`, `OIDC_ISSUER` pubblico, `PUBLIC_WEB_URL`, `S3_*`, `MAPBOX_*`,
  Keycloak admin client con secret nuovo) e `app-config.json` di produzione per la SPA.
- Realm Keycloak di produzione: import senza `safe-dev-cli`, senza utenti demo, con SMTP reale,
  redirect URI del dominio, MFA obbligatoria per il ruolo amministratore, password policy, brute force
  detection, sessioni brevi.
- Backup: script giornaliero `pg_dump` cifrato + snapshot MinIO, copia fuori macchina (object storage
  UE), test di ripristino documentato. Retention backup 30 giorni.
- Osservabilità minima: healthcheck sui servizi, log strutturati con rotazione, uptime check esterno,
  alert su spazio disco e errori 5xx; Sentry o equivalente opzionale.
- Runbook operativi: deploy/aggiornamento (`docker compose pull && up -d`, migrazioni), ripristino da
  backup, rotazione segreti, recupero chiavi (già in runbook-M7), procedura incidente/data breach.

## 2. Preparazione dati e vocabolari (sviluppo + società, ~2 giorni)

- Confini ISTAT caricati (`load_istat_boundaries`, già verificato).
- Anagrafica della società pilota da raccogliere: comprensori con confine (GeoJSON), zone, piste con
  **codice regionale** (indispensabile per l'A01), impianti, squadre e corpi di soccorso, elenco utenti
  con ruolo e squadra.
- Verifica dei vocabolari con il responsabile soccorso (cause, diagnosi, mezzi) e delle corrispondenze
  A01; eventuali voci personalizzate.
- Nessun import dello storico (deciso): l'archivio parte dalla stagione di avvio.

## 3. Provisioning del server (committente/IT + sviluppo, ~1 giorno)

1. VPS con Ubuntu 24.04 LTS, utente non root con Docker Engine + Compose plugin, firewall (solo 22
   da IP noti, 80, 443), aggiornamenti automatici di sicurezza, fuso orario Europe/Rome.
2. DNS: `A` per `safe.`, `auth.`, `api.` verso il server.
3. Clonazione della sola cartella di deploy (compose + env), segreti generati sul server, mai in git.
4. Primo avvio: Traefik ottiene i certificati; `migrate`, seed dei vocabolari e dei ruoli.

## 4. Staging e collaudo (~1 settimana)

- Stesso stack con dati sintetici (`seed_demo`) su `staging.` o sulla stessa macchina con prefisso.
- Collaudo funzionale con 2-3 utenti reali della società: inserimento eventi da web, PDF, statistiche,
  export A01 confrontato con l'elenco 2025/2026 inviato alla Provincia, mappa.
- Sicurezza: OWASP ZAP baseline sul dominio staging, `pip-audit`/`npm audit` puliti, verifica header
  e CSP, test della matrice permessi già in CI.
- Prova completa della procedura chiavi: creazione chiave società dal custode, secondo custode,
  simulazione di perdita passphrase e recupero con le 24 parole (obbligatoria prima del go-live).
- Prova di ripristino da backup su staging.
- Prestazioni: statistiche < 2 s con il dataset da 100k eventi (già misurato in sviluppo, da
  confermare sul server).

## 5. Onboarding della società pilota (~2 giorni)

1. `bootstrap_company` con l'amministratore reale → invito via email → primo accesso con MFA.
2. L'amministratore crea la propria chiave personale e **inizializza la chiave della società**;
   trascrive le 24 parole e le consegna al DPO/cassaforte; abilita il secondo custode.
3. Caricamento territorio, squadre, utenti (inviti), dispositivi se serve, impostazioni (regole di
   validità, blocco automatico, retention 10 anni, regola duplicati).
4. Formazione breve (1-2 ore): inserimento evento, dati identificativi, PDF, export regionale,
   gestione utenti. Guida rapida in PDF da preparare.

## 6. Go-live e post go-live

Checklist di go-live (tutte verdi prima di aprire agli utenti):

- [ ] certificati validi, HSTS attivo, header di sicurezza verificati
- [ ] backup notturno funzionante e ripristino provato
- [ ] uptime check e alert attivi
- [ ] Keycloak: utenti demo assenti, admin con MFA, SMTP reale testato
- [ ] chiave società inizializzata da un custode reale, 2 custodi, kit di recupero custodito
- [ ] informativa privacy pubblicata, DPIA finale approvata dal DPO, contratto art. 28 firmato
- [ ] retention configurata; audit log consultabile
- [ ] runbook operativi consegnati al committente

Dopo il go-live: aggiornamenti mensili (dipendenze e immagini), `pip-audit`/`npm audit` in CI,
rotazione annuale dei segreti, aggiornamento annuale dei confini ISTAT, test annuale del recupero
chiavi, revisione DPIA a ogni cambiamento rilevante.

## Tempi indicativi

| Passo | Durata | Dipende da |
|---|---|---|
| 0 Decisioni | 1 settimana (in parallelo) | committente |
| 1 Repo produzione | 3-4 giorni | — |
| 2 Dati società | 2 giorni | società pilota |
| 3 Server | 1 giorno | hosting, DNS |
| 4 Staging e collaudo | 1 settimana | 1, 2, 3 |
| 5 Onboarding | 2 giorni | 4, custodi |
| 6 Go-live | 1 giorno | checklist |

Totale realistico: **3-4 settimane** dal via, con il collaudo come passo critico.
