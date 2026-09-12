import { Injectable, signal } from '@angular/core';

import { KeyPair, b64, openWithKey, sealWithKey } from './sodium';

/**
 * "Ricorda per il turno" (M8.2): la chiave privata personale viene cifrata con un segreto che solo
 * l'autenticatore del telefono può ricalcolare (WebAuthn, estensione PRF: Face ID / Touch ID /
 * impronta) e conservata nel dispositivo per al massimo 8 ore. Nessun server è coinvolto: la
 * credenziale WebAuthn serve unicamente a derivare il segreto locale dopo la verifica biometrica.
 * Se il telefono non supporta PRF, la funzione non è disponibile e resta la passphrase.
 */
interface StoredUnlock {
  user_id: string;
  cred_id: string; // base64
  salt: string; // base64, input della PRF
  blob: string; // base64: nonce || secretbox(privateKey, prf)
  public_key: string; // base64
  expires_at: number;
}

const DB_NAME = 'safe-device';
const STORE = 'unlock';
const SHIFT_MS = 8 * 60 * 60 * 1000;

interface PrfExtension {
  prf?: { eval?: { first: BufferSource } };
}
interface PrfResults {
  prf?: { enabled?: boolean; results?: { first?: ArrayBuffer } };
}

/** Copia in un ArrayBuffer "puro" (le API WebAuthn rifiutano viste su SharedArrayBuffer nei tipi). */
function toBuffer(u8: Uint8Array): ArrayBuffer {
  return u8.slice().buffer as ArrayBuffer;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'user_id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexeddb'));
  });
}

function tx<T>(db: IDBDatabase, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexeddb'));
  });
}

@Injectable({ providedIn: 'root' })
export class DeviceUnlockService {
  readonly supportedNow = typeof PublicKeyCredential !== 'undefined' && typeof indexedDB !== 'undefined';
  /** Il dispositivo può usare un autenticatore biometrico: si parte da "sì" se WebAuthn esiste e si
   *  passa a "no" solo se il browser lo esclude esplicitamente (alcuni browser non rispondono). */
  readonly supported = signal(this.supportedNow);
  /** Esiste una chiave ricordata, non scaduta, per l'utente corrente. */
  readonly available = signal(false);
  /** Esito dell'ultimo tentativo di registrazione, per la diagnostica nella finestra della chiave. */
  readonly lastError = signal<string | null>(null);

  constructor() {
    if (this.supportedNow) {
      PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
        .then((ok) => {
          if (!ok) this.supported.set(false);
        })
        .catch(() => undefined);
    }
  }

  async refresh(userId: string): Promise<void> {
    const item = await this.read(userId);
    this.available.set(!!item && item.expires_at > Date.now());
  }

  /** Registra la credenziale biometrica (se manca) e conserva la privata cifrata per 8 ore. */
  async remember(userId: string, userName: string, kp: KeyPair): Promise<boolean> {
    if (!this.supportedNow) return false;
    try {
      let item = await this.read(userId);
      let credId = item?.cred_id;
      if (!credId) {
        const cred = (await navigator.credentials.create({
          publicKey: {
            challenge: crypto.getRandomValues(new Uint8Array(32)),
            rp: { name: 'SAFECIVETTA.IT', id: location.hostname },
            user: { id: new TextEncoder().encode(userId), name: userName, displayName: userName },
            pubKeyCredParams: [{ type: 'public-key', alg: -7 }, { type: 'public-key', alg: -257 }],
            authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required', residentKey: 'required' },
            timeout: 60000,
            extensions: { prf: {} } as AuthenticationExtensionsClientInputs & PrfExtension,
          },
        })) as PublicKeyCredential | null;
        if (!cred) {
          this.lastError.set('nessuna credenziale');
          return false;
        }
        const ext = cred.getClientExtensionResults() as PrfResults;
        if (!ext.prf?.enabled) {
          this.lastError.set('PRF non supportata'); // autenticatore senza PRF: niente "ricorda"
          return false;
        }
        credId = b64.encode(new Uint8Array(cred.rawId));
      }
      const salt = crypto.getRandomValues(new Uint8Array(32));
      const secret = await this.deriveSecret(credId, salt);
      if (!secret) {
        this.lastError.set('PRF senza risultato');
        return false;
      }
      this.lastError.set(null);
      const blob = await sealWithKey(kp.privateKey, secret);
      item = {
        user_id: userId,
        cred_id: credId,
        salt: b64.encode(salt),
        blob: b64.encode(blob),
        public_key: b64.encode(kp.publicKey),
        expires_at: Date.now() + SHIFT_MS,
      };
      await this.write(item);
      this.available.set(true);
      return true;
    } catch (err) {
      console.warn('device unlock: registrazione non riuscita', err);
      this.lastError.set(err instanceof Error ? `${err.name}: ${err.message}` : String(err));
      return false;
    }
  }

  /** Verifica biometrica e riapertura della privata. null se non disponibile, annullata o scaduta. */
  async unlock(userId: string): Promise<KeyPair | null> {
    const item = await this.read(userId);
    if (!item) return null;
    if (item.expires_at <= Date.now()) {
      await this.forget(userId);
      return null;
    }
    try {
      const secret = await this.deriveSecret(item.cred_id, b64.decode(item.salt));
      if (!secret) return null;
      const priv = await openWithKey(b64.decode(item.blob), secret);
      if (!priv) return null;
      return { privateKey: priv, publicKey: b64.decode(item.public_key) };
    } catch (err) {
      console.warn('device unlock: sblocco non riuscito', err);
      return null;
    }
  }

  async forget(userId: string): Promise<void> {
    if (!this.supportedNow) return;
    const db = await openDb();
    await tx(db, 'readwrite', (s) => s.delete(userId));
    db.close();
    this.available.set(false);
  }

  private async deriveSecret(credId: string, salt: Uint8Array): Promise<Uint8Array | null> {
    const assertion = (await navigator.credentials.get({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rpId: location.hostname,
        allowCredentials: [{ type: 'public-key', id: toBuffer(b64.decode(credId)) }],
        userVerification: 'required',
        timeout: 60000,
        extensions: { prf: { eval: { first: toBuffer(salt) } } } as AuthenticationExtensionsClientInputs & PrfExtension,
      },
    })) as PublicKeyCredential | null;
    const first = (assertion?.getClientExtensionResults() as PrfResults | undefined)?.prf?.results?.first;
    return first ? new Uint8Array(first) : null;
  }

  private async read(userId: string): Promise<StoredUnlock | null> {
    if (!this.supportedNow) return null;
    const db = await openDb();
    const item = (await tx<StoredUnlock | undefined>(db, 'readonly', (s) => s.get(userId))) ?? null;
    db.close();
    return item;
  }

  private async write(item: StoredUnlock): Promise<void> {
    const db = await openDb();
    await tx(db, 'readwrite', (s) => s.put(item));
    db.close();
  }
}
