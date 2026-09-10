import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService, Paginated } from './api.service';
import { AsyncJob } from './jobs.service';

export type AreaLevel = 'region' | 'province' | 'municipality';

export interface AdministrativeArea {
  level: AreaLevel;
  code: string;
  name: string;
  edition_year: number;
}

export interface RegionalRequest {
  template: 'veneto_a01';
  season: string;
  administrative_area: { level: AreaLevel; code: string } | null;
  team: string[] | null;
  format: 'xlsx' | 'xls';
  merge_duplicates: boolean;
  exclude_in_buildings: boolean;
}

export interface DuplicateGroup {
  kept_person_id: string;
  merged_person_ids: string[];
  teams: string[];
  event_ids: string[];
  dateandtime: string;
  joint: boolean;
}

export interface PreviewWarning {
  code: string;
  count?: number;
  slope_ids?: string[];
  event_ids?: string[];
}

/** Anteprima qualità dati prima della generazione dell'export regionale. */
export interface RegionalPreview {
  persons_total: number;
  excluded_in_buildings: { count: number; event_ids: string[] };
  excluded_outside_area: { count: number; event_ids: string[] };
  duplicate_groups: { count: number; persons_merged: number; groups: DuplicateGroup[] };
  exportable_persons: number;
  warnings: PreviewWarning[];
}

export interface DatasetRequest {
  dataset: 'events' | 'persons';
  format: 'csv' | 'xlsx';
  filters: Record<string, string | string[] | boolean>;
  lang?: string;
}

export interface ExportRun extends AsyncJob {
  export: {
    template: string;
    format: string;
    filters: Record<string, unknown>;
    row_count: number | null;
    administrative_area_code: string;
  } | null;
  requested_by: string | null;
}

@Injectable({ providedIn: 'root' })
export class ExportsService {
  private readonly api = inject(ApiService);

  administrativeAreas(): Observable<{ loaded: boolean; areas: AdministrativeArea[] }> {
    return this.api.get<{ loaded: boolean; areas: AdministrativeArea[] }>('exports/administrative-areas');
  }

  regionalPreview(req: RegionalRequest): Observable<RegionalPreview> {
    return this.api.post<RegionalPreview>('exports/regional/preview', req);
  }

  regional(req: RegionalRequest): Observable<AsyncJob> {
    return this.api.post<AsyncJob>('exports/regional', req);
  }

  dataset(req: DatasetRequest): Observable<AsyncJob> {
    return this.api.post<AsyncJob>('exports/dataset', req);
  }

  list(): Observable<Paginated<ExportRun>> {
    return this.api.get<Paginated<ExportRun>>('exports');
  }
}
