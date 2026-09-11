import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { PasswordModule } from 'primeng/password';

import { KeyStoreService } from '../../core/crypto/key-store.service';
import { cryptoErrorCode } from '../../core/crypto/sodium';
import { SessionService } from '../../core/session/session.service';

/** "La mia chiave": creazione (prima volta), sblocco con passphrase, cambio passphrase, blocco. */
@Component({
  selector: 'safe-key-dialog',
  imports: [FormsModule, TranslocoDirective, ButtonModule, DialogModule, PasswordModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      <p-dialog [visible]="visible()" (visibleChange)="close()" [modal]="true" [header]="t('keys.my_key')" [style]="{ width: 'min(480px, 96vw)' }" appendTo="body">
        @if (error(); as e) { <p class="error-box" role="alert">{{ t('keys.' + e) }}</p> }

        @if (mode() === 'create') {
          <p>{{ t('keys.create_intro') }}</p>
          <div class="field">
            <label for="kd-pass">{{ t('keys.passphrase') }}</label>
            <p-password inputId="kd-pass" [ngModel]="pass()" (ngModelChange)="pass.set($event)" [feedback]="true" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" [promptLabel]="t('keys.pass_prompt')" [weakLabel]="t('keys.pass_weak')" [mediumLabel]="t('keys.pass_medium')" [strongLabel]="t('keys.pass_strong')" />
          </div>
          <div class="field">
            <label for="kd-pass2">{{ t('keys.passphrase_repeat') }}</label>
            <p-password inputId="kd-pass2" [ngModel]="pass2()" (ngModelChange)="pass2.set($event)" [feedback]="false" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
          </div>
          <p class="muted">{{ t('keys.passphrase_hint') }}</p>
          <div class="actions">
            <p-button [label]="t('common.cancel')" [text]="true" severity="secondary" (onClick)="close()" />
            <p-button [label]="t('keys.create')" icon="pi pi-key" [loading]="store.busy()" [disabled]="pass().length < 12 || pass() !== pass2()" (onClick)="create()" />
          </div>
        } @else if (mode() === 'unlock') {
          <p>{{ t('keys.unlock_intro') }}</p>
          <div class="field">
            <label for="kd-unlock">{{ t('keys.passphrase') }}</label>
            <p-password inputId="kd-unlock" [ngModel]="pass()" (ngModelChange)="pass.set($event)" [feedback]="false" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" (keydown.enter)="unlock()" />
          </div>
          <div class="actions">
            <p-button [label]="t('keys.forgot')" [text]="true" severity="secondary" (onClick)="mode.set('reset')" />
            <p-button [label]="t('keys.unlock')" icon="pi pi-lock-open" [loading]="store.busy()" [disabled]="!pass()" (onClick)="unlock()" />
          </div>
        } @else if (mode() === 'reset') {
          <p class="warn">{{ t('keys.reset_intro') }}</p>
          <div class="field">
            <label for="kd-npass">{{ t('keys.new_passphrase') }}</label>
            <p-password inputId="kd-npass" [ngModel]="pass()" (ngModelChange)="pass.set($event)" [feedback]="true" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
          </div>
          <div class="field">
            <label for="kd-npass2">{{ t('keys.passphrase_repeat') }}</label>
            <p-password inputId="kd-npass2" [ngModel]="pass2()" (ngModelChange)="pass2.set($event)" [feedback]="false" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
          </div>
          <div class="actions">
            <p-button [label]="t('common.cancel')" [text]="true" severity="secondary" (onClick)="mode.set('unlock')" />
            <p-button [label]="t('keys.regenerate')" icon="pi pi-refresh" severity="danger" [loading]="store.busy()" [disabled]="pass().length < 12 || pass() !== pass2()" (onClick)="create()" />
          </div>
        } @else {
          <p><i class="pi pi-lock-open" style="color: var(--p-green-600)"></i> {{ t('keys.unlocked_status') }}</p>
          <p class="muted">{{ store.hasGrant() ? t('keys.grant_yes') : t('keys.grant_no') }}</p>
          <div class="field">
            <label for="kd-cpass">{{ t('keys.new_passphrase') }}</label>
            <p-password inputId="kd-cpass" [ngModel]="pass()" (ngModelChange)="pass.set($event)" [feedback]="true" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
          </div>
          <div class="actions">
            <p-button [label]="t('keys.lock')" icon="pi pi-lock" [text]="true" severity="secondary" (onClick)="lock()" />
            <p-button [label]="t('keys.change_passphrase')" icon="pi pi-check" [disabled]="pass().length < 12" [loading]="store.busy()" (onClick)="change()" />
          </div>
        }
      </p-dialog>
    </ng-container>
  `,
  styles: `
    .field { display: flex; flex-direction: column; gap: 0.25rem; margin: 0.75rem 0; }
    label { font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--p-text-muted-color); }
    .actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }
    .muted { color: var(--p-text-muted-color); font-size: 0.85rem; }
    .warn { color: var(--p-amber-800); background: var(--p-amber-50); border: 1px solid var(--p-amber-200); padding: 0.5rem 0.75rem; border-radius: 6px; }
    .error-box { padding: 0.5rem 0.75rem; border: 1px solid var(--p-red-300); border-radius: 6px; background: var(--p-red-50); color: var(--p-red-700); }
    :host ::ng-deep .w-full { width: 100%; }
  `,
})
export class KeyDialogComponent {
  readonly visible = input(false);
  readonly closed = output<void>();

  readonly store = inject(KeyStoreService);
  readonly session = inject(SessionService);
  private readonly transloco = inject(TranslocoService);

  readonly mode = signal<'create' | 'unlock' | 'reset' | 'manage'>('unlock');
  readonly pass = signal('');
  readonly pass2 = signal('');
  readonly error = signal<string | null>(null);
  readonly title = computed(() => this.transloco.translate('keys.my_key'));

  constructor() {
    effect(() => {
      if (!this.visible()) return;
      this.pass.set('');
      this.pass2.set('');
      this.error.set(null);
      void this.store.ensureLoaded().then(() => {
        if (!this.store.hasUserKey()) this.mode.set('create');
        else if (this.store.unlocked()) this.mode.set('manage');
        else this.mode.set('unlock');
      });
    });
  }

  async create(): Promise<void> {
    this.error.set(null);
    try {
      await this.store.createUserKey(this.pass());
      this.close();
    } catch (err) {
      console.error('createUserKey', err);
      this.error.set(cryptoErrorCode(err) ?? 'error_generic');
    }
  }

  async unlock(): Promise<void> {
    this.error.set(null);
    const ok = await this.store.unlock(this.pass());
    if (ok) this.close();
    else this.error.set('wrong_passphrase');
  }

  async change(): Promise<void> {
    this.error.set(null);
    try {
      await this.store.changePassphrase(this.pass());
      this.close();
    } catch {
      this.error.set('error_generic');
    }
  }

  lock(): void {
    this.store.lock();
    this.close();
  }

  close(): void {
    this.pass.set('');
    this.pass2.set('');
    this.closed.emit();
  }
}
