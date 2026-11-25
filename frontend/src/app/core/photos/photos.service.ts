import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { KeyStoreService } from '../crypto/key-store.service';
import { preparePhoto } from './prepare-photo';

export const MAX_PHOTOS_PER_EVENT = 6;

/** Metadati di una foto: il contenuto è cifrato e si scarica a parte. */
export interface EventPhoto {
  id: string;
  event_id: string;
  client_uuid: string | null;
  created_at: string;
  created_by: string | null;
  size_bytes: number;
  key_wrapped: string;
  key_version: number;
}

/** Foto pronta per l'invio: già ridotta e cifrata sul dispositivo (anche quella in coda offline). */
export interface EncryptedPhoto {
  ciphertext: Uint8Array;
  key_wrapped: string;
  key_version: number;
}

/**
 * Foto degli eventi: si riducono e si cifrano sul dispositivo con la chiave pubblica della società (come i
 * dati identificativi), il server conserva solo il contenuto cifrato; per vederle serve la chiave sbloccata.
 */
@Injectable({ providedIn: 'root' })
export class PhotosService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);
  private readonly keyStore = inject(KeyStoreService);

  list(eventId: string): Observable<EventPhoto[]> {
    return this.api.get<EventPhoto[]>(`events/${eventId}/photos`);
  }

  /** Riduce e cifra un file scelto dall'utente. Restituisce anche l'anteprima in chiaro, solo in memoria. */
  async prepare(file: Blob): Promise<EncryptedPhoto & { preview: Blob }> {
    const photo = await preparePhoto(file);
    const enc = await this.keyStore.encryptPhoto(photo.bytes);
    if (!enc) throw new Error('company_key_missing');
    return { ...enc, preview: new Blob([photo.bytes as BlobPart], { type: 'image/jpeg' }) };
  }

  upload(eventId: string, photo: EncryptedPhoto, clientUuid?: string): Observable<EventPhoto> {
    const form = new FormData();
    form.append('file', new Blob([photo.ciphertext as BlobPart], { type: 'application/octet-stream' }), 'foto.bin');
    form.append('key_wrapped', photo.key_wrapped);
    form.append('key_version', String(photo.key_version));
    if (clientUuid) form.append('client_uuid', clientUuid);
    return this.http.post<EventPhoto>(this.api.url(`events/${eventId}/photos`), form);
  }

  remove(id: string): Observable<void> {
    return this.api.delete<void>(`photos/${id}`);
  }

  /** Scarica il contenuto cifrato e lo decifra con la chiave della società (lettura registrata dal server). */
  async open(photo: EventPhoto): Promise<Uint8Array> {
    const data = await firstValueFrom(this.http.get(this.api.url(`photos/${photo.id}/content`), { responseType: 'arraybuffer' }));
    return this.keyStore.decryptPhoto(new Uint8Array(data), photo.key_wrapped, photo.key_version);
  }
}
