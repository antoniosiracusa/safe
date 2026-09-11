import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { ProgressBarModule } from 'primeng/progressbar';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { CompanyKeyInfo, KeyStoreService } from '../../core/crypto/key-store.service';
import { normalizeRecoveryCode } from '../../core/crypto/sodium';
import { SessionService } from '../../core/session/session.service';
import { KeyDialogComponent } from '../../layout/key-dialog/key-dialog.component';

interface GrantRow {
  id: string;
  user: { id: string; email: string; name: string; status: string };
  key_version: number;
  granted_by: string | null;
  created_at: string;
}
interface GrantsResponse {
  key: CompanyKeyInfo | null;
  grants: GrantRow[];
  candidates: { id: string; email: string; name: string }[];
}

/** Gestione · Chiavi di cifratura: stato, custodi, inizializzazione, rotazione, recupero. */
@Component({
  selector: 'safe-admin-keys',
  imports: [
    DatePipe, FormsModule, TranslocoDirective, ButtonModule, CheckboxModule, ConfirmDialogModule, DialogModule, ProgressBarModule,
    SelectModule, TableModule, TagModule, TextareaModule, ToastModule, TooltipModule, CanDirective, KeyDialogComponent,
  ],
  providers: [MessageService, ConfirmationService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  templateUrl: './keys-page.component.html',
})
export class KeysPageComponent {
  readonly session = inject(SessionService);
  readonly store = inject(KeyStoreService);
  private readonly api = inject(ApiService);
  private readonly messages = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly transloco = inject(TranslocoService);

  readonly data = signal<GrantsResponse | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly keyDialog = signal(false);
  readonly grantTo = signal<string | null>(null);
  readonly busy = signal<string | null>(null);

  /** wizard: parole di recupero mostrate una sola volta */
  readonly words = signal<string[] | null>(null);
  readonly wordsConfirmed = signal(false);
  readonly wordsTitle = signal('');
  readonly recoveryInput = signal('');
  readonly recoveryDialog = signal(false);
  readonly progress = signal<{ done: number; total: number } | null>(null);

  constructor() {
    void this.reload();
  }

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      await this.store.ensureLoaded();
      if (this.session.can('crypto.manage_keys')) this.data.set(await firstValueFrom(this.api.get<GrantsResponse>('crypto/grants')));
    } catch (err) {
      this.error.set(errorMessage(err, this.transloco.translate('common.load_error')));
    } finally {
      this.loading.set(false);
    }
  }

  private ensureUnlocked(): boolean {
    if (this.store.unlocked()) return true;
    this.keyDialog.set(true);
    return false;
  }

  async init(): Promise<void> {
    if (!this.ensureUnlocked()) return;
    this.busy.set('init');
    try {
      const words = await this.store.initCompanyKey();
      this.showWords(words, this.transloco.translate('keys.init_done'));
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.busy.set(null);
    }
  }

  async grant(): Promise<void> {
    const uid = this.grantTo();
    if (!uid || !this.ensureUnlocked()) return;
    if (!this.store.activeCompanyKeyPair()) {
      this.messages.add({ severity: 'warn', summary: this.transloco.translate('keys.need_grant_self') });
      return;
    }
    this.busy.set('grant');
    try {
      await this.store.grant(uid);
      this.grantTo.set(null);
      this.messages.add({ severity: 'success', summary: this.transloco.translate('keys.granted') });
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.busy.set(null);
    }
  }

  revoke(g: GrantRow): void {
    this.confirm.confirm({
      message: this.transloco.translate('keys.revoke_confirm', { email: g.user.email }),
      header: this.transloco.translate('keys.revoke'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('keys.revoke'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: async () => {
        try {
          await firstValueFrom(this.api.delete(`crypto/grants/${g.user.id}`));
          await this.reload();
        } catch (err) {
          this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
        }
      },
    });
  }

  rotate(): void {
    if (!this.ensureUnlocked()) return;
    if (!this.store.activeCompanyKeyPair()) {
      this.messages.add({ severity: 'warn', summary: this.transloco.translate('keys.need_grant_self') });
      return;
    }
    this.confirm.confirm({
      message: this.transloco.translate('keys.rotate_confirm'),
      header: this.transloco.translate('keys.rotate'),
      icon: 'pi pi-refresh',
      acceptButtonProps: { label: this.transloco.translate('keys.rotate') },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: async () => {
        this.busy.set('rotate');
        this.progress.set({ done: 0, total: 0 });
        try {
          const words = await this.store.rotate((done, total) => this.progress.set({ done, total }));
          this.showWords(words, this.transloco.translate('keys.rotate_done'));
          await this.reload();
        } catch (err) {
          this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
        } finally {
          this.busy.set(null);
          this.progress.set(null);
        }
      },
    });
  }

  async recover(): Promise<void> {
    const code = normalizeRecoveryCode(this.recoveryInput());
    if (!code) {
      this.messages.add({ severity: 'error', summary: this.transloco.translate('keys.recovery_invalid') });
      return;
    }
    if (!this.ensureUnlocked()) return;
    this.busy.set('recover');
    try {
      const words = await this.store.recover(code);
      this.recoveryDialog.set(false);
      this.recoveryInput.set('');
      this.showWords(words, this.transloco.translate('keys.recover_done'));
      await this.reload();
    } catch (err) {
      const msg = err instanceof Error && err.message === 'bad_recovery_code' ? this.transloco.translate('keys.recovery_wrong') : errorMessage(err, this.transloco.translate('common.save_error'));
      this.messages.add({ severity: 'error', summary: msg });
    } finally {
      this.busy.set(null);
    }
  }

  private showWords(words: string[], title: string): void {
    this.wordsTitle.set(title);
    this.wordsConfirmed.set(false);
    this.words.set(words);
  }

  percent(p: { done: number; total: number }): number {
    return p.total ? Math.round((p.done / p.total) * 100) : 100;
  }

  wordsText(): string {
    return (this.words() ?? []).map((w, i) => `${i + 1}. ${w}`).join('\n');
  }

  async copyWords(): Promise<void> {
    try {
      await navigator.clipboard.writeText((this.words() ?? []).join(' '));
      this.messages.add({ severity: 'info', summary: this.transloco.translate('keys.copied') });
    } catch {
      /* clipboard non disponibile */
    }
  }
}
