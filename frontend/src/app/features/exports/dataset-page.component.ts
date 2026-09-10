import { ChangeDetectionStrategy, Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { SelectButtonModule } from 'primeng/selectbutton';
import { ToastModule } from 'primeng/toast';
import { firstValueFrom } from 'rxjs';

import { DatasetRequest, ExportsService } from '../../core/api/exports.service';
import { JobsService } from '../../core/api/jobs.service';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { FilterStore } from '../../core/filters/filter.store';
import { JobHistoryComponent } from './job-history.component';

/** Esportazione CSV/XLSX dei dataset (eventi o persone) con i filtri globali attivi, pseudonimizzata. */
@Component({
  selector: 'safe-exports-dataset',
  imports: [FormsModule, TranslocoDirective, ButtonModule, SelectButtonModule, ToastModule, CanDirective, JobHistoryComponent],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './exports-page.scss',
  templateUrl: './dataset-page.component.html',
})
export class DatasetPageComponent {
  readonly filterStore = inject(FilterStore);
  private readonly filterOptions = inject(FilterOptionsService);
  private readonly exports = inject(ExportsService);
  private readonly jobs = inject(JobsService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  private readonly history = viewChild(JobHistoryComponent);

  readonly dataset = signal<'events' | 'persons'>('events');
  readonly format = signal<'csv' | 'xlsx'>('xlsx');
  readonly generating = signal(false);

  readonly datasetOptions = computed(() => [
    { value: 'events', label: this.transloco.translate('exports.dataset_events') },
    { value: 'persons', label: this.transloco.translate('exports.dataset_persons') },
  ]);
  readonly formatOptions = [
    { value: 'xlsx', label: 'XLSX' },
    { value: 'csv', label: 'CSV' },
  ];

  /** Riepilogo leggibile dei filtri globali attivi. */
  readonly chips = computed(() => {
    const f = this.filterStore.filters();
    const o = this.filterOptions.options();
    const name = (list: { value: string; label: string }[], v: string) => list.find((x) => x.value === v)?.label ?? v;
    const chips: { key: string; value: string }[] = [];
    if (f.team.length) chips.push({ key: 'filters.team', value: f.team.map((t) => name(o.teams, t)).join(', ') });
    if (f.season) chips.push({ key: 'filters.season', value: f.season });
    if (f.date_from || f.date_to) chips.push({ key: 'filters.period', value: `${f.date_from ?? '…'} → ${f.date_to ?? '…'}` });
    if (f.ski_area) chips.push({ key: 'filters.ski_area', value: name(o.ski_areas, f.ski_area) });
    if (f.zone) chips.push({ key: 'filters.zone', value: name(o.zones, f.zone) });
    if (f.valid_only) chips.push({ key: 'filters.valid_only', value: this.transloco.translate('common.yes') });
    return chips;
  });

  constructor() {
    void this.filterOptions.load();
  }

  async generate(): Promise<void> {
    if (this.generating()) return;
    const f = this.filterStore.filters();
    const filters: DatasetRequest['filters'] = {};
    if (f.team.length) filters['team'] = f.team;
    if (f.season) filters['season'] = f.season;
    if (f.date_from) filters['date_from'] = f.date_from;
    if (f.date_to) filters['date_to'] = f.date_to;
    if (f.ski_area) filters['ski_area'] = f.ski_area;
    if (f.zone) filters['zone'] = f.zone;
    if (f.valid_only) filters['valid_only'] = true;
    this.generating.set(true);
    try {
      this.messages.add({ severity: 'info', summary: this.transloco.translate('exports.started') });
      const job = await firstValueFrom(
        this.exports.dataset({ dataset: this.dataset(), format: this.format(), filters, lang: this.transloco.getActiveLang() }),
      );
      const done = await this.jobs.waitAndSave(job);
      this.messages.add({ severity: 'success', summary: this.transloco.translate('exports.done', { name: done.result_filename }) });
      this.history()?.reload();
    } catch {
      this.messages.add({ severity: 'error', summary: this.transloco.translate('exports.error') });
    } finally {
      this.generating.set(false);
    }
  }
}
