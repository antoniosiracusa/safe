import { Injectable, computed, inject } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { JobsService } from '../api/jobs.service';
import { RescueService } from '../api/rescue.service';
import { KeyStoreService } from '../crypto/key-store.service';
import { SessionService } from '../session/session.service';

/**
 * Rapporto PDF completo dei dati identificativi. Disponibile solo a chi ha la chiave sbloccata ed è
 * abilitato alla chiave della società: i dati vengono decifrati e scritti nel PDF nel browser, il server
 * non li riceve mai in chiaro (registra però in audit sia lo scaricamento sia ogni lettura dell'identità).
 */
@Injectable({ providedIn: 'root' })
export class FullReportService {
  private readonly jobs = inject(JobsService);
  private readonly rescue = inject(RescueService);
  private readonly keyStore = inject(KeyStoreService);
  private readonly session = inject(SessionService);
  private readonly transloco = inject(TranslocoService);

  readonly available = computed(
    () => this.session.can('reports.pdf') && this.session.can('persons.reveal_identity') && this.keyStore.canDecrypt(),
  );

  async download(eventId: string): Promise<void> {
    const [file, event] = await Promise.all([
      this.jobs.eventReportFile(eventId, 'full'),
      firstValueFrom(this.rescue.getEvent(eventId)),
    ]);
    const identities = new Map<string, Record<string, string>>();
    for (const person of event.persons) {
      if (!person.has_identity) continue;
      const data = { ...(await this.keyStore.readIdentity(person.id)) };
      if (data['document_type']) data['document_type'] = this.transloco.translate(`identity.document_types.${data['document_type']}`);
      identities.set(person.id, data);
    }
    const { fillIdentityFields } = await import('./identity-pdf');
    const bytes = await fillIdentityFields(await file.blob.arrayBuffer(), identities);
    this.jobs.saveBlob(new Blob([bytes as BlobPart], { type: 'application/pdf' }), file.filename);
  }
}
