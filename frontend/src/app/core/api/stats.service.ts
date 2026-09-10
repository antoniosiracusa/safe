import { HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService, ChartPayload } from './api.service';

export interface ChartMeta {
  unit?: 'events' | 'persons' | 'means';
  total?: number;
  codes?: string[];
  total_labels?: number;
  cached?: boolean;
  [k: string]: unknown;
}

export type ChartData = ChartPayload & { meta?: ChartMeta; datasets: (ChartPayload['datasets'][number] & { code?: string })[] };

export interface ZoneTable {
  columns: string[];
  rows: { zone: { id: string | null; name: string }; cells: { events: number; persons: number }[]; total: { events: number; persons: number } }[];
  totals: { events: number; persons: number }[];
}

export interface SeasonSummary {
  season: string;
  last_week: { from: string; to: string } | null;
  rows: {
    team: { id: string; name: string };
    season_events: number;
    last_week_events: number;
    unlocked_events: number;
    invalid_events: number;
    helicopter_rescues: number;
  }[];
  totals: Record<string, number>;
}

export interface GeneralKpi {
  total_events: number;
  total_persons: number;
  total_seasons: number;
  current_season: string;
  current_season_events: number;
  invalid_events: number;
}

/** Rotte /stats: i dati arrivano già aggregati e tradotti; il client fa solo rendering. */
@Injectable({ providedIn: 'root' })
export class StatsService {
  private readonly api = inject(ApiService);

  chart(path: string, params: HttpParams): Observable<ChartData> {
    return this.api.get<ChartData>(`stats/${path}`, params);
  }

  zoneTable(params: HttpParams): Observable<ZoneTable> {
    return this.api.get<ZoneTable>('stats/zone-summary/table', params);
  }

  seasonSummary(params: HttpParams): Observable<SeasonSummary> {
    return this.api.get<SeasonSummary>('stats/season-summary/teams', params);
  }

  general(params: HttpParams): Observable<GeneralKpi> {
    return this.api.get<GeneralKpi>('stats/general', params);
  }
}
