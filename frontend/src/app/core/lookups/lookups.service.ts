import { Injectable, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface LookupItem {
  id: string;
  code: string;
  labels: Record<string, string>;
  sort_order: number;
  is_custom: boolean;
  parent: string | null;
  color: string | null;
}
export interface CountryItem {
  code: string;
  labels: Record<string, string>;
  is_eu: boolean;
}
export interface LookupOption {
  value: string;
  label: string;
  parent?: string | null;
}

export const UNCLASSIFIED = 'unclassified';

/** Vocabolari controllati della società (GET /lookups), etichette nella lingua attiva.
 *  "Non classificato" è sempre disponibile come etichetta di fallback per i valori null. */
@Injectable({ providedIn: 'root' })
export class LookupsService {
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private loading: Promise<void> | null = null;

  private readonly data = signal<Record<string, LookupItem[]>>({});
  private readonly countries = signal<CountryItem[]>([]);
  readonly loaded = signal(false);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });

  /** Mappa dimension → code → etichetta nella lingua attiva. */
  readonly labels = computed(() => {
    const lang = this.lang();
    const out: Record<string, Record<string, string>> = {};
    for (const [dim, items] of Object.entries(this.data())) {
      out[dim] = Object.fromEntries(items.map((i) => [i.code, i.labels[lang] ?? i.labels['it'] ?? i.code]));
    }
    out['country'] = Object.fromEntries(this.countries().map((c) => [c.code, c.labels[lang] ?? c.labels['it'] ?? c.code]));
    return out;
  });

  load(): Promise<void> {
    if (this.loaded()) return Promise.resolve();
    if (!this.loading) {
      this.loading = firstValueFrom(this.api.get<Record<string, unknown>>('lookups'))
        .then((res) => {
          const { country, ...dims } = res as { country: CountryItem[] } & Record<string, LookupItem[]>;
          this.data.set(dims as Record<string, LookupItem[]>);
          this.countries.set(country ?? []);
          this.loaded.set(true);
        })
        .finally(() => (this.loading = null));
    }
    return this.loading;
  }

  items(dimension: string): LookupItem[] {
    return this.data()[dimension] ?? [];
  }

  options(dimension: string): LookupOption[] {
    const lang = this.lang();
    return this.items(dimension).map((i) => ({ value: i.code, label: i.labels[lang] ?? i.labels['it'], parent: i.parent }));
  }

  countryOptions(): LookupOption[] {
    const lang = this.lang();
    return this.countries().map((c) => ({ value: c.code, label: c.labels[lang] ?? c.labels['it'] }));
  }

  label(dimension: string, code: string | null | undefined): string {
    if (!code) return this.transloco.translate('common.unclassified');
    return this.labels()[dimension]?.[code] ?? code;
  }
}
