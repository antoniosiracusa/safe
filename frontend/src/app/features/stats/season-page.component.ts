import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, effect, inject, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';

import { SeasonSummary, StatsService } from '../../core/api/stats.service';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterStore } from '../../core/filters/filter.store';

@Component({
  selector: 'safe-stats-season',
  imports: [TranslocoDirective, RouterLink, ButtonModule, CanDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head"><h1>{{ t('nav.stats_season') }}</h1></div>
      <ng-container *safeCan="'stats.advanced'">
        <section class="table-card">
          @if (summary(); as s) {
            <h2>{{ t('stats.season_summary_title', { season: s.season }) }} @if (s.last_week) { <span class="sub">· {{ t('stats.last_week', { from: s.last_week.from, to: s.last_week.to }) }}</span> }</h2>
          }
          @if (error()) {
            <p class="state" role="alert">{{ t('common.load_error') }} <p-button [label]="t('common.retry')" [text]="true" size="small" (onClick)="load()" /></p>
          } @else if (summary(); as s) {
            @if (!s.rows.length) {
              <p class="state">{{ t('stats.empty') }}</p>
            } @else {
              <div class="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{{ t('fields.team') }}</th>
                      <th>{{ t('stats.col_season') }}</th>
                      <th>{{ t('stats.col_last_week') }}</th>
                      <th>{{ t('stats.col_unlocked') }}</th>
                      <th>{{ t('stats.col_invalid') }}</th>
                      <th>{{ t('stats.col_helicopter') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (r of s.rows; track r.team.id) {
                      <tr>
                        <td>{{ r.team.name }}</td>
                        <td>{{ r.season_events }}</td>
                        <td>{{ r.last_week_events }}</td>
                        <td><a [routerLink]="['/', lang(), 'data', 'events']" [queryParams]="{ team: r.team.id, season: s.season }" queryParamsHandling="merge">{{ r.unlocked_events }}</a></td>
                        <td><a [routerLink]="['/', lang(), 'data', 'events']" [queryParams]="{ team: r.team.id, season: s.season, valid_only: null }" queryParamsHandling="merge">{{ r.invalid_events }}</a></td>
                        <td>{{ r.helicopter_rescues }}</td>
                      </tr>
                    }
                  </tbody>
                  <tfoot>
                    <tr>
                      <td>{{ t('stats.total') }}</td>
                      <td>{{ s.totals['season_events'] }}</td>
                      <td>{{ s.totals['last_week_events'] }}</td>
                      <td>{{ s.totals['unlocked_events'] }}</td>
                      <td>{{ s.totals['invalid_events'] }}</td>
                      <td>{{ s.totals['helicopter_rescues'] }}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            }
          } @else {
            <p class="state">{{ t('common.loading') }}</p>
          }
        </section>
      </ng-container>
    </ng-container>
  `,
})
export class SeasonPageComponent {
  private readonly stats = inject(StatsService);
  private readonly filterStore = inject(FilterStore);
  private readonly transloco = inject(TranslocoService);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });
  readonly summary = signal<SeasonSummary | null>(null);
  readonly error = signal(false);

  constructor() {
    effect(() => {
      this.filterStore.httpParams();
      untracked(() => this.load());
    });
  }

  load(): void {
    this.error.set(false);
    this.stats.seasonSummary(this.filterStore.httpParams()).subscribe({
      next: (s) => this.summary.set(s),
      error: (err: HttpErrorResponse) => this.error.set(err.status !== 403),
    });
  }
}
