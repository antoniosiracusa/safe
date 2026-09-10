import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective } from '@jsverse/transloco';
import { map } from 'rxjs/operators';

import { CanDirective } from '../../core/authz/can.directive';
import { FilterStore } from '../../core/filters/filter.store';

/** Pagina segnaposto per le sezioni delle milestone successive: mostra il permesso richiesto
 *  (bloccata se manca) e i filtri attivi, così barra filtri e URL sono verificabili da subito. */
@Component({
  selector: 'safe-placeholder',
  imports: [TranslocoDirective, CanDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t(data().titleKey) }}</h1>
      <ng-container *safeCan="data().permission">
        <div class="placeholder">
          <p>{{ t('placeholder.coming', { milestone: data().milestone }) }}</p>
          @if (data().filters) {
            <p class="filters">
              <span>{{ t('placeholder.active_filters') }}</span>
              <code>{{ filterStore.httpParams().toString() || '—' }}</code>
            </p>
          }
        </div>
      </ng-container>
    </ng-container>
  `,
  styles: `
    h1 { margin: 0 0 1rem; font-size: 1.4rem; }
    .placeholder { background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-radius: 6px; padding: 1.5rem; color: var(--p-text-muted-color); }
    .filters { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin: 0.75rem 0 0; }
    code { background: var(--p-surface-100); padding: 0.15rem 0.4rem; border-radius: 3px; word-break: break-all; }
  `,
})
export class PlaceholderComponent {
  readonly filterStore = inject(FilterStore);
  private readonly route = inject(ActivatedRoute);
  readonly data = toSignal(
    this.route.data.pipe(
      map((d) => ({
        titleKey: (d['titleKey'] as string) ?? 'nav.home',
        permission: (d['permission'] as string) ?? '',
        milestone: (d['milestone'] as string) ?? '',
        filters: Boolean(d['filters']),
      })),
    ),
    { initialValue: { titleKey: 'nav.home', permission: '', milestone: '', filters: false } },
  );
}
