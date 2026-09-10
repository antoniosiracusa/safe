import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { CanDirective } from '../../core/authz/can.directive';
import { ChartCardComponent } from '../../shared/charts/chart-card.component';
import { AgeClusterToggleComponent } from './age-cluster-toggle.component';

@Component({
  selector: 'safe-stats-typology',
  imports: [TranslocoDirective, CanDirective, ChartCardComponent, AgeClusterToggleComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './stats-page.scss',
  template: `
    <ng-container *transloco="let t">
      <div class="page-head">
        <h1>{{ t('nav.stats_typology') }}</h1>
        <safe-age-cluster-toggle #ac />
      </div>
      <ng-container *safeCan="'stats.view'">
        <div class="grid">
          <safe-chart-card titleKey="stats.age_cause" endpoint="typology/age-cause" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" />
          <safe-chart-card titleKey="stats.cause" endpoint="typology/cause" kind="doughnut" />
          <safe-chart-card titleKey="stats.age_equipment" endpoint="typology/age-equipment" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" />
          <safe-chart-card titleKey="stats.age_insurance" endpoint="typology/age-insurance" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" />
          <safe-chart-card titleKey="stats.age_evacuation" endpoint="typology/age-evacuation-mean" kind="stacked" [extraParams]="{ age_cluster: ac.cluster() }" />
          <safe-chart-card titleKey="stats.evacuation_total" endpoint="typology/evacuation-means-total" kind="bar" />
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class TypologyPageComponent {}
