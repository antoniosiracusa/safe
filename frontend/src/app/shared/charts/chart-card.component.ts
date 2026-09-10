import { HttpErrorResponse, HttpParams } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { toSignal } from '@angular/core/rxjs-interop';
import { ChartConfiguration, ChartType } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { SkeletonModule } from 'primeng/skeleton';
import { TooltipModule } from 'primeng/tooltip';

import { ChartData, StatsService } from '../../core/api/stats.service';
import { FilterStore } from '../../core/filters/filter.store';

export type CardChartKind = 'bar' | 'stacked' | 'hbar' | 'doughnut' | 'line';

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/**
 * Card grafico: carica una rotta /stats con i filtri globali (+ parametri propri), rende con Chart.js,
 * offre schermo intero, download PNG e vista tabellare (accessibilità). Stati: caricamento, vuoto, errore.
 */
@Component({
  selector: 'safe-chart-card',
  imports: [TranslocoDirective, BaseChartDirective, ButtonModule, DialogModule, SkeletonModule, TooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chart-card.component.html',
  styleUrl: './chart-card.component.scss',
})
export class ChartCardComponent {
  readonly titleKey = input.required<string>();
  readonly endpoint = input.required<string>();
  readonly kind = input<CardChartKind>('bar');
  readonly extraParams = input<Record<string, string | number | boolean | null | undefined>>({});
  readonly height = input(300);

  private readonly stats = inject(StatsService);
  private readonly filterStore = inject(FilterStore);
  private readonly transloco = inject(TranslocoService);
  private readonly chartRef = viewChild(BaseChartDirective);

  readonly data = signal<ChartData | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly tableView = signal(false);
  readonly fullscreen = signal(false);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });
  private version = 0;

  readonly isEmpty = computed(() => {
    const d = this.data();
    return !!d && (d.meta?.total ?? d.datasets.reduce((a, s) => a + s.data.reduce((x, y) => x + y, 0), 0)) === 0;
  });

  readonly chartType = computed<ChartType>(() => {
    const k = this.kind();
    if (k === 'doughnut') return 'doughnut';
    if (k === 'line') return 'line';
    return 'bar';
  });

  readonly chartData = computed<ChartConfiguration['data']>(() => {
    const d = this.data();
    if (!d) return { labels: [], datasets: [] };
    const k = this.kind();
    return {
      labels: d.labels,
      datasets: d.datasets.map((s) => ({
        label: s.label,
        data: s.data,
        backgroundColor: s.backgroundColor,
        borderColor: k === 'line' ? (s.backgroundColor as string) : 'transparent',
        borderWidth: k === 'line' ? 2 : 0,
        borderRadius: k === 'line' || k === 'doughnut' ? 0 : 4,
        borderSkipped: 'start' as const,
        barPercentage: 0.7,
        categoryPercentage: 0.8,
        pointRadius: k === 'line' ? 3 : 0,
        tension: 0.2,
        fill: false,
        ...(k === 'doughnut' ? { borderColor: cssVar('--p-surface-0', '#fff'), borderWidth: 2 } : {}),
      })),
    };
  });

  readonly chartOptions = computed<ChartConfiguration['options']>(() => {
    const k = this.kind();
    const d = this.data();
    const text = cssVar('--p-text-color', '#16202b');
    const muted = cssVar('--p-text-muted-color', '#5b6b7b');
    const grid = cssVar('--p-surface-200', '#e5e7eb');
    const multi = (d?.datasets.length ?? 0) > 1;
    const base: ChartConfiguration['options'] = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      plugins: {
        legend: { display: multi || k === 'doughnut', position: 'bottom', labels: { color: text, boxWidth: 12, usePointStyle: true } },
        tooltip: { enabled: true, mode: k === 'line' ? 'index' : 'nearest', intersect: k !== 'line' },
      },
    };
    if (k === 'doughnut') return { ...base, cutout: '55%' };
    const stacked = k === 'stacked';
    return {
      ...base,
      indexAxis: k === 'hbar' ? 'y' : 'x',
      scales: {
        x: { stacked, ticks: { color: muted, autoSkip: true, maxRotation: 0 }, grid: { display: k === 'hbar', color: grid } },
        y: { stacked, beginAtZero: true, ticks: { color: muted, precision: 0 }, grid: { display: k !== 'hbar', color: grid } },
      },
    };
  });

  constructor() {
    effect(() => {
      this.filterStore.httpParams();
      this.extraParams();
      this.endpoint();
      this.lang();
      untracked(() => this.load());
    });
  }

  load(): void {
    const v = ++this.version;
    this.loading.set(true);
    this.error.set(false);
    let params: HttpParams = this.filterStore.httpParams().set('lang', this.lang());
    for (const [k, val] of Object.entries(this.extraParams())) {
      if (val !== null && val !== undefined && val !== '') params = params.set(k, String(val));
    }
    this.stats.chart(this.endpoint(), params).subscribe({
      next: (d) => {
        if (v !== this.version) return;
        this.data.set(d);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        if (v !== this.version) return;
        this.loading.set(false);
        this.error.set(err.status !== 403);
      },
    });
  }

  download(): void {
    const chart = this.chartRef()?.chart;
    if (!chart) return;
    const link = document.createElement('a');
    link.href = chart.toBase64Image('image/png', 1);
    link.download = `${this.transloco.translate(this.titleKey())}.png`.replace(/[\\/:*?"<>|]/g, '_');
    link.click();
  }

  total(): number {
    return this.data()?.meta?.total ?? 0;
  }

  unitKey(): string {
    return `stats.unit_${this.data()?.meta?.unit ?? 'events'}`;
  }

  rowTotal(i: number): number {
    return this.data()?.datasets.reduce((a, s) => a + (s.data[i] ?? 0), 0) ?? 0;
  }
}
