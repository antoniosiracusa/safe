# 05 · Mappa delle schermate e wireframe testuali

## 1. Struttura di navigazione

```
/:lang/                      Login (redirect a Keycloak) → Home
/:lang/home                  KPI + card moduli (anche bloccati)
/:lang/stats/zone            Statistiche · Riepilogo zona
/:lang/stats/demographics    Statistiche · Demografia
/:lang/stats/typology        Statistiche · Tipologia
/:lang/stats/geography       Statistiche · Geografia
/:lang/stats/weather         Statistiche · Meteo
/:lang/stats/season          Statistiche · Riepilogo stagione
/:lang/data/events           Dati · Eventi        (+ /data/events/:id drawer dettaglio/modifica)
/:lang/data/persons          Dati · Persone       (+ /data/persons/:id drawer)
/:lang/map                   Mappa
/:lang/exports/regional      Esportazioni · Enti regionali (wizard)
/:lang/exports/dataset       Esportazioni · Dataset CSV/XLSX
/:lang/exports/history       Esportazioni · Storico e download
/:lang/admin/users           Gestione · Utenti (tab attivi / inviti / disattivati)
/:lang/admin/teams           Gestione · Squadre
/:lang/admin/devices         Gestione · Dispositivi + QR
/:lang/admin/territory       Gestione · Comprensori, zone, piste
/:lang/admin/lookups         Gestione · Vocabolari
/:lang/admin/settings        Gestione · Impostazioni società e retention
/:lang/admin/keys            Gestione · Chiavi di cifratura (grant, recupero, rotazione)
/:lang/admin/audit           Gestione · Audit log
/:lang/account               Profilo, lingua, chiave personale, MFA
```

Layout comune: barra superiore (logo, selettore lingua, lucchetto stato chiave, utente),
menu laterale a sezioni, **barra filtri globale** sotto la barra superiore in tutte le pagine
di Statistiche, Dati, Mappa ed Esportazioni.

## 2. Stati standard (ogni pagina e ogni widget)

| Stato | Resa |
|---|---|
| **Caricamento** | skeleton della stessa forma del contenuto (card grafico grigia con titolo, righe tabella); mai spinner a schermo intero |
| **Vuoto** | illustrazione leggera + testo "Nessun evento per i filtri selezionati" + pulsante "Reimposta filtri"; nei grafici gli assi restano visibili con "Non classificato" a 0 |
| **Errore** | pannello in linea con codice errore, "Riprova", link "Copia dettagli"; mai il toast come unico feedback |
| **Permesso mancante** | il contenitore resta al suo posto, sfumato, con overlay: icona lucchetto, "Funzione non abilitata per il tuo profilo", "Contatta l'amministratore" (mailto se configurato); nessuna chiamata API viene emessa |
| **Chiave mancante** (dati identificativi) | banner giallo "Per vedere i dati identificativi sblocca la tua chiave" → dialog passphrase |
| **Offline / token scaduto** | banner in alto; le richieste vengono ritentate dopo il refresh silenzioso |

Accessibilità: ordine di tabulazione naturale, `aria-live="polite"` sugli aggiornamenti dei grafici,
ogni grafico ha una tabella dati alternativa accessibile ("Mostra come tabella"), contrasto ≥ 4.5:1.

## 3. Barra filtri globale

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Squadra [Tutte ▾]  Periodo [Stagione 2025/2026 ▾ | dal __/__/__ al __/__/__]           │
│ Comprensorio [Civetta ▾]  Zona [Val Fiorentina ▾]  [x] Solo validi   [Reimposta filtri] │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
- Sincronizzata con la query string (`?team=…&season=2025%2F2026&zone=…`); persistente tra
  le pagine; "Reimposta" riporta alla stagione corrente e a nessun altro filtro.
