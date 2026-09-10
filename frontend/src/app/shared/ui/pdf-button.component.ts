import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';

import { JobsService } from '../../core/api/jobs.service';
import { SessionService } from '../../core/session/session.service';

/** Pulsante "PDF" del rapporto evento: visibile sempre, attivo solo con il permesso reports.pdf.
 *  Gestisce la risposta immediata (200) e quella differita (202 + polling del job). */
@Component({
  selector: 'safe-pdf-button',
  imports: [TranslocoDirective, ButtonModule, TooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      <p-button
        icon="pi pi-file-pdf"
        [label]="withLabel() ? t('fields.pdf') : undefined"
        [text]="true"
        [size]="size()"
        [loading]="busy()"
        [disabled]="!allowed()"
        [pTooltip]="allowed() ? t('pdf.download') : t('pdf.no_permission')"
        [tooltipPosition]="tooltipPosition()"
        [attr.aria-label]="t('pdf.download')"
        (onClick)="download($event)"
      />
    </ng-container>
  `,
})
export class PdfButtonComponent {
  readonly eventId = input.required<string>();
  readonly withLabel = input(false);
  readonly size = input<'small' | 'large' | undefined>(undefined);
  readonly tooltipPosition = input<'left' | 'right' | 'top' | 'bottom'>('left');

  private readonly session = inject(SessionService);
  private readonly jobs = inject(JobsService);
  private readonly messages = inject(MessageService, { optional: true });
  private readonly transloco = inject(TranslocoService);

  readonly allowed = computed(() => this.session.can('reports.pdf'));
  readonly busy = signal(false);

  async download(e: Event): Promise<void> {
    e.stopPropagation();
    if (this.busy() || !this.allowed()) return;
    this.busy.set(true);
    try {
      await this.jobs.eventReportPdf(this.eventId());
    } catch {
      this.messages?.add({ severity: 'error', summary: this.transloco.translate('pdf.error') });
    } finally {
      this.busy.set(false);
    }
  }
}
