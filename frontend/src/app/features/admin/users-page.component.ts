import { DatePipe, UpperCasePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';
import { SelectButtonModule } from 'primeng/selectbutton';
import { TableModule } from 'primeng/table';
import { TabsModule } from 'primeng/tabs';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { AdminUser, Role, TeamAdmin, UserStatus } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { SessionService } from '../../core/session/session.service';

type Effect = 'inherit' | 'grant' | 'deny';

interface UserForm {
  id: string | null;
  email: string;
  first_name: string;
  last_name: string;
  locale: string;
  mfa_required: boolean;
  teams: string[];
  default_team: string | null;
  roles: string[];
  effects: Record<string, Effect>;
}

/** Gestione utenti: attivi / invitati / disattivati, invito via email (Keycloak), squadre, ruoli e permessi. */
@Component({
  selector: 'safe-admin-users',
  imports: [
    DatePipe, UpperCasePipe, FormsModule, TranslocoDirective, ButtonModule, CheckboxModule, ConfirmDialogModule, DialogModule, InputTextModule,
    MultiSelectModule, SelectModule, SelectButtonModule, TableModule, TabsModule, TagModule, ToastModule, TooltipModule, CanDirective,
  ],
  providers: [MessageService, ConfirmationService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  templateUrl: './users-page.component.html',
})
export class UsersPageComponent {
  readonly session = inject(SessionService);
  private readonly admin = inject(AdminService);
  private readonly messages = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly transloco = inject(TranslocoService);

  readonly users = signal<AdminUser[]>([]);
  readonly roles = signal<Role[]>([]);
  readonly teams = signal<TeamAdmin[]>([]);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly tab = signal<UserStatus>('active');
  readonly search = signal('');

  readonly counts = computed(() => {
    const c = { active: 0, invited: 0, disabled: 0 };
    for (const u of this.users()) c[u.status]++;
    return c;
  });
  readonly rows = computed(() => {
    const q = this.search().trim().toLowerCase();
    return this.users().filter(
      (u) => u.status === this.tab() && (!q || u.email.includes(q) || u.full_name.toLowerCase().includes(q)),
    );
  });
  readonly teamOptions = computed(() => this.teams().filter((t) => t.is_active).map((t) => ({ value: t.id, label: t.name })));
  readonly roleOptions = computed(() => {
    const lang = this.transloco.getActiveLang();
    return this.roles().map((r) => ({ value: r.code, label: (r as unknown as Record<string, string>)[`name_${lang}`] || r.name_it }));
  });
  readonly localeOptions = [
    { value: 'it', label: 'IT' },
    { value: 'en', label: 'EN' },
    { value: 'de', label: 'DE' },
  ];
  readonly effectOptions = computed(() => [
    { value: 'inherit', label: this.transloco.translate('admin.effect_inherit') },
    { value: 'grant', label: this.transloco.translate('admin.effect_grant') },
    { value: 'deny', label: this.transloco.translate('admin.effect_deny') },
  ]);
  /** Tutti i codici di permesso assegnabili, raggruppati per modulo (prefisso). */
  readonly permissionGroups = computed(() => {
    const codes = Object.keys(this.session.permissions()).filter((c) => c !== 'platform.admin' && c !== 'crypto.holder');
    const groups = new Map<string, string[]>();
    for (const c of codes.sort()) {
      const mod = c.split('.')[0];
      groups.set(mod, [...(groups.get(mod) ?? []), c]);
    }
    return [...groups.entries()].map(([module, perms]) => ({ module, perms }));
  });

  readonly dialog = signal<UserForm | null>(null);
  readonly saving = signal(false);
  readonly dialogError = signal<string | null>(null);
  readonly busy = signal<string | null>(null);

  /** Permessi ereditati dai ruoli selezionati nel dialogo (sola lettura). */
  readonly inherited = computed(() => {
    const d = this.dialog();
    if (!d) return new Set<string>();
    const set = new Set<string>();
    for (const r of this.roles()) if (d.roles.includes(r.code)) r.permissions.forEach((p) => set.add(p));
    return set;
  });

  constructor() {
    void this.reload();
  }

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(false);
    try {
      const [users, roles, teams] = await Promise.all([
        firstValueFrom(this.admin.users()),
        firstValueFrom(this.admin.roles()),
        firstValueFrom(this.admin.teams()),
      ]);
      this.users.set(users);
      this.roles.set(roles);
      this.teams.set(teams);
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  openInvite(): void {
    this.dialogError.set(null);
    this.dialog.set({
      id: null, email: '', first_name: '', last_name: '', locale: this.session.company()?.timezone ? 'it' : 'it',
      mfa_required: false, teams: [], default_team: null, roles: ['rescuer'], effects: {},
    });
  }

  openEdit(u: AdminUser): void {
    this.dialogError.set(null);
    const effects: Record<string, Effect> = {};
    u.grants.forEach((c) => (effects[c] = 'grant'));
    u.denies.forEach((c) => (effects[c] = 'deny'));
    this.dialog.set({
      id: u.id, email: u.email, first_name: u.first_name, last_name: u.last_name, locale: u.locale, mfa_required: u.mfa_required,
      teams: u.teams.map((t) => t.id), default_team: u.teams.find((t) => t.is_default)?.id ?? null, roles: [...u.roles], effects,
    });
  }

  patchDialog(patch: Partial<UserForm>): void {
    const d = this.dialog();
    if (d) this.dialog.set({ ...d, ...patch });
  }

  setEffect(code: string, effect: Effect): void {
    const d = this.dialog();
    if (!d) return;
    const effects = { ...d.effects };
    if (effect === 'inherit') delete effects[code];
    else effects[code] = effect;
    this.dialog.set({ ...d, effects });
  }

  effectOf(code: string): Effect {
    return this.dialog()?.effects[code] ?? 'inherit';
  }

  async save(): Promise<void> {
    const d = this.dialog();
    if (!d || this.saving()) return;
    this.saving.set(true);
    this.dialogError.set(null);
    const grants = Object.entries(d.effects).filter(([, e]) => e === 'grant').map(([c]) => c);
    const denies = Object.entries(d.effects).filter(([, e]) => e === 'deny').map(([c]) => c);
    const defaultTeam = d.default_team && d.teams.includes(d.default_team) ? d.default_team : d.teams[0] ?? null;
    try {
      if (d.id === null) {
        const created = await firstValueFrom(
          this.admin.invite({
            email: d.email.trim(), first_name: d.first_name.trim(), last_name: d.last_name.trim(), locale: d.locale,
            teams: d.teams, default_team: defaultTeam, roles: d.roles, mfa_required: d.mfa_required,
          }),
        );
        if (grants.length || denies.length) {
          await firstValueFrom(this.admin.putPermissions(created.id, { roles: d.roles, grants, denies }));
        }
        this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.invite_sent', { email: created.email }) });
      } else {
        const canManage = this.session.can('users.manage');
        const canAssign = this.session.can('users.assign_permissions');
        if (canManage) {
          await firstValueFrom(
            this.admin.patchUser(d.id, {
              first_name: d.first_name.trim(), last_name: d.last_name.trim(), locale: d.locale, mfa_required: d.mfa_required,
              teams: d.teams, default_team: defaultTeam,
            }),
          );
        }
        if (canAssign) await firstValueFrom(this.admin.putPermissions(d.id, { roles: d.roles, grants, denies }));
        this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
        if (d.id === this.session.user()?.id) void this.session.reload();
      }
      this.dialog.set(null);
      await this.reload();
    } catch (err) {
      this.dialogError.set(errorMessage(err, this.transloco.translate('common.save_error')));
    } finally {
      this.saving.set(false);
    }
  }

  async resend(u: AdminUser): Promise<void> {
    await this.run(u.id, this.admin.resendInvite(u.id), 'admin.invite_sent', { email: u.email });
  }

  disable(u: AdminUser): void {
    this.confirm.confirm({
      message: this.transloco.translate('admin.disable_confirm', { email: u.email }),
      header: this.transloco.translate('admin.disable'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('admin.disable'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => void this.run(u.id, this.admin.disableUser(u.id), 'admin.disabled_ok'),
    });
  }

  async enable(u: AdminUser): Promise<void> {
    await this.run(u.id, this.admin.enableUser(u.id), 'admin.enabled_ok');
  }

  private async run(id: string, op: Promise<unknown> | import('rxjs').Observable<unknown>, okKey: string, params?: Record<string, string>): Promise<void> {
    this.busy.set(id);
    try {
      await (op instanceof Promise ? op : firstValueFrom(op));
      this.messages.add({ severity: 'success', summary: this.transloco.translate(okKey, params) });
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.busy.set(null);
    }
  }

  roleLabel(code: string): string {
    return this.roleOptions().find((r) => r.value === code)?.label ?? code;
  }

  statusSeverity(s: UserStatus): 'success' | 'warn' | 'danger' {
    return s === 'active' ? 'success' : s === 'invited' ? 'warn' : 'danger';
  }
}
