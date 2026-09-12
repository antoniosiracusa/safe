import { Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';

import { PwaService } from '../../core/pwa/pwa.service';

/** Senza rete e senza una sessione valida non si può accedere: si attende la connessione (M8.2). */
@Component({
  selector: 'safe-offline',
  imports: [TranslocoDirective, ButtonModule],
  template: `
    <div class="box" *transloco="let t">
      <i class="pi pi-wifi" aria-hidden="true"></i>
      <h1>{{ t('pwa.offline_login_title') }}</h1>
      <p>{{ t('pwa.offline_login_text') }}</p>
      <p-button [label]="t('pwa.offline_retry')" icon="pi pi-refresh" [disabled]="!pwa.online()" (onClick)="retry()" />
    </div>
  `,
  styles: `
    .box { max-width: 420px; margin: 15vh auto; text-align: center; padding: 1.5rem; }
    i { font-size: 2.5rem; color: #c8102e; }
    h1 { font-size: 1.3rem; margin: 0.75rem 0 0.5rem; }
    p { color: var(--p-text-muted-color); margin-bottom: 1.25rem; }
  `,
})
export class OfflinePageComponent {
  readonly pwa = inject(PwaService);

  retry(): void {
    window.location.href = '/';
  }
}
