import { ChangeDetectionStrategy, Component, inject, viewChild } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { CanDirective } from '../../core/authz/can.directive';
import { ChartCardComponent } from '../../shared/charts/chart-card.component';
import { AgeClusterToggleComponent } from './age-cluster-toggle.component';
import { LimitSliderComponent } from './limit-slider.component';

@Component({
  selector: 'safe-stats-demographics',
  imports: [TranslocoDirective, CanDirective, ChartCardComponent, AgeClusterToggleComponent, LimitSliderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head">
        <h1>{{ t('nav.stats_demographics') }}</h1>
        <safe-age-cluster-toggle #ac />
      </div>
      <ng-container *safeCan="'stats.view'">
        <div class="grid">
          <safe-chart-card titleKey="stats.age_gender" endpoint="demographics/age-gender" kind="bar" [extraParams]="{ age_cluster: ac.cluster() }" />
          <safe-chart-card titleKey="stats.country" endpoint="demographics/country" kind="hbar" [extraParams]="{ limit: countries.value() }">
          </safe-chart-card>
          <safe-limit-slider #countries param="countries_limit" [default]="10" [min]="3" [max]="30" labelKey="stats.countries_shown" />
          <safe-chart-card class="span-2" titleKey="stats.nationality_weekday" endpoint="demographics/nationality-weekday" kind="stacked" />
          <safe-chart-card titleKey="stats.age_diagnosis" endpoint="demographics/age-diagnosis" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" [height]="360" />
          <safe-chart-card titleKey="stats.age_injury_place" endpoint="demographics/age-injury-place" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" [height]="360" />
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class DemographicsPageComponent {}
