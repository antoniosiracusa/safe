# 00 · Domande di chiarimento e assunzioni di lavoro

Stato: **in attesa di risposta**. Per ogni punto è indicata l'assunzione con cui i documenti di Fase 1
sono stati redatti; se confermi senza rispondere, vale l'assunzione. Le risposte cambiano
il piano solo dove indicato con ⚠.

Fonti analizzate nella cartella di lavoro:

| File | Cosa ci ha detto |
|---|---|
| `testo base.odt` | Analisi del portale di riferimento (SAFE v5.2.37, Motorialab): moduli API, permessi osservati, modello dati, vocabolari. |
| `report-evento-*.pdf` | Layout del rapporto di intervento: il PDF stampa **solo iniziali** di nome e cognome, età, città e nazione; il form reale è molto più ricco del modello minimo richiesto. |
| `export.xlsx` | Tracciato dell'export eventi attuale (18 colonne). Serve come formato di import storico. |
| `A01_*.xls`, `Lista soccorsi *.pdf` | Tracciato **A01 Regione Veneto** (elenco infortuni per Provincia, art. 49 c.4 L.R. 21/2008): una riga per persona, fasce orarie, sesso, fasce età 0-10…>80, pista con **codice regionale**, attrezzatura, tipologia, colonna "soccorso congiunto con 7° RGT Alpini". Le due liste (Carabinieri, Truppe Alpine) contengono gli stessi incidenti visti da due squadre: da qui i "duplicati raggruppati". |
| `comunicazione elenco infortuni.docx` | Lettera di trasmissione alla Provincia di Belluno: destinatario e base giuridica dell'export regionale. |

---

## A. Perimetro funzionale

