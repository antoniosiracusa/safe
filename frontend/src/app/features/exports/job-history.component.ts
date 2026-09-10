import { DatePipe, UpperCasePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';

import { ExportRun, ExportsService } from '../../core/api/exports.service';
import { JobsService } from '../../core/api/jobs.service';

/** Storico delle esportazioni della società (GET /exports), con download dei file ancora disponibili. */
@Component({
  selector: 'safe-job-history',
  imports: [DatePipe, UpperCasePipe, TranslocoDirective, ButtonModule, TableModule, TagModule, TooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './exports-page.scss',
  template: `
    <ng-container *transloco="let t">
      <section class="card">
        <div class="history-head">
          <h2>{{ t('exports.history') }}</h2>
          <p-button icon="pi pi-refresh" [text]="true" size="small" [loading]="loading()" (onClick)="reload()" [attr.aria-label]="t('common.retry')" />
        </div>
        @if (error()) {
          <p class="error-box" role="alert">{{ t('common.load_error') }}</p>
        }
        <p-table [value]="rows()" [loading]="loading()" styleClass="p-datatable-sm" [tableStyle]="{ 'min-width': '720px' }">
          <ng-template #header>
            <tr>
              <th>{{ t('exports.created') }}</th>
              <th>{{ t('exports.template') }}</th>
              <th>{{ t('exports.format') }}</th>
              <th class="num">{{ t('exports.rows') }}</th>
              <th>{{ t('exports.requested_by') }}</th>
              <th>{{ t('exports.status') }}</th>
              <th></th>
            </tr>
          </ng-template>
          <ng-template #body let-row>
            <tr>
              <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
              <td>{{ templateLabel(row) }} @if (row.export?.administrative_area_code) { <small>· {{ row.export.administrative_area_code }}</small> }</td>
              <td>{{ (row.export?.format || row.result_mime || '—') | uppercase }}</td>
              <td class="num">{{ row.export?.row_count ?? '—' }}</td>
              <td>{{ row.requested_by || '—' }}</td>
              <td><p-tag [value]="t('exports.status_' + row.status)" [severity]="severity(row)" /></td>
              <td class="num">
                @if (row.download_url) {
                  <p-button icon="pi pi-download" [text]="true" size="small" [loading]="downloading() === row.id" (onClick)="download(row)" [pTooltip]="row.result_filename" tooltipPosition="left" [attr.aria-label]="t('exports.download')" />
                } @else if (row.status === 'done') {
                  <small>{{ t('exports.expired') }}</small>
                }
              </td>
            </tr>
          </ng-template>
          <ng-template #emptymessage>
            <tr><td colspan="7" class="empty">@if (!loading()) { {{ t('exports.history_empty') }} }</td></tr>
          </ng-template>
        </p-table>
      </section>
    </ng-container>
  `,
})
export class JobHistoryComponent {
  /** Limita lo storico a un tipo di job (export_regional | export_dataset). */
  readonly kind = input<string | null>(null);

  private readonly exports = inject(ExportsService);
  private readonly jobs = inject(JobsService);
  private readonly messages = inject(MessageService, { optional: true });
  private readonly transloco = inject(TranslocoService);

  private readonly all = signal<ExportRun[]>([]);
  readonly rows = computed(() => (this.kind() ? this.all().filter((r) => r.kind === this.kind()) : this.all()));
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly downloading = signal<string | null>(null);

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(false);
    this.exports.list().subscribe({
      next: (res) => {
        this.all.set(res.results);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set(true);
      },
    });
  }

  templateLabel(row: ExportRun): string {
    const code = row.export?.template ?? row.kind;
    const key = `exports.template_${code}`;
    const label = this.transloco.translate(key);
    return label === key ? code : label;
  }

  severity(row: ExportRun): 'success' | 'info' | 'danger' | 'secondary' {
    if (row.status === 'done') return 'success';
    if (row.status === 'failed' || row.status === 'cancelled') return 'danger';
    if (row.status === 'running') return 'info';
    return 'secondary';
  }

  async download(row: ExportRun): Promise<void> {
    this.downloading.set(row.id);
    try {
      this.jobs.saveBlob(await this.jobs.download(row), row.result_filename ?? `${row.kind}.bin`);
    } catch {
      this.messages?.add({ severity: 'error', summary: this.transloco.translate('exports.error') });
    } finally {
      this.downloading.set(null);
    }
  }
}
