import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { CanDirective } from '../../core/authz/can.directive';
import { ChartCardComponent } from '../../shared/charts/chart-card.component';

@Component({
  selector: 'safe-stats-weather',
  imports: [TranslocoDirective, CanDirective, ChartCardComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head"><h1>{{ t('nav.stats_weather') }}</h1></div>
      <ng-container *safeCan="'stats.view'">
        <div class="grid">
          <safe-chart-card titleKey="stats.weather" endpoint="weather/weather" kind="bar" />
          <safe-chart-card titleKey="stats.snow" endpoint="weather/snow" kind="bar" />
          <safe-chart-card titleKey="stats.wind" endpoint="weather/wind" kind="doughnut" />
          <safe-chart-card titleKey="stats.visibility" endpoint="weather/visibility" kind="doughnut" />
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class WeatherPageComponent {}
