import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';
import { SelectButtonModule } from 'primeng/selectbutton';
import { ToastModule } from 'primeng/toast';
import { firstValueFrom } from 'rxjs';

import { AdministrativeArea, AreaLevel, ExportsService, RegionalPreview, RegionalRequest } from '../../core/api/exports.service';
import { JobsService } from '../../core/api/jobs.service';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { FilterStore } from '../../core/filters/filter.store';
import { JobHistoryComponent } from './job-history.component';

/** Esportazione per enti regionali (tracciato A01 Veneto): parametri → anteprima qualità → generazione. */
@Component({
  selector: 'safe-exports-regional',
  imports: [
    DatePipe, FormsModule, TranslocoDirective, ButtonModule, CheckboxModule, MultiSelectModule, SelectModule,
    SelectButtonModule, ToastModule, CanDirective, JobHistoryComponent,
  ],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './exports-page.scss',
  templateUrl: './regional-page.component.html',
})
export class RegionalPageComponent {
  readonly filterOptions = inject(FilterOptionsService);
  private readonly filterStore = inject(FilterStore);
  private readonly exports = inject(ExportsService);
  private readonly jobs = inject(JobsService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  private readonly history = viewChild(JobHistoryComponent);

  readonly season = signal<string | null>(this.filterStore.filters().season);
  readonly area = signal<string | null>(null); // "level:code"
  readonly teams = signal<string[]>(this.filterStore.filters().team);
  readonly format = signal<'xlsx' | 'xls'>('xlsx');
  readonly mergeDuplicates = signal(true);
  readonly excludeBuildings = signal(true);

  readonly areasLoaded = signal<boolean | null>(null);
  readonly areas = signal<AdministrativeArea[]>([]);
  readonly areaOptions = computed(() => [
    { value: null, label: this.transloco.translate('exports.area_all') },
    ...this.areas().map((a) => ({
      value: `${a.level}:${a.code}`,
      label: `${a.name} (${this.transloco.translate('exports.level_' + a.level)}, ${a.code})`,
    })),
  ]);
  readonly formatOptions = [
    { value: 'xlsx', label: 'XLSX' },
    { value: 'xls', label: 'XLS (Excel 97-2003)' },
  ];

  readonly preview = signal<RegionalPreview | null>(null);
  readonly previewing = signal(false);
  readonly generating = signal(false);
  readonly error = signal<string | null>(null);
  readonly canGenerate = computed(() => !!this.preview() && !this.previewing() && !this.generating());

  constructor() {
    void this.filterOptions.load();
    this.exports.administrativeAreas().subscribe({
      next: (res) => {
        this.areasLoaded.set(res.loaded);
        this.areas.set(res.areas);
      },
      error: () => this.areasLoaded.set(false),
    });
  }

  request(): RegionalRequest | null {
    const season = this.season();
    if (!season) return null;
    const area = this.area();
    const [level, code] = area ? area.split(':') : [null, null];
    return {
      template: 'veneto_a01',
      season,
      administrative_area: level && code ? { level: level as AreaLevel, code } : null,
      team: this.teams().length ? this.teams() : null,
      format: this.format(),
      merge_duplicates: this.mergeDuplicates(),
      exclude_in_buildings: this.excludeBuildings(),
    };
  }

  /** Ogni modifica dei parametri invalida l'anteprima. */
  invalidate(): void {
    this.preview.set(null);
  }

  runPreview(): void {
    const req = this.request();
    if (!req) return;
    this.previewing.set(true);
    this.error.set(null);
    this.exports.regionalPreview(req).subscribe({
      next: (pv) => {
        this.preview.set(pv);
        this.previewing.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.previewing.set(false);
        this.error.set(err.error?.detail ?? this.transloco.translate('common.load_error'));
      },
    });
  }

  async generate(): Promise<void> {
    const req = this.request();
    if (!req || !this.canGenerate()) return;
    this.generating.set(true);
    this.error.set(null);
    try {
      this.messages.add({ severity: 'info', summary: this.transloco.translate('exports.started') });
      const job = await firstValueFrom(this.exports.regional(req));
      const done = await this.jobs.waitAndSave(job);
      this.messages.add({ severity: 'success', summary: this.transloco.translate('exports.done', { name: done.result_filename }) });
      this.history()?.reload();
    } catch {
      this.messages.add({ severity: 'error', summary: this.transloco.translate('exports.error') });
    } finally {
      this.generating.set(false);
    }
  }

  warningText(w: { code: string; count?: number }): string {
    return this.transloco.translate(`exports.warning_${w.code}`, { count: w.count ?? 0 });
  }

  shortId(id: string): string {
    return id.slice(-8).toUpperCase();
  }
}
