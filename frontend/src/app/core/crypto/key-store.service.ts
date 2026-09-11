import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { SessionService } from '../session/session.service';
import {
  ALGORITHMS, EncryptedPrivateKey, KeyPair, b64, decryptPii, decryptPrivateKey, encryptPii, encryptPrivateKey,
  generateKeyPair, generateRecoveryCode, publicKeyOf, seal, unseal,
} from './sodium';

export interface MyKey extends EncryptedPrivateKey {
  algorithm: string;
  public_key: string;
  created_at: string;
  rotated_at: string | null;
  grants: {
    company_key_id: string;
    key_version: number;
    key_status: 'active' | 'retired';
    company_public_key: string;
    wrapped_private_key: string;
  }[];
}

export interface CompanyKeyInfo {
  id: string;
  version: number;
  algorithm: string;
  public_key: string;
  status: 'active' | 'retired';
  created_at: string;
  created_by: string | null;
  retired_at: string | null;
}

export interface Identity {
  person_id: string;
  algorithm: string;
  ciphertext: string;
  key_wrapped: string;
  key_version: number;
  fields: string[];
  grant: { company_key_id: string; wrapped_private_key: string };
}

const AUTO_LOCK_MS = 15 * 60 * 1000;

/** Stato delle chiavi in memoria per la sessione: mai in storage. Si blocca dopo 15 minuti di
 *  inattività, al logout o manualmente (docs/05-schermate.md §5.2). */
