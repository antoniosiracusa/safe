/**
 * Primitive crittografiche (libsodium) usate dal browser — docs/01-architettura.md §7.
 *
 * - coppie X25519 (utente e società); sealed box per "avvolgere" chiavi verso una pubblica;
 * - Argon2id per derivare da passphrase/codice di recupero la chiave che cifra la privata (secretbox);
 * - XChaCha20-Poly1305 con data key casuale per i dati identificativi della persona.
 *
 * Il server riceve soltanto chiavi pubbliche, blob cifrati e data key sigillate.
 * libsodium (~1 MB) è caricato solo alla prima operazione crittografica, come script separato
 * (`public/vendor/sodium.js`, generato da `npm run vendor:sodium`): la build ESM del pacchetto usa
 * top-level await e quella CommonJS non è servibile dal dev server.
 */
import { BIP39_WORDS } from './bip39-words';

type Sodium = typeof import('libsodium-wrappers-sumo');

export const ALGORITHMS = {
  userKey: 'x25519-v1',
  companyKey: 'x25519-sealedbox-v1',
  pii: 'xchacha20poly1305-x25519sealedbox-v1',
} as const;

export interface KdfParams {
  alg: 'argon2id';
  salt: string; // base64
  ops: number;
  mem: number; // byte
  v: 1;
}

export interface EncryptedPrivateKey {
  private_key_encrypted: string; // base64: nonce || secretbox
  kdf_params: KdfParams;
}

let ready: Promise<Sodium> | null = null;

/** Errori "di ambiente" distinti da una passphrase sbagliata (chiavi i18n `keys.<codice>`). */
export const CRYPTO_ERROR_CODES = ['wasm_blocked', 'crypto_selftest_failed'] as const;
export type CryptoErrorCode = (typeof CRYPTO_ERROR_CODES)[number];

export function cryptoErrorCode(err: unknown): CryptoErrorCode | null {
  const msg = err instanceof Error ? err.message : '';
  return (CRYPTO_ERROR_CODES as readonly string[]).includes(msg) ? (msg as CryptoErrorCode) : null;
}

/** WebAssembly deve poter essere compilato (CSP `script-src` con 'wasm-unsafe-eval'): senza, libsodium
 *  ripiega su asm.js e, dopo la crescita di memoria di Argon2, restituisce buffer stantii → blob corrotti. */
function wasmAllowed(): boolean {
  try {
    new WebAssembly.Module(new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]));
    return true;
  } catch {
    return false;
  }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      reject(new Error('sodium_load_failed'));
    };
    document.head.appendChild(script);
  });
}

/** Carica `vendor/sodium.js` (bundle IIFE generato da `npm run vendor:sodium`) alla prima chiamata.
 *  Se il primo caricamento fallisce (rete instabile, copia del service worker non valida) riprova una
 *  volta con un URL che aggira le cache; un esito negativo non resta "memorizzato": la chiamata
 *  successiva ritenta da capo. */
export function sodiumReady(): Promise<Sodium> {
  if (ready) return ready;
  const w = window as unknown as { sodium?: Sodium };
  const attempt = (async () => {
    if (!w.sodium) {
      try {
        await loadScript('vendor/sodium.js');
      } catch {
        console.warn('sodium: primo caricamento fallito, riprovo aggirando le cache');
        await loadScript(`vendor/sodium.js?retry=${Date.now()}`);
      }
    }
    const s = w.sodium;
    if (!s) throw new Error('sodium_missing');
    if (!wasmAllowed()) throw new Error('wasm_blocked');
    await s.ready;
    return s;
  })();
  ready = attempt.catch((err: unknown) => {
    ready = null; // il prossimo tentativo ricarica lo script
    throw err;
  });
  return ready;
}

/** Base64 standard senza dipendere da libsodium (usato anche prima del caricamento). */
export const b64 = {
  encode: (data: Uint8Array): string => btoa(String.fromCharCode(...data)),
  decode: (text: string): Uint8Array => Uint8Array.from(atob(text), (c) => c.charCodeAt(0)),
};

export interface KeyPair {
  publicKey: Uint8Array;
  privateKey: Uint8Array;
}

export async function generateKeyPair(): Promise<KeyPair> {
  const s = await sodiumReady();
  const kp = s.crypto_box_keypair();
  return { publicKey: kp.publicKey, privateKey: kp.privateKey };
}

/** Argon2id interattivo (64 MiB, 2 passaggi): ~1 s su un portatile, adeguato a una passphrase di sessione. */
async function deriveKey(secret: string, params: KdfParams): Promise<Uint8Array> {
  const s = await sodiumReady();
  return s.crypto_pwhash(
    s.crypto_secretbox_KEYBYTES,
    secret.normalize('NFKC'),
    b64.decode(params.salt),
    params.ops,
    params.mem,
    s.crypto_pwhash_ALG_ARGON2ID13,
  );
}

export async function newKdfParams(): Promise<KdfParams> {
  const s = await sodiumReady();
  return {
    alg: 'argon2id',
    salt: b64.encode(s.randombytes_buf(s.crypto_pwhash_SALTBYTES)),
    ops: s.crypto_pwhash_OPSLIMIT_INTERACTIVE,
    mem: s.crypto_pwhash_MEMLIMIT_INTERACTIVE,
    v: 1,
  };
}

/** Cifra una chiave privata con un segreto (passphrase o codice di recupero). */
export async function encryptPrivateKey(privateKey: Uint8Array, secret: string): Promise<EncryptedPrivateKey> {
  const s = await sodiumReady();
  const params = await newKdfParams();
  const key = await deriveKey(secret, params);
  const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
  const box = s.crypto_secretbox_easy(privateKey, nonce, key);
  assertRoundTrip(s, () => s.crypto_secretbox_open_easy(box, nonce, key), privateKey);
  const out = new Uint8Array(nonce.length + box.length);
  out.set(nonce);
  out.set(box, nonce.length);
  return { private_key_encrypted: b64.encode(out), kdf_params: params };
}

