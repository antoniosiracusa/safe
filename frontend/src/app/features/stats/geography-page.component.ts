import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { CanDirective } from '../../core/authz/can.directive';
import { ChartCardComponent } from '../../shared/charts/chart-card.component';
import { LimitSliderComponent } from './limit-slider.component';

@Component({
  selector: 'safe-stats-geography',
  imports: [TranslocoDirective, CanDirective, ChartCardComponent, LimitSliderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head"><h1>{{ t('nav.stats_geography') }}</h1></div>
      <ng-container *safeCan="'stats.view'">
        <div class="grid">
          <safe-chart-card titleKey="stats.ski_areas" endpoint="geography/ski-areas" kind="bar" />
          <safe-chart-card titleKey="stats.slope_difficulty" endpoint="geography/slope-difficulty" kind="doughnut" />
          <div class="span-2">
            <safe-limit-slider #sl param="slopes_limit" [default]="20" [min]="3" [max]="60" labelKey="stats.slopes_shown" />
            <safe-chart-card titleKey="stats.slopes" endpoint="geography/slopes" kind="hbar" [extraParams]="{ limit: sl.value() }" [height]="Math.max(300, 22 * sl.value() + 80)" />
          </div>
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class GeographyPageComponent {
  readonly Math = Math;
}
