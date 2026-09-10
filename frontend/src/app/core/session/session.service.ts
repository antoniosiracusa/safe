import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface MeResponse {
  user: {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    locale: string;
    mfa_required: boolean;
  };
  company: { id: string; name: string; slug: string; tenant_type: string; timezone: string };
  teams: { id: string; name: string; is_default: boolean }[];
  permissions: Record<string, boolean>;
  key_status: { user_key: 'missing' | 'present'; company_key_version: number | null; grant: 'none' | 'active' };
}

/** Sessione applicativa: utente, società, squadre e mappa permessi risolti dal server (/me). */
@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly api = inject(ApiService);
  private loading: Promise<MeResponse> | null = null;

  readonly me = signal<MeResponse | null>(null);
  readonly user = computed(() => this.me()?.user ?? null);
  readonly company = computed(() => this.me()?.company ?? null);
  readonly teams = computed(() => this.me()?.teams ?? []);
  readonly permissions = computed(() => this.me()?.permissions ?? {});
  readonly keyStatus = computed(() => this.me()?.key_status ?? null);
  readonly displayName = computed(() => {
    const u = this.user();
    if (!u) return '';
    return `${u.first_name} ${u.last_name}`.trim() || u.email;
  });

  /** Vero se l'utente ha TUTTI i permessi indicati. La verifica reale resta lato server. */
  can(...codes: string[]): boolean {
    const perms = this.permissions();
    return codes.every((c) => perms[c] === true);
  }

  ensureLoaded(): Promise<MeResponse> {
    if (this.me()) return Promise.resolve(this.me() as MeResponse);
    if (!this.loading) {
      this.loading = firstValueFrom(this.api.get<MeResponse>('me'))
        .then((me) => {
          this.me.set(me);
          return me;
        })
        .finally(() => (this.loading = null));
    }
    return this.loading;
  }

  async reload(): Promise<MeResponse> {
    this.me.set(null);
    return this.ensureLoaded();
  }

  async setLocale(locale: string): Promise<void> {
    const me = await firstValueFrom(this.api.patch<MeResponse>('me', { locale }));
    this.me.set(me);
  }
}
