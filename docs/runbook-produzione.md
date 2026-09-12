# Runbook · Produzione (deploy/)

Tutto ciò che serve per installare, aggiornare, salvare e ripristinare SAFE su un server Linux con
Docker. Riferimenti: [08-messa-online.md](08-messa-online.md) per il piano, `deploy/` nel repository
per i file.

## Architettura sul server

| Componente | Immagine | Esposizione |
|---|---|---|
| Traefik v3 | `traefik:v3.3` | 80 → redirect 443; 443 con certificati Let's Encrypt (HTTP-01) |
| Web (SPA) | `ghcr.io/antoniosiracusa/safe-web` (nginx) | `https://DOMINIO/` |
| API | `ghcr.io/antoniosiracusa/safe-api` (gunicorn, 3 worker) | `https://DOMINIO/api/...` |
| WebSocket | stessa immagine (daphne) | `https://DOMINIO/ws/...` |
| Worker + beat | stessa immagine (Celery) | interni |
| Keycloak 26 | `quay.io/keycloak/keycloak:26.3` | `https://auth.DOMINIO/` |
| PostgreSQL 16 + PostGIS | `postgis/postgis:16-3.4` | interno, volume `db-data` |
| Redis 7 | `redis:7-alpine` | interno |
| MinIO (o Aruba Object Storage) | `minio/minio` | interno, volume `minio-data` |

API e SPA condividono l'origine (`DOMINIO`): niente CORS, cookie o WebSocket cross-origin. Keycloak
è l'unica seconda origine (`auth.DOMINIO`), presente nella CSP della SPA.

## DNS

Tre record `A` verso l'IP del server: `DOMINIO` (record `@`), `auth.DOMINIO` e `www.DOMINIO` (reindirizzato al dominio nudo). Se si usa Cloudflare come proxy:
modalità TLS "Full (strict)" e regola di esclusione della cache per `/api/*`; altrimenti DNS-only.

## Prima installazione

Prerequisiti: Ubuntu 24.04 con Docker Engine + Compose (immagine Aruba "Ubuntu 24.04 - Docker"),
accesso SSH con chiave, firewall 22/80/443 (già configurato sul server Aruba l'11/09/2026 insieme a
fail2ban, unattended-upgrades e login SSH solo con chiave).

```bash
# sul server, come root
git clone https://github.com/antoniosiracusa/safe.git /opt/safe-src    # oppure copia di deploy/
cp -r /opt/safe-src/deploy /opt/safe && cd /opt/safe
cp .env.production.example .env
nano .env            # dominio (in tutte le righe), segreti (openssl rand -base64 36), SMTP, token Mapbox
./install.sh         # render.sh + deploy.sh + cron di backup
```

Se il repository GitHub è privato, prima di `install.sh`: `docker login ghcr.io` con un token
personale (scope `read:packages`).

`install.sh` rifiuta di partire se in `.env` restano valori `CHANGE-ME`. Al primo avvio Traefik
ottiene i certificati (serve che il DNS punti già al server), PostGIS crea ruoli e database
(`db/init.prod.sh`), l'API applica le migrazioni (che includono vocabolari e ruoli), Keycloak
importa il realm generato (senza utenti demo, senza `safe-dev-cli`, con SMTP reale).

Poi:

```bash
docker compose --env-file .env -f docker-compose.prod.yml run --rm --no-deps api \
  python manage.py bootstrap_company --name "Società X S.p.A." --slug societax \
  --admin-email admin@societax.it --admin-first-name Nome --admin-last-name Cognome --invite
docker compose --env-file .env -f docker-compose.prod.yml run --rm --no-deps api \
  python manage.py load_istat_boundaries --year 2025 \
  --url https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2025/Limiti01012025_g.zip
```

Con `--invite` l'amministratore viene creato anche in Keycloak e riceve l'email di attivazione
(password + MFA); in alternativa crearlo dalla console `https://auth.DOMINIO/admin/` (utente
`KEYCLOAK_ADMIN`) con la stessa email. Al primo login OIDC l'utente `invited` diventa `active`.
Il primo amministratore ha anche il ruolo "Custode chiavi / DPO": è lui a inizializzare la chiave
della società (Gestione → Chiavi di cifratura) e a conservare le 24 parole di recupero.

## Aggiornamento

```bash
cd /opt/safe && ./deploy.sh            # immagini da .env (latest o tag fissato)
cd /opt/safe && ./deploy.sh v1.1.0     # rilascio con tag (creato in CI dal tag git v1.1.0)
```

