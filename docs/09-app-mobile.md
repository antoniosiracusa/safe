# 09 · Piano dell'app mobile

Stato di partenza (12/09/2026): il portale è in produzione; l'API è già predisposta per il mobile
(client Keycloak `safe-mobile` pubblico con PKCE e redirect `safe://auth/callback`, registrazione
dispositivi con codice di arruolamento via QR e autorizzazione dell'amministratore, creazione eventi
idempotente con `client_uuid`, sincronizzazione con `updated_since`, chiave pubblica della società
scaricabile per cifrare i dati identificativi sul dispositivo). Manca solo l'app.

## 1. Obiettivo

Permettere al soccorritore di registrare l'intervento **in pista, dal telefono, anche senza rete**,
con posizione GPS automatica e dati identificativi cifrati sul dispositivo, e completare il rapporto
dal portale a fine turno. Non sostituisce il portale: lo alimenta.

## 2. Due strade possibili

| | A · App web installabile (PWA) | B · App nativa (Flutter, iOS + Android) |
|---|---|---|
| Cos'è | il portale attuale, reso installabile sul telefono, con una "modalità pista" ottimizzata e funzionamento offline | applicazione da store, codice separato dal portale |
| Offline | sì (coda locale, sincronizzazione al ritorno della rete) | sì, più robusto (database locale) |
| GPS, fotocamera | sì tramite browser | sì, con precisione e controllo maggiori |
| Distribuzione | nessuno store: si apre safecivetta.it e si "aggiunge alla schermata Home" | App Store e Google Play (account sviluppatore, revisione Apple, aggiornamenti tramite store) |
| Notifiche push | limitate su iPhone | complete |
| Cifratura E2E | già pronta (stesso codice del portale) | da riscrivere con libsodium nativo |
| Registrazione dispositivo via QR | non necessaria (stesso login del portale) | come previsto (QR + autorizzazione admin) |
| Sforzo stimato | 12-15 giornate | 45-60 giornate + manutenzione store |
| Costi ricorrenti | nessuno | Apple Developer 99 €/anno, Google Play 25 € una tantum |
| Tempi | 3-4 settimane | 3-4 mesi |
| Pronta per la stagione 2026/2027 | sì | difficile (revisione Apple, collaudo in campo) |

**Raccomandazione: strada A subito, strada B solo se dopo una stagione emergono bisogni che la PWA non copre**
(notifiche push affidabili, lavoro prolungato senza rete, integrazione con radio o dispositivi).
La PWA riusa tutto il codice esistente, compresa la cifratura già collaudata, e costa un quarto.

## 3. Cosa fa la "modalità pista" (PWA)

1. **Avvio rapido**: icona sulla Home del telefono, apertura a schermo intero, accesso con le stesse
   credenziali del portale; la sessione resta valida secondo le regole di Keycloak.
2. **Nuovo intervento in 60 secondi**: una schermata sola con i campi essenziali (ora proposta,
   squadra predefinita, zona e pista con ricerca, posizione GPS con precisione mostrata e possibilità
   di correggerla sulla mappa, causa, tipo di evento); il resto si compila dopo.
3. **Persona soccorsa essenziale**: età, genere, nazionalità, diagnosi presunta, destinazione, mezzo
   di evacuazione; dati identificativi cifrati subito con la chiave della società (serve la chiave
   personale sbloccata: la passphrase può essere ricordata per la durata del turno con sblocco
   biometrico del telefono).
4. **Offline**: se manca la rete l'intervento resta nella coda locale (cifrata) e viene inviato appena
   possibile; l'idempotenza con `client_uuid` evita duplicati; indicatore "da inviare: N".
5. **I miei interventi di oggi**: elenco, stato di invio, apertura per completare o correggere.
6. **Sincronizzazione**: vocabolari, zone, piste e chiave pubblica scaricati all'avvio e aggiornati con
   `updated_since`, così i menu funzionano anche offline.
7. **Foto** (facoltativo, da decidere): scatto allegato all'evento, cifrato come i dati identificativi.
   Oggi il modello dati non prevede allegati: è l'unica parte che richiede lavoro sul server.

Fuori ambito della prima versione: notifiche push, mappa completa offline (solo l'ultima area vista
resta in cache), lettura del QR dello skipass, firma su schermo.

## 4. Lavori lato server (comuni a entrambe le strade)

- Endpoint compatto di sincronizzazione iniziale (vocabolari + territorio + chiave società in una
  chiamata) e `updated_since` verificato su tutte le liste.
- Allegati foto cifrati (se richiesti): modello, storage su MinIO, quota, retention.
- Verifica dei limiti di richieste (rate limiting) per la sincronizzazione a raffica dopo l'offline.
- Per la strada B: pubblicazione dei link agli store nel QR di arruolamento, endpoint per notifiche push.

## 5. Fasi e tempi (strada A)

| Fase | Contenuto | Durata | Chi |
|---|---|---|---|
| 0 · Decisioni | piattaforme, foto sì/no, sblocco biometrico, elenco campi essenziali | 1 settimana | Consorzio |
| 1 · Fondamenta PWA | manifest, service worker, cache dell'applicazione e dei dati di riferimento, installazione su iPhone e Android, test su 3 telefoni reali | 3 giorni | fornitore |
| 2 · Modalità pista | schermata nuovo intervento, GPS, persona essenziale, cifratura, coda offline con sincronizzazione | 6 giorni | fornitore |
| 3 · Rifiniture | elenco "oggi", indicatori di stato, sblocco biometrico, guida rapida mobile, test di campo con 2-3 soccorritori | 3 giorni | fornitore + Consorzio |
| 4 · Foto (opzionale) | allegati cifrati lato server e app | 3 giorni | fornitore |
| Collaudo in pista | prova reale prima dell'apertura impianti | 1-2 settimane | Consorzio |

Totale: 12-15 giornate di sviluppo, calendario di 4-6 settimane; con avvio a ottobre 2026 la modalità
pista è pronta per l'apertura della stagione. Corrispettivo secondo il contratto: giornate a
preventivo (480 €/giorno), quindi indicativamente 5.800-7.200 € + IVA, foto comprese.

## 6. Rischi e attenzioni

- **iPhone e offline**: Safari limita lo spazio e cancella la cache delle app web non usate per
  settimane; la coda offline va svuotata a ogni rientro in rete e il rischio è accettabile per un uso
  quotidiano in stagione. Se il Consorzio vuole garanzie forti sul lavoro offline prolungato, meglio
  la strada B.
- **Chiave personale sul telefono**: la passphrase non deve restare in chiaro; lo sblocco biometrico
  usa il portachiavi del sistema. In caso di furto del telefono l'amministratore disattiva l'utente e
  un custode revoca l'abilitazione.
- **Batteria e GPS**: acquisizione della posizione solo alla creazione dell'intervento, non in
  continuo.
- **Dati personali nei campi liberi**: stesse regole del portale; in pista è più facile sbagliare,
  la schermata rapida non ha campi liberi tranne una nota breve con avviso.

## 7. Decisioni richieste al Consorzio

1. Strada A (PWA) o B (nativa): raccomandata A.
2. Foto degli interventi: sì o no; se sì, con che regole di conservazione.
3. Sblocco biometrico della chiave personale per il turno: sì o no.
4. Quali campi sono "essenziali" in pista (proposta: ora, squadra, zona, pista, posizione, causa,
   tipo evento; persona: età, genere, nazionalità, diagnosi, destinazione, mezzo).
5. Telefoni di riferimento per il collaudo (modelli, versione del sistema) e 2-3 soccorritori
   disponibili a provarla in pista.
