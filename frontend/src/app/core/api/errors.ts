import { HttpErrorResponse } from '@angular/common/http';

/** Messaggio leggibile da una risposta di errore uniforme {code, detail, fields}. */
export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof HttpErrorResponse && err.error && typeof err.error === 'object') {
    const body = err.error as { detail?: string; fields?: Record<string, string[] | string> };
    if (body.fields) {
      const parts = Object.entries(body.fields).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : String(v)}`);
      if (parts.length) return parts.join(' · ');
    }
    if (body.detail) return body.detail;
  }
  return fallback;
}

export function errorCode(err: unknown): string | null {
  if (err instanceof HttpErrorResponse && err.error && typeof err.error === 'object') {
    return (err.error as { code?: string }).code ?? null;
  }
  return null;
}