@Injectable({ providedIn: 'root' })
export class KeyStoreService {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);

  private userKeyPair: KeyPair | null = null;
  /** chiavi private società aperte, per versione */
  private companyKeys = new Map<number, KeyPair>();
  private lockTimer: ReturnType<typeof setTimeout> | null = null;

  readonly unlocked = signal(false);
  readonly myKey = signal<MyKey | null | undefined>(undefined); // undefined = non ancora caricata
  readonly companyKey = signal<CompanyKeyInfo | null | undefined>(undefined);
  readonly busy = signal(false);

  readonly hasUserKey = computed(() => this.myKey() !== null && this.myKey() !== undefined);
  readonly hasGrant = computed(() => (this.myKey()?.grants ?? []).some((g) => g.key_status === 'active'));
  /** Può decifrare: sbloccata e con grant sulla chiave attiva. */
  readonly canDecrypt = computed(() => this.unlocked() && this.hasGrant());
  /** Può cifrare: basta la chiave pubblica della società. */
  readonly canEncrypt = computed(() => !!this.companyKey());

  constructor() {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) this.armAutoLock();
    });
    ['click', 'keydown'].forEach((ev) => document.addEventListener(ev, () => this.touch(), { passive: true }));
  }

  // --- caricamento ------------------------------------------------------------------------------

  async loadMyKey(): Promise<MyKey | null> {
    try {
      const k = await firstValueFrom(this.api.get<MyKey>('crypto/my-key'));
      this.myKey.set(k);
      return k;
    } catch {
      this.myKey.set(null);
      return null;
    }
  }

  async loadCompanyKey(): Promise<CompanyKeyInfo | null> {
    try {
      const k = await firstValueFrom(this.api.get<CompanyKeyInfo>('crypto/company-key'));
      this.companyKey.set(k);
      return k;
    } catch {
      this.companyKey.set(null);
      return null;
    }
  }

  async ensureLoaded(): Promise<void> {
    if (this.myKey() === undefined) await this.loadMyKey();
    if (this.companyKey() === undefined && this.session.can('persons.edit')) await this.loadCompanyKey();
  }

  // --- chiave personale ----------------------------------------------------------------------------

  /** Crea (o sostituisce) la coppia personale cifrata con la passphrase; resta sbloccata. */
  async createUserKey(passphrase: string): Promise<void> {
    this.busy.set(true);
    try {
      const kp = await generateKeyPair();
      const enc = await encryptPrivateKey(kp.privateKey, passphrase);
      await firstValueFrom(
        this.api.put('crypto/my-key', { algorithm: ALGORITHMS.userKey, public_key: b64.encode(kp.publicKey), ...enc }),
      );
      this.userKeyPair = kp;
      this.companyKeys.clear();
      this.unlocked.set(true);
      this.armAutoLock();
      await this.loadMyKey();
      await this.session.reload();
    } finally {
      this.busy.set(false);
    }
  }

  /** Sblocca con la passphrase: apre la privata personale e tutte le grant. Ritorna false se errata. */
  async unlock(passphrase: string): Promise<boolean> {
    const k = this.myKey() ?? (await this.loadMyKey());
    if (!k) return false;
    this.busy.set(true);
    try {
      const priv = await decryptPrivateKey(k, passphrase);
      if (!priv) return false;
      this.userKeyPair = { privateKey: priv, publicKey: b64.decode(k.public_key) };
      this.companyKeys.clear();
      for (const g of k.grants) {
        try {
          const cpriv = await unseal(b64.decode(g.wrapped_private_key), this.userKeyPair);
          this.companyKeys.set(g.key_version, { privateKey: cpriv, publicKey: b64.decode(g.company_public_key) });
        } catch {
          /* grant non apribile (chiave rigenerata): ignorata */
        }
      }
      this.unlocked.set(true);
      this.armAutoLock();
      return true;
    } finally {
      this.busy.set(false);
    }
  }

  /** Cambia passphrase: stessa coppia, nuovo blob cifrato (le grant restano valide). */
  async changePassphrase(passphrase: string): Promise<void> {
    if (!this.userKeyPair) throw new Error('locked');
    const enc = await encryptPrivateKey(this.userKeyPair.privateKey, passphrase);
    await firstValueFrom(
      this.api.put('crypto/my-key', { algorithm: ALGORITHMS.userKey, public_key: b64.encode(this.userKeyPair.publicKey), ...enc }),
    );
    await this.loadMyKey();
  }

  lock(): void {
    this.userKeyPair = null;
    this.companyKeys.clear();
    this.unlocked.set(false);
    if (this.lockTimer) clearTimeout(this.lockTimer);
  }

  private armAutoLock(): void {
    if (this.lockTimer) clearTimeout(this.lockTimer);
    if (this.unlocked()) this.lockTimer = setTimeout(() => this.lock(), AUTO_LOCK_MS);
  }

  private touch(): void {
    if (this.unlocked() && !document.hidden) this.armAutoLock();
  }

  // --- dati identificativi -----------------------------------------------------------------------

  async encryptIdentity(fields: Record<string, string>): Promise<{ ciphertext: string; key_wrapped: string; key_version: number; fields: string[] } | null> {
    const ck = this.companyKey() ?? (await this.loadCompanyKey());
    if (!ck) return null;
    const enc = await encryptPii(fields, b64.decode(ck.public_key));
    if (!enc.fields.length) return null;
    return { ...enc, key_version: ck.version };
  }

  /** Legge e decifra l'identità di una persona (l'accesso è registrato in audit dal server). */
  async readIdentity(personId: string): Promise<Record<string, string>> {
    if (!this.userKeyPair) throw new Error('locked');
    const ident = await firstValueFrom(this.api.get<Identity>(`persons/${personId}/identity`));
    let kp = this.companyKeys.get(ident.key_version);
    if (!kp) {
      const cpriv = await unseal(b64.decode(ident.grant.wrapped_private_key), this.userKeyPair);
      kp = { privateKey: cpriv, publicKey: await publicKeyOf(cpriv) };
      this.companyKeys.set(ident.key_version, kp);
    }
    return decryptPii(ident.ciphertext, ident.key_wrapped, kp);
  }

  // --- custodia: inizializzazione, grant, rotazione, recupero -----------------------------------

  private requireUserKey(): KeyPair {
    if (!this.userKeyPair) throw new Error('locked');
    return this.userKeyPair;
  }

  /** Genera la coppia società nel browser; ritorna le 24 parole (da mostrare una sola volta). */
  async initCompanyKey(): Promise<string[]> {
    const ukp = this.requireUserKey();
    const ckp = await generateKeyPair();
    const words = await generateRecoveryCode();
    const body = await this.companyKeyPayload(ckp, ukp, words.join(' '));
    const info = await firstValueFrom(this.api.post<CompanyKeyInfo>('crypto/company-key', body));
    this.companyKeys.set(info.version, ckp);
    this.companyKey.set(info);
    await this.loadMyKey();
    await this.session.reload();
    return words;
  }

  private async companyKeyPayload(ckp: KeyPair, ukp: KeyPair, recoveryCode: string) {
    return {
      public_key: b64.encode(ckp.publicKey),
      wrapped_private_key: b64.encode(await seal(ckp.privateKey, ukp.publicKey)),
      recovery: await encryptPrivateKey(ckp.privateKey, recoveryCode).then((e) => ({
        encrypted_private_key: e.private_key_encrypted,
        kdf_params: e.kdf_params,
      })),
    };
  }

  activeCompanyKeyPair(): KeyPair | null {
    const ck = this.companyKey();
    return ck ? (this.companyKeys.get(ck.version) ?? null) : null;
  }

  /** Concede la chiave società a un utente: la privata viene ri-sigillata con la sua pubblica. */
  async grant(userId: string): Promise<void> {
    this.requireUserKey();
    const ckp = this.activeCompanyKeyPair();
    if (!ckp) throw new Error('no_company_key');
    const pub = await firstValueFrom(this.api.get<{ public_key: string }>(`crypto/users/${userId}/public-key`));
    await firstValueFrom(
      this.api.post('crypto/grants', { user_id: userId, wrapped_private_key: b64.encode(await seal(ckp.privateKey, b64.decode(pub.public_key))) }),
    );
  }

  /** Rotazione: nuova coppia, poi ri-sigillo a lotti delle data key. `onProgress(done, total)`. */
  async rotate(onProgress: (done: number, total: number) => void): Promise<string[]> {
    const ukp = this.requireUserKey();
    const old = this.activeCompanyKeyPair();
    if (!old) throw new Error('no_company_key');
    const ckp = await generateKeyPair();
    const words = await generateRecoveryCode();
    const info = await firstValueFrom(
      this.api.post<CompanyKeyInfo & { persons_to_rewrap: number }>('crypto/company-key/rotate', await this.companyKeyPayload(ckp, ukp, words.join(' '))),
    );
    this.companyKeys.set(info.version, ckp);
    this.companyKey.set(info);
    const total = info.persons_to_rewrap;
    let done = 0;
    onProgress(0, total);
    for (;;) {
      const batch = await firstValueFrom(
        this.api.get<{ items: { person_id: string; key_wrapped: string; key_version: number }[]; remaining: number }>('crypto/company-key/rewrap?limit=200'),
      );
      if (!batch.items.length) break;
      const items = [];
      for (const it of batch.items) {
        const oldKp = this.companyKeys.get(it.key_version);
        if (!oldKp) continue;
        const dataKey = await unseal(b64.decode(it.key_wrapped), oldKp);
        items.push({ person_id: it.person_id, key_wrapped: b64.encode(await seal(dataKey, ckp.publicKey)) });
      }
      if (!items.length) break;
      const res = await firstValueFrom(this.api.post<{ updated: number; remaining: number }>('crypto/company-key/rewrap', { items }));
      done += res.updated;
      onProgress(done, total);
      if (res.remaining === 0 || res.updated === 0) break;
    }
    await this.loadMyKey();
    await this.session.reload();
    return words;
  }

  /** Recupero con le 24 parole: apre la privata società, crea la propria grant e un nuovo kit. */
  async recover(recoveryCode: string): Promise<string[]> {
    const ukp = this.requireUserKey();
    const rec = await firstValueFrom(
      this.api.get<{ key_version: number; company_public_key: string; encrypted_private_key: string; kdf_params: EncryptedPrivateKey['kdf_params'] }>('crypto/recovery'),
    );
    const priv = await decryptPrivateKey({ private_key_encrypted: rec.encrypted_private_key, kdf_params: rec.kdf_params }, recoveryCode);
    if (!priv) throw new Error('bad_recovery_code');
    const ckp: KeyPair = { privateKey: priv, publicKey: b64.decode(rec.company_public_key) };
    const words = await generateRecoveryCode();
    await firstValueFrom(this.api.post('crypto/recovery', await this.companyKeyPayload(ckp, ukp, words.join(' '))));
    this.companyKeys.set(rec.key_version, ckp);
    await this.loadCompanyKey();
    await this.loadMyKey();
    await this.session.reload();
    return words;
  }
}
