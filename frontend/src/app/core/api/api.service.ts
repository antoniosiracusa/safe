import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AppConfigService } from '../config/app-config';

/** Risposta paginata standard {count, next, previous, results}. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Payload dei grafici, già aggregato lato server. */
export interface ChartPayload {
  labels: string[];
  datasets: { label: string; data: number[]; backgroundColor: string | string[] }[];
  meta?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(AppConfigService);

  url(path: string): string {
    return `${this.config.config.apiBaseUrl}/${path.replace(/^\//, '')}`;
  }

  get<T>(path: string, params?: HttpParams | Record<string, string | string[]>): Observable<T> {
    return this.http.get<T>(this.url(path), { params });
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(this.url(path), body);
  }

  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(this.url(path), body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.url(path));
  }
}