/** Un blob che non si riapre nello stesso browser non deve mai arrivare al server. */
function assertRoundTrip(s: Sodium, open: () => Uint8Array, expected: Uint8Array): void {
  let back: Uint8Array | null = null;
  try {
    back = open();
  } catch {
    back = null;
  }
  if (!back || back.length !== expected.length || !s.memcmp(back, expected)) {
    throw new Error('crypto_selftest_failed');
  }
}

/** Restituisce null se il segreto è sbagliato. */
export async function decryptPrivateKey(blob: EncryptedPrivateKey, secret: string): Promise<Uint8Array | null> {
  const s = await sodiumReady();
  try {
    const key = await deriveKey(secret, blob.kdf_params);
    const data = b64.decode(blob.private_key_encrypted);
    const nonce = data.slice(0, s.crypto_secretbox_NONCEBYTES);
    const box = data.slice(s.crypto_secretbox_NONCEBYTES);
    return s.crypto_secretbox_open_easy(box, nonce, key);
  } catch {
    return null;
  }
}

/** secretbox con chiave grezza (32 byte): nonce || box. Usato da "ricorda per il turno" (M8.2). */
export async function sealWithKey(data: Uint8Array, key: Uint8Array): Promise<Uint8Array> {
  const s = await sodiumReady();
  const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
  const box = s.crypto_secretbox_easy(data, nonce, key);
  assertRoundTrip(s, () => s.crypto_secretbox_open_easy(box, nonce, key), data);
  const out = new Uint8Array(nonce.length + box.length);
  out.set(nonce);
  out.set(box, nonce.length);
  return out;
}

export async function openWithKey(blob: Uint8Array, key: Uint8Array): Promise<Uint8Array | null> {
  const s = await sodiumReady();
  try {
    return s.crypto_secretbox_open_easy(blob.slice(s.crypto_secretbox_NONCEBYTES), blob.slice(0, s.crypto_secretbox_NONCEBYTES), key);
  } catch {
    return null;
  }
}

export async function seal(data: Uint8Array, recipientPublicKey: Uint8Array): Promise<Uint8Array> {
  const s = await sodiumReady();
  return s.crypto_box_seal(data, recipientPublicKey);
}

export async function unseal(sealed: Uint8Array, kp: KeyPair): Promise<Uint8Array> {
  const s = await sodiumReady();
  return s.crypto_box_seal_open(sealed, kp.publicKey, kp.privateKey);
}

export async function publicKeyOf(privateKey: Uint8Array): Promise<Uint8Array> {
  const s = await sodiumReady();
  return s.crypto_scalarmult_base(privateKey);
}

/** Dati identificativi → {ciphertext, key_wrapped}: data key casuale, AEAD, data key sigillata per la società. */
export async function encryptPii(
  fields: Record<string, string>,
  companyPublicKey: Uint8Array,
): Promise<{ ciphertext: string; key_wrapped: string; fields: string[] }> {
  const s = await sodiumReady();
  const clean = Object.fromEntries(Object.entries(fields).filter(([, v]) => v && v.trim()));
  const dataKey = s.crypto_aead_xchacha20poly1305_ietf_keygen();
  const nonce = s.randombytes_buf(s.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES);
  const plain = s.from_string(JSON.stringify(clean));
  const box = s.crypto_aead_xchacha20poly1305_ietf_encrypt(plain, null, null, nonce, dataKey);
  assertRoundTrip(s, () => s.crypto_aead_xchacha20poly1305_ietf_decrypt(null, box, null, nonce, dataKey), plain);
  const out = new Uint8Array(nonce.length + box.length);
  out.set(nonce);
  out.set(box, nonce.length);
  return {
    ciphertext: b64.encode(out),
    key_wrapped: b64.encode(await seal(dataKey, companyPublicKey)),
    fields: Object.keys(clean),
  };
}

export async function decryptPii(
  ciphertext: string,
  keyWrapped: string,
  companyKeyPair: KeyPair,
): Promise<Record<string, string>> {
  const s = await sodiumReady();
  const dataKey = await unseal(b64.decode(keyWrapped), companyKeyPair);
  const data = b64.decode(ciphertext);
  const nonce = data.slice(0, s.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES);
  const box = data.slice(s.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES);
  const plain = s.crypto_aead_xchacha20poly1305_ietf_decrypt(null, box, null, nonce, dataKey);
  return JSON.parse(s.to_string(plain)) as Record<string, string>;
}

/** Codice di recupero: 24 parole BIP-39 (256 bit di entropia + checksum), mostrato una sola volta. */
export async function generateRecoveryCode(): Promise<string[]> {
  const s = await sodiumReady();
  const entropy = s.randombytes_buf(32);
  const hash = s.crypto_hash_sha256(entropy);
  const bits = [...entropy].map((x) => x.toString(2).padStart(8, '0')).join('') + hash[0].toString(2).padStart(8, '0');
  const words: string[] = [];
  for (let i = 0; i < 24; i++) words.push(BIP39_WORDS[parseInt(bits.slice(i * 11, i * 11 + 11), 2)]);
  return words;
}

/** Normalizza il codice digitato (spazi multipli, maiuscole) e verifica che le parole esistano. */
export function normalizeRecoveryCode(input: string): string | null {
  const words = input.toLowerCase().trim().split(/[\s,;]+/).filter(Boolean);
  if (words.length !== 24 || words.some((w) => !BIP39_WORDS.includes(w))) return null;
  return words.join(' ');
}
