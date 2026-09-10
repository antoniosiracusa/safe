import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective } from '@jsverse/transloco';
import { SelectButtonModule } from 'primeng/selectbutton';
import { map } from 'rxjs/operators';

export type AgeCluster = 'standard' | 'veneto_a01';

/** Selettore delle classi di età (standard | A01 Veneto), riflesso nella URL come `age_cluster`. */
@Component({
  selector: 'safe-age-cluster-toggle',
  imports: [FormsModule, TranslocoDirective, SelectButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="controls" *transloco="let t">
      <label for="age-cluster">{{ t('stats.age_cluster') }}</label>
      <p-selectButton
        id="age-cluster"
        [options]="[{ value: 'standard', label: t('stats.age_cluster_standard') }, { value: 'veneto_a01', label: t('stats.age_cluster_a01') }]"
        optionLabel="label"
        optionValue="value"
        [ngModel]="cluster()"
        (ngModelChange)="set($event)"
        [allowEmpty]="false"
        size="small"
      />
    </div>
  `,
  styles: `.controls { display: flex; align-items: center; gap: 0.5rem; } label { font-size: 0.8rem; color: var(--p-text-muted-color); }`,
})
export class AgeClusterToggleComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly cluster = toSignal(
    this.route.queryParamMap.pipe(map((q) => (q.get('age_cluster') === 'veneto_a01' ? 'veneto_a01' : 'standard') as AgeCluster)),
    { initialValue: 'standard' as AgeCluster },
  );

  set(value: AgeCluster): void {
    void this.router.navigate([], { queryParams: { age_cluster: value === 'standard' ? null : value }, queryParamsHandling: 'merge' });
  }
}
