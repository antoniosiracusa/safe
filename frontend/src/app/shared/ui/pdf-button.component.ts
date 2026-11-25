import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { Menu, MenuModule } from 'primeng/menu';
import { TooltipModule } from 'primeng/tooltip';

import { JobsService } from '../../core/api/jobs.service';
import { FullReportService } from '../../core/reports/full-report.service';
import { SessionService } from '../../core/session/session.service';

/** Pulsante "PDF" del rapporto evento: visibile sempre, attivo solo con il permesso reports.pdf.
 *  Gestisce la risposta immediata (200) e quella differita (202 + polling del job).
 *  Con la chiave sbloccata propone la scelta fra documento completo (con i dati identificativi,
 *  decifrati nel browser) e rapporto pseudonimizzato. */
@Component({
  selector: 'safe-pdf-button',
  imports: [TranslocoDirective, ButtonModule, MenuModule, TooltipModule],
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
        [pTooltip]="allowed() ? (full.available() ? t('pdf.download_choice') : t('pdf.download')) : t('pdf.no_permission')"
        [tooltipPosition]="tooltipPosition()"
        [attr.aria-label]="t('pdf.download')"
        (onClick)="onClick($event, menu)"
      />
      <p-menu #menu [model]="items()" [popup]="true" appendTo="body" />
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
  readonly full = inject(FullReportService);
  private readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });

  readonly allowed = computed(() => this.session.can('reports.pdf'));
  readonly busy = signal(false);

  readonly items = computed(() => {
    this.lang(); // le voci seguono la lingua attiva
    return [
      { label: this.transloco.translate('pdf.full'), icon: 'pi pi-id-card', command: () => void this.download('full') },
      { label: this.transloco.translate('pdf.standard'), icon: 'pi pi-file-pdf', command: () => void this.download('standard') },
    ];
  });

  /** Con la chiave sbloccata si sceglie quale documento scaricare; altrimenti parte subito quello pseudonimizzato. */
  onClick(e: Event, menu: Menu): void {
    e.stopPropagation();
    if (this.busy() || !this.allowed()) return;
    if (this.full.available()) menu.toggle(e);
    else void this.download('standard');
  }

  async download(variant: 'standard' | 'full'): Promise<void> {
    if (this.busy() || !this.allowed()) return;
    this.busy.set(true);
    try {
      if (variant === 'full') {
        await this.full.download(this.eventId());
        this.messages?.add({ severity: 'info', summary: this.transloco.translate('pdf.full_done'), life: 8000 });
      } else {
        await this.jobs.eventReportPdf(this.eventId());
      }
    } catch {
      this.messages?.add({ severity: 'error', summary: this.transloco.translate('pdf.error') });
    } finally {
      this.busy.set(false);
    }
  }
}