`deploy.sh` rigenera i file da `.env`, scarica le immagini, applica le migrazioni e riavvia solo i
servizi cambiati. Tempo di indisponibilità: pochi secondi per l'API. Per tornare indietro:
`./deploy.sh <tag-precedente>` (le migrazioni non vengono annullate: verificare le note di rilascio).

## Backup e ripristino

- `backup.sh` (cron 02:30): `pg_dumpall` di SAFE e Keycloak, compresso e cifrato con AES-256
  (`BACKUP_PASSPHRASE`), in `/opt/safe/backups` per `BACKUP_KEEP_DAYS` giorni; copia su bucket S3
  esterno se `BACKUP_S3_*` è impostato, conservata `BACKUP_S3_KEEP_DAYS` giorni (default 90).
  In produzione: Backblaze B2, bucket privato `safecivetta-backup` (endpoint
  `s3.eu-central-003.backblazeb2.com`, chiave applicativa limitata al bucket, ciclo di vita del
  bucket "Keep only the last version" così le cancellazioni liberano spazio). Log in
  `/var/log/safe-backup.log`.
- Snapshot della macchina dal pannello Aruba: utile in aggiunta, non in sostituzione.
- I file su MinIO (PDF, export) sono rigenerabili e non fanno parte del backup.
- `restore-test.sh`: prova di ripristino dell'ultimo backup in un PostgreSQL temporaneo (conteggi di
  società, utenti, eventi, Keycloak), poi rimosso. Eseguita il 12/09/2026; da ripetere ogni anno.
- `monitor.sh` (cron ogni ora, riepilogo lunedì 08:00): disco, container, API, Keycloak, scadenza
  certificato, backup < 26 h e copia esterna. Email a `ALERT_EMAIL` quando lo stato cambia;
  `./monitor.sh --test` invia un'email di prova. Log in `/var/log/safe-monitor.log`. In aggiunta è
  consigliato un controllo esterno di raggiungibilità (es. UptimeRobot su https://DOMINIO/api/v1/health).

Ripristino su un server vuoto (dopo `install.sh`):

```bash
cd /opt/safe
docker compose --env-file .env -f docker-compose.prod.yml stop api ws worker beat keycloak
gpg --batch --passphrase "$BACKUP_PASSPHRASE" -d backups/safe-YYYYMMDD-HHMM.sql.gz.gpg | gunzip \
  | docker compose --env-file .env -f docker-compose.prod.yml exec -T db psql -U postgres -d postgres
./deploy.sh
```

Provare il ripristino su staging **prima** del go-live e almeno una volta l'anno.

## Operazioni ricorrenti

| Quando | Cosa |
|---|---|
| ogni notte | backup automatico (verificare il log una volta a settimana) |
| ogni notte | retention: anonimizzazione persone scadute (beat) |
| ogni mese | `./deploy.sh` con le immagini aggiornate dalla CI (dipendenze e base image) |
| ogni anno | `load_istat_boundaries` con la nuova edizione; rotazione dei segreti; test del recupero chiavi |
| al bisogno | `docker compose ... logs -f api` / `traefik` / `keycloak` per diagnosi |

## Sicurezza operativa

- Segreti solo in `/opt/safe/.env` (permessi 600), mai in git. Rotazione: cambiare il valore in
  `.env` e rilanciare `deploy.sh` (per le password del database serve anche `ALTER ROLE`).
- Traefik: HSTS, TLS ≥ 1.2, header di sicurezza; l'API aggiunge CSP `default-src 'none'` e
  `no-store`; la SPA ha la propria CSP nel template nginx.
- Keycloak: brute force detection, password policy (12 caratteri, storico 3), sessioni 30 min di
  inattività, MFA attivabile per utente (`mfa_required` nell'invito). La console admin è raggiungibile
  solo con l'utente `KEYCLOAK_ADMIN`: usare una password lunga e attivare OTP al primo accesso.
- Accesso al server: solo chiave SSH, fail2ban, aggiornamenti di sicurezza automatici (riavvio
  manuale quando `/var/run/reboot-required` esiste).
- Le chiavi di cifratura dei dati identificativi non stanno sul server in chiaro: il recupero è
  descritto in [runbook-M7.md](runbook-M7.md).

## Passaggio a Aruba Object Storage (opzionale)

1. Creare il bucket `safe-files` e le chiavi di accesso nel pannello Aruba.
2. In `.env`: `S3_ENDPOINT_URL=https://<endpoint-aruba>`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
   `S3_REGION` come indicato dal pannello.
3. Rimuovere il servizio `minio` da `docker-compose.prod.yml` (o lasciarlo spento) e rilanciare `deploy.sh`.
4. Per i backup: bucket separato `safe-backup` e le variabili `BACKUP_S3_*`.
