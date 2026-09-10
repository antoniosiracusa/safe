import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';

import { AuthService } from '../../core/auth/auth.service';

/** Utente autenticato dall'identity provider ma non invitato in alcuna società (o disattivato). */
@Component({
  selector: 'safe-not-provisioned',
  imports: [TranslocoDirective, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="wrap" *transloco="let t">
      <section class="box" role="alert">
        <i class="pi pi-user-minus" aria-hidden="true"></i>
        <h1>{{ t('not_provisioned.title') }}</h1>
        <p>{{ t('not_provisioned.message') }}</p>
        <p-button type="button" [label]="t('shell.logout')" icon="pi pi-sign-out" (onClick)="auth.logout()" />
      </section>
    </main>
  `,
  styles: `
    .wrap { min-height: 100vh; display: grid; place-items: center; background: var(--p-surface-100); padding: 1rem; }
    .box { background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-radius: 8px; padding: 2rem; max-width: 32rem; text-align: center; display: flex; flex-direction: column; gap: 0.75rem; align-items: center; }
    i { font-size: 2rem; color: #c8102e; }
    h1 { margin: 0; font-size: 1.3rem; }
    p { margin: 0; color: var(--p-text-muted-color); }
  `,
})
export class NotProvisionedComponent {
  readonly auth = inject(AuthService);
}
