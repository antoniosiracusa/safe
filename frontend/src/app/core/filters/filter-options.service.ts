import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface FilterOption {
  value: string;
  label: string;
}
export interface SeasonOption extends FilterOption {
  start_date: string;
  end_date: string;
  is_current: boolean;
}
export interface ZoneOption extends FilterOption {
  ski_area: string;
}
export interface FilterOptions {
  teams: FilterOption[];
  seasons: SeasonOption[];
  ski_areas: FilterOption[];
  zones: ZoneOption[];
}

const EMPTY: FilterOptions = { teams: [], seasons: [], ski_areas: [], zones: [] };

/** Opzioni della barra filtri, una sola chiamata per sessione (GET /filters/options). */
@Injectable({ providedIn: 'root' })
export class FilterOptionsService {
  private readonly api = inject(ApiService);
  private loading: Promise<FilterOptions> | null = null;

  readonly options = signal<FilterOptions>(EMPTY);
  readonly loaded = signal(false);
  readonly error = signal(false);

  load(): Promise<FilterOptions> {
    if (this.loaded()) return Promise.resolve(this.options());
    if (!this.loading) {
      this.loading = firstValueFrom(this.api.get<FilterOptions>('filters/options'))
        .then((o) => {
          this.options.set(o);
          this.loaded.set(true);
          this.error.set(false);
          return o;
        })
        .catch((e: unknown) => {
          this.error.set(true);
          throw e;
        })
        .finally(() => (this.loading = null));
    }
    return this.loading;
  }

  invalidate(): void {
    this.loaded.set(false);
  }
}
