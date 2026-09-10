import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/** Stato "permesso mancante": il contenitore resta al suo posto, sfumato, con messaggio informativo. */
@Component({
  selector: 'safe-locked-panel',
  imports: [TranslocoDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="locked" role="status" *transloco="let t">
      <i class="pi pi-lock" aria-hidden="true"></i>
      <h3>{{ title() || t('locked.title') }}</h3>
      <p>{{ t('locked.message') }}</p>
      <p class="hint">{{ t('locked.contact') }}</p>
      @if (missing().length) {
        <p class="codes">
          <span>{{ t('locked.required') }}</span>
          @for (code of missing(); track code) {
            <code>{{ code }}</code>
          }
        </p>
      }
    </section>
  `,
  styles: `
    .locked {
      border: 1px dashed var(--p-surface-400);
      border-radius: var(--p-border-radius-md, 6px);
      padding: 2rem 1.5rem;
      text-align: center;
      color: var(--p-text-muted-color);
      background: var(--p-surface-50);
      min-height: 160px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 0.35rem;
    }
    i { font-size: 1.75rem; }
    h3 { margin: 0.25rem 0 0; color: var(--p-text-color); font-size: 1.05rem; }
    p { margin: 0; }
    .hint { font-size: 0.9rem; }
    .codes { margin-top: 0.5rem; font-size: 0.8rem; display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; }
    code { background: var(--p-surface-200); padding: 0 0.35rem; border-radius: 3px; }
  `,
})
export class LockedPanelComponent {
  readonly missing = input<string[]>([]);
  readonly title = input<string>('');
}
