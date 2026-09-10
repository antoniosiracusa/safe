import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/** Job asincrono (GET /jobs/{id}); i risultati si scaricano da /jobs/{id}/download. */
export interface AsyncJob {
  id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  expires_at: string | null;
  download_url: string | null;
  result_filename: string | null;
  result_mime: string | null;
  error_code: string | null;
  result: Record<string, unknown> | null;
}

export function filenameFrom(disposition: string | null): string | null {
  const m = /filename="?([^";]+)"?/.exec(disposition ?? '');
  return m ? m[1] : null;
}

@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  get(id: string): Observable<AsyncJob> {
    return this.api.get<AsyncJob>(`jobs/${id}`);
  }

  /** Attende il completamento con polling (1 s → 3 s), al massimo `timeoutMs`. */
  async waitFor(job: AsyncJob, timeoutMs = 180_000): Promise<AsyncJob> {
    const start = Date.now();
    let delay = 1000;
    let current = job;
    while (current.status === 'queued' || current.status === 'running') {
      if (Date.now() - start > timeoutMs) throw new Error('job_timeout');
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 1.5, 3000);
      current = await firstValueFrom(this.get(current.id));
    }
    if (current.status !== 'done') throw new Error(current.error_code || 'job_failed');
    return current;
  }

  download(job: AsyncJob): Promise<Blob> {
    return firstValueFrom(this.http.get(this.api.url(`jobs/${job.id}/download`), { responseType: 'blob' }));
  }

  /** Salva un Blob come file nel browser (nessun dato passa per la URL). */
  saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  /** Attende il job e salva il risultato. */
  async waitAndSave(job: AsyncJob): Promise<AsyncJob> {
    const done = await this.waitFor(job);
    this.saveBlob(await this.download(done), done.result_filename ?? `${done.kind}.bin`);
    return done;
  }

  /** PDF del rapporto evento: 200 → file immediato, 202 → job da attendere e poi scaricare. */
  async eventReportPdf(eventId: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.get(this.api.url(`events/${eventId}/report.pdf`), { observe: 'response', responseType: 'blob' }),
    );
    const fallback = `report-${eventId.slice(-8).toUpperCase()}.pdf`;
    if (res.status === 202 && res.body) {
      const job = JSON.parse(await res.body.text()) as AsyncJob;
      const done = await this.waitFor(job);
      this.saveBlob(await this.download(done), done.result_filename ?? fallback);
      return;
    }
    if (!res.body) throw new Error('empty_response');
    this.saveBlob(res.body, filenameFrom(res.headers.get('Content-Disposition')) ?? fallback);
  }
}
