# Runbook M7 · Cifratura end-to-end, audit, retention, hardening

## Modello (docs/01-architettura.md §7, docs/07-dpia §5)

| Oggetto | Dove sta | Chi lo apre |
|---|---|---|
| Chiave **personale** (X25519) | pubblica su `user_key.public_key`; privata cifrata con `secretbox(Argon2id(passphrase))` in `private_key_encrypted` | solo il browser dell'utente con la passphrase (in memoria, mai in storage; blocco dopo 15 minuti di inattività, al logout, o manuale) |
| Chiave **società** (X25519, versionata) | pubblica su `company_key`; privata **mai sul server in chiaro**: sigillata per ogni custode (`company_key_grant.wrapped_private_key`, sealed box verso la pubblica personale) e cifrata con il codice di recupero (`company_key_recovery`) | custodi con grant attiva, dopo aver sbloccato la chiave personale |
| Dati identificativi persona | `person.pii_ciphertext` = XChaCha20-Poly1305 con data key casuale; `pii_key_wrapped` = data key sigillata per la pubblica società; `pii_fields` solo nomi dei campi | chi ha `persons.reveal_identity` **e** una grant: `GET /persons/{id}/identity` restituisce ciphertext + data key sigillata + grant; la decifratura avviene nel browser; ogni lettura è in audit e limitata a 30/min |
| Codice di recupero | 24 parole BIP-39 (256 bit) mostrate **una sola volta** al custode | procedura di recupero (`crypto.recovery`, 5 letture/ora) |

Chi cifra: chiunque abbia `persons.edit` (basta la pubblica società, `GET /crypto/company-key`).
Il form persona ha la sezione "Dati identificativi (cifrati)": nome, cognome, data di nascita, telefono,
email, indirizzo, codice assicurazione/skipass, consegnato a, documento di riconoscimento (tipo, rilasciato da,
numero; dal 14/09/2026). Con chiave sbloccata e grant, i valori
esistenti si possono mostrare (drawer evento e form) e modificare.

## Procedure

**Prima chiave personale**: lucchetto in alto → "Crea la chiave" → passphrase (≥ 12 caratteri). Argon2id
interattivo (64 MiB) nel browser. Passphrase dimenticata → "Rigenera": nuova coppia, grant revocate
automaticamente (il server confronta la chiave pubblica), un custode ri-concede.

**Inizializzazione chiave società** (Gestione › Chiavi, `crypto.manage_keys`): con chiave personale
sbloccata → "Inizializza": il browser genera la coppia, sigilla la privata per sé, cifra la privata con il
codice di recupero e carica tutto (`POST /crypto/company-key`). Le 24 parole vanno trascritte e
conservate offline; la chiusura del dialogo richiede la conferma esplicita.

**Abilitare un custode**: l'utente crea la propria chiave; il custode sceglie l'utente da "Abilita un
utente" (solo utenti attivi con chiave) → la privata società viene ri-sigillata con la sua pubblica
(`POST /crypto/grants`). Revoca da tabella; l'ultimo custode non è revocabile (`last_custodian`).

**Rotazione** (`POST /crypto/company-key/rotate` + `GET/POST …/rewrap`): nuova versione attiva, la
vecchia diventa `retired`; il browser del custode scarica a lotti di 200 le data key sigillate con le
versioni precedenti, le apre con la vecchia privata e le ri-sigilla con la nuova (barra di avanzamento).
I ciphertext non cambiano. Gli altri custodi ricevono una nuova abilitazione. Nuovo codice di recupero.

**Recupero** (`crypto.recovery`): "Recupero con codice" → 24 parole → il browser decifra la privata società
dal kit (`GET /crypto/recovery`), verifica che corrisponda alla pubblica attiva, crea la grant per chi
recupera e **un nuovo kit** (`POST /crypto/recovery`, il precedente è invalidato). Tutto in audit
(`crypto.recovery_read`, `crypto.recovery_used`). Test annuale in staging con chiave di prova.

