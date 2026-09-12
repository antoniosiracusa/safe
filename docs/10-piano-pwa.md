# 10 · Milestone M8 · Modalità pista (app web installabile)

Attuazione della strada A del [piano app mobile](09-app-mobile.md), decisa il 12/09/2026.
Obiettivo: modalità pista in uso reale all'apertura della stagione 2026/2027.

## Assunzioni di partenza (modificabili entro il 19/09/2026)

| Decisione | Assunzione adottata |
|---|---|
| Foto degli interventi | **no** nella prima versione (fase opzionale a fine piano) |
| Sblocco biometrico della chiave personale | **sì dove il telefono lo supporta** (WebAuthn con estensione PRF: Android/Chrome recenti, iOS 18+); altrimenti passphrase ricordata per il turno (8 ore) con conferma dell'utente |
| Campi essenziali evento | data/ora, squadra, zona, pista (o tipo di luogo), posizione GPS, causa, tipo di evento, nota breve |
| Campi essenziali persona | età, genere, nazionalità, ruolo, diagnosi presunta, sede lesione, mezzo di evacuazione, destinazione; dati identificativi (nome, cognome, data di nascita, telefono) |
| Telefoni di riferimento | un iPhone (iOS 17 o 18) e un Android recente (Chrome), forniti dal Consorzio per il collaudo |
| Uso offline | coda locale svuotata a ogni rientro in rete; nessuna garanzia oltre 7 giorni senza rete |

## Calendario

| Settimana | Date | Attività | Consegna |
|---|---|---|---|
| 0 | 15-19 set | Conferma delle assunzioni; scelta dei soccorritori e dei telefoni di prova; analisi tecnica (service worker, spazio di archiviazione su iOS, WebAuthn PRF) | assunzioni confermate |
| 1 | 22-26 set | **M8.0 Fondamenta**: manifest, icone, service worker con cache dell'applicazione e dei dati di riferimento (vocabolari, zone, piste, chiave società), banner "installa", pagina di stato offline; endpoint compatto `sync/bootstrap` e verifica di `updated_since` | portale installabile su iPhone e Android, funzionante offline in lettura |
| 2 | 29 set - 3 ott | **M8.1 Modalità pista, parte 1**: rotta `/pista`, schermata "nuovo intervento" a passi (dove, cosa, chi), GPS con precisione e correzione sulla mappa, salvataggio in coda locale (IndexedDB cifrata) | interventi creabili offline e inviati al rientro in rete, senza duplicati |
| 3 | 6-10 ott | **M8.1 parte 2**: persona soccorsa essenziale con cifratura dei dati identificativi sul telefono, sblocco biometrico o per turno, elenco "i miei interventi di oggi" con stato di invio, ripresa dell'invio dopo errori | flusso completo evento + persona in pista |
| 4 | 13-17 ott | **M8.2 Rifiniture e collaudo interno**: indicatori di rete e coda, gestione sessione scaduta offline, test su 4 telefoni reali, guida rapida mobile (2 pagine), aggiornamento guida operatori, test automatici | versione candidata; consegna ai soccorritori di prova |
| 5-7 | 20 ott - 7 nov | **Collaudo in campo** da parte del Consorzio (anche su strada o in cantiere, senza neve): raccolta segnalazioni, correzioni settimanali | elenco segnalazioni chiuso |
| 8 | 10-14 nov | **Rilascio** della modalità pista a tutti gli utenti; formazione breve (1 ora, anche da remoto) | in produzione |
| opz. | 17-21 nov | **M8.3 Foto cifrate**, se richieste: allegati sul server, scatto e cifratura nell'app, visualizzazione nel portale | in produzione |
| dic | apertura impianti | esercizio con assistenza rafforzata nelle prime due settimane | — |

Sviluppo: 12 giornate (M8.0-M8.2) + 3 opzionali (M8.3). Corrispettivo secondo contratto: a giornata, su ordine scritto.

## Disegno tecnico (sintesi)

- **Installabilità**: `@angular/service-worker` con `ngsw-config.json`; manifest con icone Ski Civetta; rotta dedicata `/it/pista` aperta all'avvio da telefono.
- **Dati di riferimento offline**: risposta unica `GET /api/v1/sync/bootstrap` (vocabolari attivi, comprensori, zone, piste, squadre dell'utente, chiave pubblica della società, impostazioni) salvata in IndexedDB con versione; aggiornamento incrementale con `updated_since`.
- **Coda offline**: IndexedDB con record `{client_uuid, payload cifrato, stato, tentativi, creato_il}`; invio con `POST /events` (idempotente su `client_uuid`) e poi `POST /events/{id}/persons`; ripetizione con attesa crescente; conflitti impossibili per costruzione (creazione sola; le modifiche si fanno dal portale).
- **Cifratura**: stesso modulo libsodium del portale; dati identificativi cifrati prima di entrare in coda; chiave personale sbloccata tenuta in memoria e, se l'utente lo sceglie, protetta nel dispositivo tramite WebAuthn PRF; in assenza, passphrase valida per il turno.
- **Posizione**: `navigator.geolocation` con alta precisione una sola volta alla creazione; mostrata la precisione in metri; correzione manuale sulla mappa (tessere in cache dell'ultima area vista).
- **Sessione**: token OIDC rinnovato dal service worker quando torna la rete; se la sessione è scaduta, la coda resta e si invia dopo il nuovo accesso.
- **Sicurezza**: CSP invariata; nessun dato identificativo in chiaro su disco; cancellazione della coda dopo l'invio; disattivazione utente dal portale che invalida il token entro il tempo di sessione; audit degli invii come per il portale (`source=mobile`).
- **Server**: endpoint bootstrap; verifica `updated_since` su vocabolari e territorio; limiti di richieste adeguati alle raffiche di sincronizzazione; campo `source` sugli eventi se non presente.

## Criteri di accettazione

1. Installazione dalla Home su iPhone e Android in meno di un minuto, senza store.
2. Creazione di un intervento con persona e dati identificativi in modalità aereo, invio automatico al ritorno della rete, evento visibile nel portale entro 1 minuto, nessun duplicato dopo 3 tentativi forzati.
3. Posizione GPS entro 20 m in campo aperto, correggibile sulla mappa.
4. Dati identificativi mai in chiaro su disco: verifica con ispezione dello storage del browser.
5. Vocabolari, zone e piste disponibili offline dopo il primo avvio in rete.
6. Tempo dal tocco dell'icona all'intervento salvato: sotto i 60 secondi con dati essenziali.
7. Guida rapida mobile consegnata e test automatici verdi.

## Rischi principali e contromisure

| Rischio | Contromisura |
|---|---|
| Safari cancella i dati delle app web inutilizzate per settimane | avvio dell'app almeno settimanale in stagione; coda svuotata subito al rientro in rete; avviso nell'app |
| WebAuthn PRF non disponibile sul telefono | ripiego automatico su passphrase per turno |
| GPS impreciso in gola o sotto gli impianti | precisione mostrata e correzione sulla mappa obbligatoria sotto i 50 m di accuratezza |
| Collaudo tardivo | consegna della versione candidata il 17/10, tre settimane di campo prima del rilascio |

## Prossimi passi immediati

- Consorzio: confermare le assunzioni entro il 19/09; indicare 2-3 soccorritori e i telefoni.
- Fornitore: ordine scritto per 12 giornate (M8.0-M8.2); avvio lunedì 22/09.
