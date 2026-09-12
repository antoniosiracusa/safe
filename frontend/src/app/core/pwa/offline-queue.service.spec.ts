import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { RescueService } from '../api/rescue.service';
import { EventDetail, Person } from '../api/rescue.models';
import { OfflineQueueService } from './offline-queue.service';
import { PwaService } from './pwa.service';

describe('OfflineQueueService', () => {
  let rescue: jasmine.SpyObj<RescueService>;
  let online: { online: () => boolean };
  let service: OfflineQueueService;

  beforeEach(async () => {
    rescue = jasmine.createSpyObj<RescueService>('RescueService', ['createEvent', 'addPerson']);
    online = { online: () => true };
    TestBed.configureTestingModule({
      providers: [
        { provide: RescueService, useValue: rescue },
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
});