## Audit (`audit.view`)

`GET /audit-logs` (filtri `action`, `actor`, `object_type`, `object_id`, `event`, `date_from/to`),
`GET /audit-logs/actions`, `GET /audit-logs/export` (CSV, a sua volta in audit). Pagina Gestione › Audit
log; nel drawer evento la scheda "Storico" mostra le operazioni sull'evento. La tabella `audit_log` è
**append-only**: un trigger rifiuta UPDATE e DELETE (eccetto il purge di retention con
`SET LOCAL app.audit_purge = 'on'`). Per costruzione non contiene valori di dati personali.

## Retention (`company.retention`)

`GET/PATCH /company/retention` (anni per identificativi e audit, 1-30), `POST /company/retention/run`
(job). Anonimizzazione: persone con evento più vecchio di `retention_identity_years` perdono `pii_*`,
iniziali ed età (resta `age_class_snapshot`, quindi le statistiche non cambiano); `anonymized_at` viene
valorizzato e l'azione è in audit. Anonimizzazione anticipata su richiesta dell'interessato:
`POST /persons/{id}/anonymize` (`reason` in audit). Beat giornaliero `safe.apps.rescue.retention_run`
per tutte le società; il purge dell'audit segue `retention_audit_years`. Scheda "Conservazione e
anonimizzazione" nelle Impostazioni.

## Hardening

- `SecurityHeadersMiddleware`: `X-Content-Type-Options`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy`, `X-Frame-Options: DENY`; sull'API `Content-Security-Policy: default-src 'none'`
  e `Cache-Control: no-store`; **rifiuto (400 `pii_in_url`) di query string con nomi di dati personali**
  (mai PII in URL né nei log degli accessi).
- Throttling DRF: utenti 600/min, anonimi 60/min, `identity` 30/min, `recovery` 5/ora, `invite` 30/ora.
- Test di sicurezza (`tests/test_audit_retention_security.py`): header, PII in URL, throttling,
  nessun campo identificativo nelle risposte di eventi/persone né nei metadati di audit, campi in chiaro
  ignorati dal serializer. Matrice permessi estesa alle rotte crypto/audit/retention.
- CI: `pip-audit` e `npm audit --audit-level=high` (avviso), ESLint (`npm run lint`, angular-eslint).
- Produzione (già in `settings/prod.py`): HSTS, cookie sicuri, TLS terminato dal reverse proxy.

## Verifiche

```bash
docker compose run --rm api sh -c "ruff check . && mypy safe && pytest"   # 153 test
cd frontend && npm run lint && npm test -- --watch=false --browsers=ChromeHeadless && npm run build -- --configuration=production
```

Verificato nel browser l'11/09/2026 sulla società demo: creazione chiave personale, inizializzazione
chiave società con codice di 24 parole, persona salvata con nome/cognome/telefono cifrati (a database
solo 100 byte di ciphertext, nessuna stringa in chiaro), decifratura con "Mostra" nel drawer, audit
`person.identity_read`, pagina Audit log, scheda retention. Backend: round trip sealed box con PyNaCl,
rotazione con re-wrap, recupero, immutabilità dell'audit, anonimizzazione.

## Note tecniche e rinvii

- libsodium (`libsodium-wrappers-sumo`) è servito come script separato `public/vendor/sodium.js`
  generato da `npm run vendor:sodium` (esbuild, IIFE) prima di start/build/test: la build ESM del pacchetto
  usa top-level await (non supportato dal bundler Angular) e quella CommonJS non è servibile dal dev
  server. Il file è ignorato da git.
- Frazionamento Shamir del kit di recupero (opzionale nel DPIA): non implementato; il modello lo prevede.
- Cifratura dall'app mobile: stesse primitive; l'app non fa parte di questo progetto.
- OWASP ZAP baseline e scansione delle immagini: da eseguire sull'ambiente di staging (non in questa CI).