**Q1 · Modello dati esteso.** Il modello minimo richiesto copre ~40 campi; il rapporto di intervento del portale di riferimento ne ha circa 90 (chiamante, ora chiamata, tempo dall'incidente, altitudine, caratteristiche luogo, traffico, innevamento, tipo evento, operatori; ruolo persona, stato attrezzatura, altre protezioni, soccorso rifiutato, consegnato a, codice assicurazione, skipass, indirizzo, telefono, email, luogo di nascita…).
→ *Assunzione:* implemento il modello minimo come nucleo obbligatorio e aggiungo i campi estesi come **opzionali** (nullable, sezione "Dati estesi" del form), così il PDF può replicare il report di riferimento e l'app mobile futura non richiede una migrazione. Statistiche e aggregati usano solo il nucleo. ⚠ Se rispondi "solo minimo", M2 e M5 si accorciano di ~4 giorni.

**Q2 · Export regionale.** Il tracciato confermato è l'A01 Veneto verso la Provincia (XLS + PDF di accompagnamento).
→ *Assunzione:* motore di export "a template" con A01 come primo template; altri enti (es. trauma center, Svizzera) fuori perimetro ma aggiungibili come template. Le fasce d'età A01 (0-10, 11-20, …, oltre 80) e le fasce orarie (08-11, 11-14, 14-17, 17-08) sono proprietà del template, distinte dalle classi statistiche (0-17, 18-24, …).

**Q3 · Regola di raggruppamento duplicati (anteprima export).** Proposta: due persone sono "duplicate" se appartengono a eventi di **squadre diverse** della stessa società, stessa data, stessa pista (o entrambe senza pista), |Δ orario| ≤ 30 min, stesso genere, stessa classe d'età A01, stessa attrezzatura. Il gruppo viene esportato una sola volta con il flag "soccorso congiunto".
→ *Assunzione:* regola come sopra, parametri (Δ minuti, campi confrontati) configurabili per società. Confermi?

**Q4 · Persone escluse perché "in edifici".** Proposta: esclusione se `location_type = Edificio` **oppure** il punto ricade in un poligono `building` OSM del tile set (verifica spaziale).
→ *Assunzione:* entrambe le condizioni, con elenco nominativo (ID evento) nell'anteprima per permettere la correzione prima dell'invio.

**Q5 · Enti pubblici regionali come utenti del portale?** Ricevono solo i file oppure accedono a statistiche aggregate cross-società su base amministrativa?
→ *Assunzione:* nella prima release **non accedono**; ricevono i file generati. Lo schema prevede però un tipo di tenant `authority` con permesso `stats.cross_company` + `filter_by_administrative_area` per una release successiva.

**Q6 · Visibilità per squadra.** Un soccorritore vede tutti gli eventi della società o solo quelli della propria squadra?
→ *Assunzione:* lettura a livello società per default; scrittura limitata alle squadre di appartenenza salvo permesso `events.edit_any_team`. Il permesso `events.view_own_teams_only` restringe la lettura per profili "soccorritore".

**Q7 · Semantica di blocco/sblocco evento.** "Eventi sbloccati" nel riepilogo stagione implica un ciclo di vita.
→ *Assunzione:* l'evento viene **bloccato** (`locked_at`) alla chiusura del rapporto (dal mobile o da web) oppure automaticamente dopo N ore configurabili (default 48). Modificare un evento bloccato richiede `events.unlock`; lo sblocco è tracciato in audit e l'evento conta come "sbloccato" nella stagione.

**Q8 · Definizione di `fully_valid` / `valid`.** Calcolati o impostati a mano?
→ *Assunzione:* **calcolati** a ogni salvataggio da regole configurabili per società. Default: evento valido se presenti data/ora, zona, (pista o tipo di luogo), causa, geometria; persona valida se presenti età, genere, diagnosi presunta, almeno un mezzo di evacuazione. Un evento è `fully_valid` se valido esso stesso e tutte le persone lo sono. Override manuale non previsto.

**Q9 · Statistiche ed eventi non validi.** Includerli?
→ *Assunzione:* sì, sempre inclusi (regola "mai scartare"), con filtro globale opzionale `valid_only=true`.

**Q10 · Sezioni del portale di riferimento non richieste** (home con KPI e news, stato apertura piste, report generati/richieste, contabilità comprensorio, condivisione eventi tra squadre).
→ *Assunzione:* fuori perimetro. Prevedo solo una home minimale con KPI e le card dei moduli (anche bloccati). Lo schema non le contempla ma non le impedisce.

## B. Privacy e cifratura

**Q11 · Modello di cifratura (punto più importante).** Proposta: cifratura **end-to-end lato client**. Il server custodisce solo ciphertext e chiavi pubbliche; non è mai in grado di decifrare. Conseguenze:
- il PDF del rapporto e tutti gli export contengono solo **iniziali + età + nazione** (come già fa il portale di riferimento);
- la ricerca per nome non è possibile (opzionale: indice cieco HMAC per ricerca esatta, non in MVP);
- l'app mobile cifra al momento della raccolta con la chiave pubblica della società;
- recupero tramite "kit di recupero" (chiave privata società cifrata con codice di 24 parole custodito offline) e opzionalmente frazionamento Shamir 2-di-3 tra custodi.
→ *Assunzione:* modello come sopra. ⚠ Se invece servono nomi in chiaro nel PDF o negli export, occorre una decifratura server-side per-sessione (chiave sbloccata dal browser e inviata al worker in memoria): meno robusta, +3 giorni in M7. Dimmi quale.

**Q12 · Quali campi cifrare.** Oltre a nome e cognome: luogo di nascita, indirizzo, civico, città, telefono, email, codice assicurazione, codice skipass, "consegnato a" (contiene nomi di terzi), note libere?
→ *Assunzione:* tutti quelli elencati sono cifrati in un unico blob per persona (`pii_ciphertext`), **inclusa la città** (in chiaro nel riferimento, ma combinata con iniziali ed età è re-identificante). Nazione, età, genere restano in chiaro. Le note libere di evento e persona restano in chiaro ma il form avvisa di non inserire dati identificativi.

**Q13 · Retention.** Proposta: dati identificativi cifrati conservati **10 anni** dalla data evento (prescrizione ordinaria art. 2946 c.c., contenziosi assicurativi), poi anonimizzazione automatica (cancellazione ciphertext e iniziali; età sostituita dalla classe). Dati statistici pseudonimizzati conservati senza limite. Audit log 10 anni.
→ *Assunzione:* valori di default configurabili per società; **da validare con il DPO** della società.

**Q14 · MFA per i custodi delle chiavi.**
→ *Assunzione:* TOTP obbligatorio (required action Keycloak) per chi possiede `crypto.manage_keys` o una grant di decifratura; opzionale per gli altri.

## C. Integrazioni e dati

**Q15 · Import storico.** Ho il tracciato eventi (`export.xlsx`). Manca un campione dell'export **persone** del portale attuale, e va capito se contiene nomi in chiaro o già pseudonimizzati.
→ *Assunzione:* import eventi + persone da CSV/XLSX con mapping configurabile; se i nomi arrivano in chiaro l'import avviene **da browser** (cifratura client-side) e non da linea di comando. Ti chiedo il campione persone prima di M2.

**Q16 · App mobile.** Esiste già un'app da collegare o è tutta futura?
→ *Assunzione:* futura. L'API nasce già pronta per il mobile (chiave di idempotenza `client_uuid`, `updated_since`, registrazione dispositivo con autorizzazione dell'amministratore, QR con link agli store + codice di arruolamento).

