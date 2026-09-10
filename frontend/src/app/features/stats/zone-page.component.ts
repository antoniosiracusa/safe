import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { ToggleSwitchModule } from 'primeng/toggleswitch';

import { StatsService, ZoneTable } from '../../core/api/stats.service';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterStore } from '../../core/filters/filter.store';
import { ChartCardComponent } from '../../shared/charts/chart-card.component';

@Component({
  selector: 'safe-stats-zone',
  imports: [FormsModule, TranslocoDirective, ButtonModule, ToggleSwitchModule, CanDirective, ChartCardComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head">
        <h1>{{ t('nav.stats_zone') }}</h1>
        <div class="controls">
          <label for="incremental">{{ t('stats.incremental') }}</label>
          <p-toggleSwitch inputId="incremental" [ngModel]="incremental()" (ngModelChange)="incremental.set($event)" />
        </div>
      </div>
      <ng-container *safeCan="'stats.view'">
        <div class="grid">
          <safe-chart-card class="span-2" titleKey="stats.annual_distribution" endpoint="zone-summary/annual-distribution" [kind]="incremental() ? 'line' : 'bar'" [extraParams]="{ incremental: incremental() }" [height]="340" />
          <section class="table-card span-2">
            <h2>{{ t('stats.zone_table') }}</h2>
            @if (error()) {
              <p class="state" role="alert">{{ t('common.load_error') }} <p-button [label]="t('common.retry')" [text]="true" size="small" (onClick)="load()" /></p>
            } @else if (table(); as tb) {
              @if (!tb.rows.length) {
                <p class="state">{{ t('stats.empty') }}</p>
              } @else {
                <div class="scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{{ t('fields.zone') }}</th>
                        @for (c of tb.columns; track c) { <th>{{ c }}<br /><span class="sub">{{ t('stats.events_persons') }}</span></th> }
                        <th>{{ t('stats.total') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (r of tb.rows; track r.zone.id) {
                        <tr>
                          <td>{{ r.zone.name }}</td>
                          @for (c of r.cells; track $index) { <td>{{ c.events }} / {{ c.persons }}</td> }
                          <td>{{ r.total.events }} / {{ r.total.persons }}</td>
                        </tr>
                      }
                    </tbody>
                    <tfoot>
                      <tr>
                        <td>{{ t('stats.total') }}</td>
                        @for (c of tb.totals; track $index) { <td>{{ c.events }} / {{ c.persons }}</td> }
                        <td>{{ grand(tb).events }} / {{ grand(tb).persons }}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              }
            } @else {
              <p class="state">{{ t('common.loading') }}</p>
            }
          </section>
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class ZonePageComponent {
  private readonly stats = inject(StatsService);
  private readonly filterStore = inject(FilterStore);
  readonly incremental = signal(false);
  readonly table = signal<ZoneTable | null>(null);
  readonly error = signal(false);

  constructor() {
    effect(() => {
      this.filterStore.httpParams();
      untracked(() => this.load());
    });
  }

  load(): void {
    this.error.set(false);
    this.stats.zoneTable(this.filterStore.httpParams()).subscribe({
      next: (tb) => this.table.set(tb),
      error: (err: HttpErrorResponse) => this.error.set(err.status !== 403),
    });
  }

  grand(tb: ZoneTable): { events: number; persons: number } {
    return tb.totals.reduce((a, c) => ({ events: a.events + c.events, persons: a.persons + c.persons }), { events: 0, persons: 0 });
  }
}
