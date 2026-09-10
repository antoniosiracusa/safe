import { HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

/** Filtri globali: stessa forma della query string dell'API (docs/03-openapi.yaml, StatsFilters). */
export interface GlobalFilters {
  team: string[];
  season: string | null;
  date_from: string | null;
  date_to: string | null;
  ski_area: string | null;
  zone: string | null;
  valid_only: boolean;
}

export const FILTER_KEYS: (keyof GlobalFilters)[] = [
  'team',
  'season',
  'date_from',
  'date_to',
  'ski_area',
  'zone',
  'valid_only',
];

/** Stagione sciistica: 1 giugno → 31 maggio. */
export function seasonCodeFor(day: Date): string {
  const start = day.getMonth() + 1 >= 6 ? day.getFullYear() : day.getFullYear() - 1;
  return `${start}/${start + 1}`;
}

export function defaultFilters(today = new Date()): GlobalFilters {
  return {
    team: [],
    season: seasonCodeFor(today),
    date_from: null,
    date_to: null,
    ski_area: null,
    zone: null,
    valid_only: false,
  };
}

export function parseFilters(params: Record<string, string | string[] | undefined>, today = new Date()): GlobalFilters {
  const one = (k: string): string | null => {
    const v = params[k];
    if (Array.isArray(v)) return v[0] ?? null;
    return v ?? null;
  };
  const teams = params['team'];
  const teamList = Array.isArray(teams) ? teams : teams ? [teams] : [];
  const hasPeriod = one('season') || one('date_from') || one('date_to');
  return {
    team: teamList.filter(Boolean),
    season: hasPeriod ? one('season') : defaultFilters(today).season,
    date_from: one('date_from'),
    date_to: one('date_to'),
    ski_area: one('ski_area'),
    zone: one('zone'),
    valid_only: one('valid_only') === 'true',
  };
}

export function serializeFilters(f: GlobalFilters): Record<string, string | string[] | null> {
  return {
    team: f.team.length ? f.team : null,
    season: f.season,
    date_from: f.date_from,
    date_to: f.date_to,
    ski_area: f.ski_area,
    zone: f.zone,
    valid_only: f.valid_only ? 'true' : null,
  };
}

export function toHttpParams(f: GlobalFilters): HttpParams {
  let p = new HttpParams();
  for (const t of f.team) p = p.append('team', t);
  if (f.season) p = p.set('season', f.season);
  if (f.date_from) p = p.set('date_from', f.date_from);
  if (f.date_to) p = p.set('date_to', f.date_to);
  if (f.ski_area) p = p.set('ski_area', f.ski_area);
  if (f.zone) p = p.set('zone', f.zone);
  if (f.valid_only) p = p.set('valid_only', 'true');
  return p;
}

/**
 * Stato dei filtri globali, persistente tra le pagine e riflesso nella URL (condivisibile).
 * Fonte di verità: la query string. Le pagine leggono `filters()`; le chiamate API usano `httpParams()`.
 */
@Injectable({ providedIn: 'root' })
export class FilterStore {
  private readonly router = inject(Router);
  private readonly state = signal<GlobalFilters>(defaultFilters());

  readonly filters = this.state.asReadonly();
  readonly httpParams = computed(() => toHttpParams(this.state()));
  readonly queryParams = computed(() => serializeFilters(this.state()));
  readonly activeCount = computed(() => {
    const f = this.state();
    return (
      (f.team.length ? 1 : 0) +
      (f.date_from || f.date_to ? 1 : 0) +
      (f.ski_area ? 1 : 0) +
      (f.zone ? 1 : 0) +
      (f.valid_only ? 1 : 0)
    );
  });

  constructor() {
    this.syncFromUrl();
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => this.syncFromUrl());
  }

  private syncFromUrl(): void {
    const params = this.router.parseUrl(this.router.url).queryParams as Record<string, string | string[]>;
    const next = parseFilters(params);
    if (JSON.stringify(next) !== JSON.stringify(this.state())) this.state.set(next);
  }

  apply(patch: Partial<GlobalFilters>): void {
    const next: GlobalFilters = { ...this.state(), ...patch };
    // periodo: stagione e intervallo date sono alternativi
    if (patch.date_from !== undefined || patch.date_to !== undefined) {
      if (next.date_from || next.date_to) next.season = null;
    }
    if (patch.season) {
      next.date_from = null;
      next.date_to = null;
    }
    // la zona deve appartenere al comprensorio selezionato: chi la conosce (la barra) la azzera
    void this.router.navigate([], { queryParams: serializeFilters(next), queryParamsHandling: 'merge' });
  }

  reset(): void {
    const cleared = Object.fromEntries(FILTER_KEYS.map((k) => [k, null]));
    void this.router.navigate([], { queryParams: cleared, queryParamsHandling: 'merge' });
  }
}
