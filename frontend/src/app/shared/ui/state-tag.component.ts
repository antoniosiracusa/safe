import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { TagModule } from 'primeng/tag';

/** Stato di validità e blocco di un evento/persona, sempre con testo (non solo colore). */
@Component({
  selector: 'safe-state-tag',
  imports: [TagModule, TranslocoDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      @switch (kind()) {
        @case ('valid') {
          <p-tag [severity]="value() ? 'success' : 'warn'" [value]="value() ? t('state.valid') : t('state.invalid')" [rounded]="true" />
        }
        @case ('locked') {
          <p-tag [severity]="value() ? 'secondary' : 'info'" [icon]="value() ? 'pi pi-lock' : 'pi pi-lock-open'" [value]="value() ? t('state.locked') : t('state.open')" [rounded]="true" />
        }
        @case ('bool') {
          @if (value() === null || value() === undefined) {
            <span class="muted">{{ t('common.unclassified') }}</span>
          } @else {
            {{ value() ? t('common.yes') : t('common.no') }}
          }
        }
      }
    </ng-container>
  `,
  styles: `.muted { color: var(--p-text-muted-color); font-style: italic; }`,
})
export class StateTagComponent {
  readonly kind = input.required<'valid' | 'locked' | 'bool'>();
  readonly value = input<boolean | null | undefined>(null);
}