- Zona dipende dal comprensorio; cambiando comprensorio la zona incompatibile si azzera.
- Le opzioni vengono da `/filters/options` (una sola chiamata all'avvio).

## 4. Wireframe

### 4.1 Home
```
┌ KPI ──────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Eventi stagione   │ Persone          │ Ultima settimana │ Eventi da validare│
│ 266               │ 291              │ 0                │ 7                │
├ Moduli ───────────┴──────────────────┴──────────────────┴──────────────────┤
│ [Statistiche]  [Dati]  [Mappa]  [Esportazioni 🔒]  [Gestione 🔒]           │
│  card bloccata: "Funzione non abilitata · Contatta l'amministratore"       │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Statistiche · Riepilogo zona
```
[Barra filtri]
┌ Distribuzione annuale incidenti ───────────── [⤢][⬇]┐ ┌ Cumulativo ────────────── [⤢][⬇]┐
│ barre raggruppate: x = mese (giu→mag), serie=stagione│ │ linee cumulative per stagione     │
└──────────────────────────────────────────────────────┘ └───────────────────────────────────┘
┌ Tabella zona × stagione ───────────────────────────────────────────────────────────────┐
│ Zona            │ 2023/2024 (ev/pers) │ 2024/2025 │ 2025/2026 │ Totale                  │
│ Val Fiorentina  │ 210 / 231           │ 244 / 260 │ 266 / 291 │ 720 / 782                │
│ Totale          │ …                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```
Ogni card grafico ha: titolo, [⤢] schermo intero, [⬇] scarica PNG, menu "Mostra come tabella".

### 4.3 Statistiche · Demografia
Griglia 2 colonne: Età × Genere (barre affiancate) · Paesi (barre orizzontali top 10 + Altri + N.c.) ·
Connazionali vs stranieri per giorno settimana (barre impilate lun→dom) · Età × Diagnosi (impilato) ·
Età × Sede lesione (impilato). Selettore "Classi d'età: standard | A01".

### 4.4 Statistiche · Tipologia
Età × Causa · Distribuzione cause (ciambella) · Età × Attrezzatura · Età × Assicurazione ·
Età × Mezzo di evacuazione (primo mezzo) · Totale mezzi utilizzati (barre).

### 4.5 Statistiche · Geografia
```
┌ Eventi per comprensorio ─────┐ ┌ Eventi per difficoltà ───────┐
└──────────────────────────────┘ └──────────────────────────────┘
┌ Eventi per pista ──────────────────────────────────────────────┐
│ Mostra le prime [====●=====] 20 piste (di 27)                   │
│ barre orizzontali ordinate desc, ultima "Non classificato"      │
└────────────────────────────────────────────────────────────────┘
```
Lo slider aggiorna `limit` con debounce 300 ms e riflette il valore in query string (`slopes_limit`).

### 4.6 Statistiche · Meteo
Quattro ciambelle/barre: meteo, neve, vento, visibilità. Tutte con "Non classificato".

### 4.7 Statistiche · Riepilogo stagione (`stats.advanced`)
```
┌ Squadra                 │ Stagione attuale │ Settimana scorsa │ Sbloccati │ Non validi │ Elicottero ┐
│ Polizia Selva di Cadore │ 266              │ 0                │ 3         │ 7          │ 12         │
│ Totale                  │ 266              │ 0                │ 3         │ 7          │ 12         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```
Clic su "Non validi" → tabella Eventi con filtro `valid_only=false` e ordinamento per errori.

### 4.8 Dati · Eventi
```
[Barra filtri] + filtri specifici: pista, causa, bloccato, testo luogo
┌ 266 eventi │ [Colonne ▾] [Esporta ▾] [+ Nuovo evento] ───────────────────────────────────┐
│ ID  │ Data/ora ▾ │ Squadra │ Zona │ Pista │ Diff │ Causa │ Meteo │ Neve │ Valido │ 🔒 │ PDF │ … │
│ …   │ 18/01 10:05│ Polizia │ V.F. │ LE CIAUNE│ Azz│ Collis│ Sereno│ Comp│ ✓      │ 🔒 │ ⬇  │ ⋯ │
│ (scroll orizzontale, colonne congelate: ID, Data/ora)                                     │
├ Pagina 1 di 6 · 50 per pagina [25|50|100] ────────────────────────────────────────────────┤
```
Clic riga → drawer laterale "Evento" con tab: Dati · Persone (schede) · Mappa · Storico (audit).
Modifica inline nel drawer; se bloccato: banner "Evento bloccato il … · [Richiedi sblocco]".
PDF: clic → spinner sul pulsante; 200 apre il file, 202 mostra toast "Generazione in corso" e
notifica al completamento (WebSocket o polling).

### 4.9 Dati · Persone
Colonne: ID evento, Data/ora, Squadra, Zona, Pista, Iniziali (C. S.), Età, Genere, Paese,
Casco, Attrezzatura, Diagnosi, Sede, Mezzi (akja → ambulanza), Destinazione, Valido, PDF.
Drawer persona: sezione "Identità" con pulsante **Mostra dati identificativi** (attivo solo con
permesso + chiave sbloccata; ogni clic è in audit e mostra il badge "accesso registrato").
I dati decifrati restano visibili 60 s e mai nella tabella.

### 4.10 Mappa
```
┌ [Stile: Inverno ▾ | Estate | Satellite]  Layer: [x] Confini comprensorio [ ] Heatmap [x] Eventi ┐
│                                                                                                   │
│        ● 12        ● 3                popup: Evento 0192d… · 18/01/2026 10:05 · [PDF]            │
│                          ●                                                                        │
│  [+][−][⌂ centra sul comprensorio]                                          scala · attribuzioni  │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```
Stato vuoto: mappa centrata sul confine del comprensorio con messaggio. Stato errore tile server:
mappa in stile fallback (solo confini + eventi) e banner.

### 4.11 Esportazioni · Enti regionali (wizard 3 passi)
```
① Parametri: Template [Veneto A01 ▾] Stagione [2025/2026 ▾] Area [Provincia di Belluno ▾] Squadre [Tutte]
② Anteprima qualità del dato
   ┌ Persone totali 291 │ Escluse (edifici) 6 [vedi] │ Fuori area 2 [vedi] │ Duplicati raggruppati 41 (43 persone) [vedi] │ Esportabili 240 ┐
   ⚠ 14 eventi su piste senza codice regionale [correggi in Territorio]
③ Genera: formato [XLSX|XLS|PDF] → job → download + lettera di accompagnamento (DOCX precompilata, opzionale)
```
"[vedi]" apre una tabella con gli ID evento e link al drawer; il passo ③ è disabilitato finché
l'anteprima non è stata calcolata con i parametri correnti.

### 4.12 Esportazioni · Dataset
Scelta dataset (Eventi/Persone), formato (CSV/XLSX), colonne (multi-select), riepilogo filtri
attivi → "Genera" → riga nello storico con stato e download. Nota fissa: "Gli export non contengono
mai nome e cognome".

### 4.13 Gestione · Utenti
```
[Attivi (12)] [Inviti (2)] [Disattivati (3)]                                   [+ Invita utente]
│ Nome │ Email │ Squadre │ Ruoli │ Chiave │ Ultimo accesso │ Azioni (modifica, permessi, disattiva) │
Dialog invito: email, nome, cognome, lingua, squadre, ruolo template → "Invia invito"
Toast: "Invito inviato: l'utente riceverà un'email per impostare la password su Keycloak".
```

### 4.14 Gestione · Squadre
Tabella nome / corpo / utenti / eventi / attiva; dialog crea/modifica; disattivazione bloccata se ha eventi (messaggio).

### 4.15 Gestione · Dispositivi
```
┌ [Genera QR di arruolamento] → dialog con QR (safe://enroll?code=…), codice testuale, scadenza, link store ┐
│ Nome │ Utente │ OS │ Versione app │ Ultimo accesso │ Stato (In attesa / Autorizzato / Revocato) │ Azioni │
```

### 4.16 Gestione · Chiavi di cifratura
- Stato: "Chiave società v2 attiva dal …", elenco custodi con grant, pulsante "Concedi a…".
- Procedure guidate: **Inizializza** (genera, mostra codice di recupero 24 parole una sola volta, chiede conferma di trascrizione), **Recupero** (inserisci codice → ri-sigilla per te), **Rotazione** (progress bar del re-wrap).
- Pagina Account: "La mia chiave" (crea/cambia passphrase, stato sbloccata/bloccata).

### 4.17 Gestione · Audit log
Filtri: azione, utente, oggetto, periodo. Tabella: data, utente, azione, oggetto (link), IP. Export CSV (senza PII per costruzione).

## 5. Flussi chiave

1. **Primo accesso invitato**: email Keycloak → imposta password (+ TOTP se richiesto) → redirect SPA → `/me` → se `key_status.user_key = missing` e l'utente ha `persons.edit`, wizard "Crea la tua chiave personale".
2. **Sblocco chiave**: clic lucchetto → passphrase → derivazione Argon2id (Web Worker) → chiave in memoria → lucchetto verde; si blocca al logout, al cambio tab per > 15 min, o manualmente.
3. **Nuovo evento da web**: form a schede (Evento · Persone · Luogo su mappa) con salvataggio bozza; alla chiusura "Blocca rapporto".
