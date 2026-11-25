import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { RescueService } from '../api/rescue.service';
import { EventDetail, Person } from '../api/rescue.models';
import { EventPhoto, PhotosService } from '../photos/photos.service';
import { OfflineQueueService } from './offline-queue.service';
import { PwaService } from './pwa.service';

describe('OfflineQueueService', () => {
  let rescue: jasmine.SpyObj<RescueService>;
  let photos: jasmine.SpyObj<PhotosService>;
  let online: { online: () => boolean };
  let service: OfflineQueueService;

  beforeEach(async () => {
    rescue = jasmine.createSpyObj<RescueService>('RescueService', ['createEvent', 'addPerson']);
    photos = jasmine.createSpyObj<PhotosService>('PhotosService', ['upload']);
    online = { online: () => true };
    TestBed.configureTestingModule({
      providers: [
        { provide: RescueService, useValue: rescue },
        { provide: PhotosService, useValue: photos },
        { provide: PwaService, useValue: online },
      ],
    });
    service = TestBed.inject(OfflineQueueService);
    await service.clearAll();
  });

  afterEach(async () => {
    await service.clearAll();
    await service.close();
  });

  it('invia evento e persone, poi segna "sent" con il codice breve', async () => {
    rescue.createEvent.and.returnValue(of({ id: '01234567-89ab-cdef-0123-456789abcdef' } as EventDetail));
    rescue.addPerson.and.returnValue(of({} as Person));
    const q = service;
    await q.enqueue({ dateandtime: '2026-12-01T10:00:00Z', team: 't1' }, [{ age: 30 }, { age: 8 }], 12);
    await q.sync();
    const items = await q.refresh();
    expect(items.length).toBe(1);
    expect(items[0].status).toBe('sent');
    expect(items[0].server_code).toBe('89ABCDEF');
    expect(rescue.createEvent).toHaveBeenCalledTimes(1);
    expect(rescue.createEvent.calls.mostRecent().args[0].client_uuid).toBe(items[0].id);
    expect(rescue.addPerson).toHaveBeenCalledTimes(2);
    expect(q.pending()).toBe(0);
  });

  it('senza rete resta "pending" senza contare tentativi; con errore server passa a "error"', async () => {
    rescue.createEvent.and.returnValue(throwError(() => ({ status: 0 })));
    const q = service;
    await q.enqueue({ dateandtime: '2026-12-01T10:00:00Z', team: 't1' }, [], null);
    await q.sync();
    let items = await q.refresh();
    expect(items[0].status).toBe('pending');
    expect(items[0].attempts).toBe(0);
    expect(q.pending()).toBe(1);

    rescue.createEvent.and.returnValue(throwError(() => new HttpErrorResponse({ status: 403, error: { detail: 'Permesso negato' } })));
    await q.sync();
    items = await q.refresh();
    expect(items[0].status).toBe('error');
    expect(items[0].attempts).toBe(1);
    expect(items[0].last_error).toContain('Permesso');

    // riprova esplicita dopo la correzione lato server
    rescue.createEvent.and.returnValue(of({ id: 'aaaaaaaa-0000-0000-0000-000000000001' } as EventDetail));
    await q.retry(items[0].id);
    await q.sync();
    items = await q.refresh();
    expect(items[0].status).toBe('sent');
  });

  it('non ricrea l\'evento se era già stato creato prima di un errore sulle persone', async () => {
    rescue.createEvent.and.returnValue(of({ id: 'bbbbbbbb-0000-0000-0000-000000000002' } as EventDetail));
    rescue.addPerson.and.returnValue(throwError(() => ({ status: 500 })));
    const q = service;
    await q.enqueue({ dateandtime: '2026-12-01T10:00:00Z', team: 't1' }, [{ age: 40 }], null);
    await q.sync();
    let items = await q.refresh();
    expect(items[0].status).toBe('error');
    expect(items[0].server_id).toBe('bbbbbbbb-0000-0000-0000-000000000002');

    rescue.addPerson.and.returnValue(of({} as Person));
    await q.retry(items[0].id);
    await q.sync();
    items = await q.refresh();
    expect(items[0].status).toBe('sent');
    expect(rescue.createEvent).toHaveBeenCalledTimes(1);
  });

  it('invia le foto dopo le persone, una volta sola, e ne toglie il contenuto dal telefono', async () => {
    rescue.createEvent.and.returnValue(of({ id: 'cccccccc-0000-0000-0000-000000000003' } as EventDetail));
    rescue.addPerson.and.returnValue(of({} as Person));
    // la seconda foto fallisce la prima volta (rete instabile in quota)
    let calls = 0;
    photos.upload.and.callFake(() => (++calls === 2 ? throwError(() => ({ status: 500 })) : of({} as EventPhoto)));
    const q = service;
    const enc = (n: number) => ({ ciphertext: new Uint8Array([n, n, n]), key_wrapped: 'k' + n, key_version: 1 });
    await q.enqueue({ dateandtime: '2026-12-01T10:00:00Z', team: 't1' }, [{ age: 30 }], null, [enc(1), enc(2)]);
    await q.sync();
    let items = await q.refresh();
    expect(items[0].status).toBe('error');
    expect(items[0].photos!.map((p) => p.sent)).toEqual([true, false]);
    expect(items[0].photos![0].ciphertext).toBeNull(); // inviata: il contenuto lascia il telefono
    expect(items[0].photos![1].ciphertext).toEqual(new Uint8Array([2, 2, 2])); // da rimandare, conservata cifrata

    await q.retry(items[0].id);
    await q.sync();
    items = await q.refresh();
    expect(items[0].status).toBe('sent');
    expect(photos.upload).toHaveBeenCalledTimes(3); // la prima non viene rimandata
    const [eventId, sent, clientUuid] = photos.upload.calls.mostRecent().args;
    expect(eventId).toBe('cccccccc-0000-0000-0000-000000000003');
    expect(sent.key_wrapped).toBe('k2');
    expect(clientUuid).toBe(items[0].photos![1].client_uuid); // idempotenza lato server
  });
});