**Q17 · Identity provider.** Keycloak nuovo e self-hosted, oppure un IdP esistente (Entra ID, altro Keycloak)?
→ *Assunzione:* Keycloak 26 dedicato, gestito in Docker Compose con il resto dello stack; realm unico `safe`, client `safe-web` (PKCE), `safe-mobile` (PKCE), account di servizio per gli inviti.

**Q18 · Cartografia satellitare e licenze.** Lo stile "satellite" richiede una fonte raster: Sentinel-2 cloudless di EOX è CC-BY-NC-SA (non usabile in commerciale), ESRI World Imagery richiede accettazione termini ArcGIS, MapTiler/Mapbox sono a canone.
→ *Assunzione:* base OpenMapTiles generata con Planetiler (estratto Italia/Alpi), terreno da Copernicus DEM 30 m convertito in terrain-RGB, contour da TINITALY; satellite tramite **MapTiler Cloud** (chiave in configurazione runtime) sostituibile. ⚠ Confermare budget o fonte alternativa.

**Q19 · Confini ISTAT.** Uso i "Confini delle unità amministrative a fini statistici" ISTAT (edizione 1° gennaio 2026, WGS84), caricati in PostGIS, con `codice regionale pista` mantenuto sull'anagrafica pista.
→ *Assunzione:* confermato; aggiornamento annuale via comando di management.

**Q20 · Volumi attesi.** Numero di società, squadre, comprensori, eventi/stagione, utenti concorrenti.
→ *Assunzione:* 10-20 società, 2-6 squadre ciascuna, 300-1.500 eventi/stagione per società, < 50 utenti concorrenti. Il benchmark di accettazione resta 100.000 eventi.

**Q21 · Lingue.** IT/EN/DE confermate; il tedesco serve per clienti altoatesini?
→ *Assunzione:* IT default, EN e DE complete per UI e vocabolari; traduzioni vocabolari mantenute in tabella.

**Q22 · Hosting, CI, repository.**
→ *Assunzione:* monorepo su GitHub con GitHub Actions; produzione su singolo host Docker Compose + Traefik (TLS Let's Encrypt), backup PostgreSQL con pgBackRest; SMTP relay esterno per gli inviti. Kubernetes non necessario ai volumi assunti.

---

## Sintesi delle decisioni che prendo in autonomia (revocabili)

1. Angular 20 + PrimeNG (una sola libreria UI, non due come nel riferimento), Transloco per i18n a runtime.
2. Django 5 + DRF, PostGIS, Celery/Redis, Django Channels; validazione JWT via JWKS senza sessioni server.
3. TileServer-GL come tile server (serve anche le immagini statiche per la mappa nel PDF); layer piste/impianti generati con tippecanoe da PostGIS.
4. Isolamento tenant a tre livelli: middleware, manager Django, Row Level Security PostgreSQL.
5. Cifratura con libsodium (X25519 sealed box + XChaCha20-Poly1305 envelope) in browser e in Python (PyNaCl).
6. Permessi come codici stringa in tabella, ruoli come semplici template di permessi.
