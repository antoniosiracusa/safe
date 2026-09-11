# 07 · Valutazione d'impatto sulla protezione dei dati (sintetica)

Documento preliminare ai sensi dell'art. 35 GDPR, da completare con il DPO del titolare.
Il trattamento rientra nei casi che richiedono la DPIA: dati relativi alla salute (art. 9),
su larga scala e con geolocalizzazione, di interessati vulnerabili (minori, persone infortunate).

## 1. Ruoli

| Ruolo | Soggetto |
|---|---|
| Titolare | Società di gestione del comprensorio (tenant) |
| Responsabile (art. 28) | Fornitore della piattaforma SAFE (hosting, manutenzione) — contratto ex art. 28 necessario |
| Sub-responsabili | provider hosting, provider satellite (solo tile, nessun dato personale), SMTP (solo email utenti interni) |
| Destinatari | Provincia/Regione (export A01, dati **non identificativi**), assicurazioni e autorità **solo su richiesta e fuori piattaforma** |
| Autorizzati | soccorritori, responsabili, amministratori, custodi delle chiavi della società |

## 2. Trattamenti

| # | Trattamento | Dati | Interessati | Base giuridica (da validare) |
|---|---|---|---|---|
| T1 | Raccolta del rapporto di intervento sul campo | identificativi (nome, cognome, nascita, indirizzo, contatti), sanitari (diagnosi presunta, sede lesione, destinazione), dati dell'incidente, posizione | persone soccorse, testimoni, accompagnatori | art. 6.1.c + art. 9.2.h (assistenza sanitaria/soccorso) e obblighi del gestore ex L.R. Veneto 21/2008 art. 49 e D.Lgs. 40/2021; per contenziosi art. 9.2.f |
| T2 | Gestione e consultazione nel back-office | come T1, con identificativi cifrati; consultazione pseudonimizzata | idem | idem |
| T3 | Analisi statistica interna e sicurezza piste | dati pseudonimizzati/aggregati | idem | art. 6.1.f (interesse legittimo: sicurezza), art. 9.2.j non necessario se aggregati |
| T4 | Comunicazione all'ente regionale (A01) | data, fascia oraria, sesso, fascia d'età, pista, attrezzatura, tipologia — nessun identificativo | idem | art. 6.1.c (L.R. 21/2008 art. 49 c.4) |
| T5 | Report PDF dell'intervento | pseudonimizzato (iniziali, età, città non inclusa) | idem | come T1 |
| T6 | Gestione utenti e dispositivi | nome, email, IP, dispositivo, log accessi | personale interno | art. 6.1.b/f |
| T7 | Audit log | id utente, azione, id oggetto, IP | personale interno | art. 6.1.c/f (accountability, art. 32) |
| T8 | Cartografia | posizione dell'evento (non dell'interessato in senso proprio) | — | come T1; il GeoJSON non contiene identificativi |

## 3. Principi e misure (privacy by design)

| Principio | Misura |
|---|---|
| Minimizzazione | modello minimo obbligatorio; campi estesi opzionali; città e contatti cifrati; export e PDF senza identificativi; GeoJSON solo geometria + data |
| Pseudonimizzazione (art. 4.5, 32) | liste e statistiche su iniziali + età + nazione; identificativi in blob cifrato separato |
| Cifratura (art. 32) | E2E lato client: X25519 sealed box + XChaCha20-Poly1305 (libsodium); il responsabile (fornitore) **non può** decifrare; chiavi private cifrate con Argon2id; TLS 1.2+ ovunque; dischi cifrati |
| Controllo accessi | OIDC + MFA per custodi; permessi granulari verificati server-side; RLS; grant di decifratura nominativa e revocabile |
| Accountability | audit log append-only di ogni accesso a identificativi, modifiche, export, sblocchi, gestione chiavi; conservazione 10 anni |
| Limitazione della conservazione | retention configurabile per società (default 10 anni per identificativi), anonimizzazione automatica; dati statistici anonimizzati senza limite |
| Esattezza | validazione, regole di validità, blocco rapporto, correzioni tracciate |
| Trasparenza | informativa da consegnare al soccorso (modulo cartaceo/QR, a cura del titolare); testo modello fornito in M7 |
| Diritti degli interessati | ricerca per identificativo non possibile senza chiave: procedura "ricerca assistita" del custode per data/pista/età; anonimizzazione anticipata su richiesta (`company.retention` + azione puntuale in audit) |
| Sicurezza applicativa | CSP, security headers, rate limiting, dipendenze scansionate, immagini scansionate, backup cifrati, test OWASP ZAP baseline |
| Nessun dato personale in URL/log | id opachi UUID; filtri senza testo libero identificativo; logger con scrubber; Sentry `send_default_pii=false`; corpi richiesta mai loggati |
| Data breach | il ciphertext senza chiavi è inutilizzabile → riduce l'obbligo di notifica agli interessati (art. 34.3.a); procedura di notifica al Garante entro 72 h nel runbook |

## 4. Rischi residui

| Rischio | Gravità | Probabilità | Trattamento |
|---|---|---|---|
| Re-identificazione da dati pseudonimizzati (iniziali + età + paese + data + pista) in comunità piccole | media | media | accesso alle liste solo a autorizzati; export regionale senza iniziali; aggregati con soglia minima 5 nelle viste cross-società (futuro) |
| Perdita delle chiavi (indisponibilità degli identificativi) | alta per il titolare | bassa | kit di recupero, ≥ 2 custodi, test annuale del recupero |
| Compromissione della postazione di un custode | alta | bassa | MFA, chiave in memoria solo a sessione sbloccata, timeout 15 min, revoca grant immediata |
| Note libere contenenti identificativi | media | media | avviso nel form, lint lato client (pattern nome/telefono), audit; possibilità di cifrare le note in una release successiva |
| Operatori (personale) nominati nel rapporto | bassa | alta | dato di personale interno, base giuridica contrattuale; visibile solo nel PDF |
| Fornitore con accesso a DB | media | bassa | E2E encryption; accesso amministrativo tracciato; contratto art. 28 |

## 5. Procedura di recupero chiavi (sintesi; procedura operativa in [runbook-M7.md](runbook-M7.md))

1. Alla creazione della chiave società il custode ottiene un **codice di recupero** (24 parole BIP39) mostrato una sola volta; il browser cifra la chiave privata con Argon2id(codice) e carica il blob (`company_key_recovery`). Il codice va conservato offline (cassaforte, DPO).
2. Opzionale: frazionamento Shamir 2-di-3 tra tre custodi (previsto dal modello dati, non ancora implementato nell'interfaccia).
3. Recupero (tutti i custodi hanno perso la chiave): un utente con `crypto.recovery` (MFA) apre "Recupero" → inserisce il codice → il browser decifra la chiave privata società → crea la propria grant → invita nuovi custodi → **genera un nuovo kit** (il vecchio viene invalidato) → tutto in audit.
4. Perdita della passphrase personale: l'utente rigenera la propria coppia; un custode gli ri-concede la grant. Nessun dato perso.
5. Test della procedura: almeno una volta l'anno, in ambiente di staging con chiave di test.

## 6. Conclusione preliminare

Con le misure descritte il rischio residuo per gli interessati è **basso**; il trattamento
può proseguire senza consultazione preventiva (art. 36) salvo diversa valutazione del DPO.
Punti aperti: basi giuridiche specifiche per Regione, testo dell'informativa, durata di
conservazione definitiva, contratto ex art. 28 con il fornitore.
