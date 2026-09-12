import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { RescueService } from '../api/rescue.service';
import { EventWrite, PersonWrite } from '../api/rescue.models';
import { errorMessage } from '../api/errors';
import { PwaService } from './pwa.service';

/** Intervento registrato in pista, in attesa di invio o già inviato (M8.1). I dati identificativi
 *  delle persone sono già cifrati (campo `pii`): su disco non resta nulla in chiaro. */
export interface QueuedIntervention {
  id: string; // client_uuid dell'evento
  created_at: string;
  event: EventWrite;
  persons: PersonWrite[];
  status: 'pending' | 'sending' | 'sent' | 'error';
  attempts: number;
  last_error: string | null;
  server_id: string | null;
  server_code: string | null;
  sent_at: string | null;
  /** posizione GPS: precisione in metri al momento dell'acquisizione (solo informativa) */
  gps_accuracy_m: number | null;
}

const DB_NAME = 'safe-pista';
const STORE = 'interventions';
const KEEP_SENT_DAYS = 7;
const RETRY_BASE_MS = 5000;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexeddb'));
  });
}

function tx<T>(db: IDBDatabase, mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const req = fn(t.objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexeddb'));
  });
}

/**
 * Coda locale degli interventi (IndexedDB) con invio automatico: creazione evento idempotente
 * (`client_uuid`) e poi persone, una alla volta; ripetizione con attesa crescente; nessun conflitto
 * possibile perché in pista si creano soltanto nuovi interventi (le modifiche si fanno dal portale).
 */
@Injectable({ providedIn: 'root' })
export class OfflineQueueService {
  private readonly rescue = inject(RescueService);
  private readonly pwa = inject(PwaService);
  private db: Promise<IDBDatabase> | null = null;
  private syncPromise: Promise<void> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  readonly items = signal<QueuedIntervention[]>([]);
  readonly pending = signal(0);
  readonly busy = signal(false);
  readonly supported = typeof indexedDB !== 'undefined';

  constructor() {
    if (!this.supported) return;
    void this.refresh().then(() => this.sync());
    window.addEventListener('online', () => void this.sync());
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) void this.sync();
    });
  }

  private async open(): Promise<IDBDatabase> {
    return (this.db ??= openDb());
  }

  async refresh(): Promise<QueuedIntervention[]> {
    const db = await this.open();
    const all = (await tx<QueuedIntervention[]>(db, 'readonly', (s) => s.getAll())) ?? [];
    // pulizia: gli inviati più vecchi di 7 giorni escono dall'elenco locale
    const cutoff = Date.now() - KEEP_SENT_DAYS * 86400000;
    for (const it of all) {
      if (it.status === 'sent' && it.sent_at && Date.parse(it.sent_at) < cutoff) {
        await tx(db, 'readwrite', (s) => s.delete(it.id));
      }
    }
    const kept = all
      .filter((it) => !(it.status === 'sent' && it.sent_at && Date.parse(it.sent_at) < cutoff))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    this.items.set(kept);
    this.pending.set(kept.filter((it) => it.status !== 'sent').length);
    return kept;
  }

  /** Salva un nuovo intervento in coda e prova subito a inviarlo. */
  async enqueue(event: EventWrite, persons: PersonWrite[], gpsAccuracy: number | null): Promise<QueuedIntervention> {
    const id = event.client_uuid ?? crypto.randomUUID();
    const item: QueuedIntervention = {
      id,
      created_at: new Date().toISOString(),
      event: { ...event, client_uuid: id },
      persons: persons.map((p) => ({ ...p, client_uuid: p.client_uuid ?? crypto.randomUUID() })),
      status: 'pending',
      attempts: 0,
      last_error: null,
      server_id: null,
      server_code: null,
      sent_at: null,
      gps_accuracy_m: gpsAccuracy,
    };
    await this.put(item);
    await this.refresh();
    void this.sync();
    return item;
  }

  async remove(id: string): Promise<void> {
    const db = await this.open();
    await tx(db, 'readwrite', (s) => s.delete(id));
    await this.refresh();
  }

  /** Rimette in coda un intervento in errore (dopo una correzione lato server, es. permessi). */
  async retry(id: string): Promise<void> {
    const it = (await this.refresh()).find((x) => x.id === id);
    if (!it) return;
    await this.put({ ...it, status: 'pending', last_error: null, attempts: 0 });
    await this.refresh();
    void this.sync();
  }

  /** Invia in ordine tutti gli interventi in attesa. Una sola esecuzione alla volta: le chiamate
   *  concorrenti attendono quella in corso. */
  sync(): Promise<void> {
    if (!this.supported || !this.pwa.online()) return Promise.resolve();
    return (this.syncPromise ??= this.runSync().finally(() => (this.syncPromise = null)));
  }

  private async runSync(): Promise<void> {
    this.busy.set(true);
    let failed = false;
    try {
      const queue = (await this.refresh()).filter((it) => it.status === 'pending' || it.status === 'error').reverse();
      for (const it of queue) {
        if (it.status === 'error' && it.attempts >= 5) continue; // richiede un "riprova" esplicito
        const ok = await this.send(it);
        if (!ok) failed = true;
      }
    } finally {
      this.busy.set(false);
      await this.refresh();
      if (failed && this.pwa.online()) this.scheduleRetry();
    }
  }

  /** Svuota la coda locale (uso nei test e nelle impostazioni). */
  async clearAll(): Promise<void> {
    const db = await this.open();
    await tx(db, 'readwrite', (s) => s.clear());
    await this.refresh();
  }

  /** Chiude la connessione al database locale (test). */
  async close(): Promise<void> {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.db) (await this.db).close();
    this.db = null;
  }

  private scheduleRetry(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    const attempts = Math.max(1, ...this.items().filter((it) => it.status === 'error').map((it) => it.attempts));
    const delay = Math.min(RETRY_BASE_MS * 2 ** (attempts - 1), 5 * 60 * 1000);
    this.retryTimer = setTimeout(() => void this.sync(), delay);
  }

  private async send(it: QueuedIntervention): Promise<boolean> {
    let cur: QueuedIntervention = { ...it, status: 'sending' };
    await this.put(cur);
    try {
      if (!cur.server_id) {
        const created = await firstValueFrom(this.rescue.createEvent(cur.event)); // 201, o 200 se già ricevuto
        cur = { ...cur, server_id: created.id, server_code: created.id.slice(-8).toUpperCase() }; // codice breve del portale
        await this.put(cur);
      }
      for (const p of cur.persons) {
        await firstValueFrom(this.rescue.addPerson(cur.server_id!, p)); // idempotente su client_uuid
      }
      await this.put({ ...cur, status: 'sent', sent_at: new Date().toISOString(), last_error: null });
      return true;
    } catch (err) {
      const offline = !this.pwa.online() || (err as { status?: number }).status === 0;
      await this.put({
        ...cur,
        status: offline ? 'pending' : 'error',
        attempts: offline ? cur.attempts : cur.attempts + 1,
        last_error: offline ? null : errorMessage(err, 'Invio non riuscito'),
      });
      return false;
    }
  }

  private async put(item: QueuedIntervention): Promise<void> {
    const db = await this.open();
    await tx(db, 'readwrite', (s) => s.put(item));
  }
}
