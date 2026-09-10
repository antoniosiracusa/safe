import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { TeamAdmin } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { LookupLabelPipe } from '../../core/lookups/lookup-label.pipe';
import { LookupsService } from '../../core/lookups/lookups.service';
import { SessionService } from '../../core/session/session.service';

@Component({
  selector: 'safe-admin-teams',
  imports: [
    FormsModule, TranslocoDirective, ButtonModule, ConfirmDialogModule, DialogModule, InputTextModule, SelectModule, TableModule,
    TagModule, ToastModule, TooltipModule, CanDirective, LookupLabelPipe,
  ],
  providers: [MessageService, ConfirmationService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  template: `
    <ng-container *transloco="let t">
      <p-toast />
      <p-confirmDialog />
      <div class="page-head">
        <h1>{{ t('nav.teams') }}</h1>
        <ng-container *safeCan="'teams.manage'; mode: 'hide'">
          <p-button [label]="t('admin.new_team')" icon="pi pi-plus" (onClick)="open(null)" />
        </ng-container>
      </div>
      <p class="intro">{{ t('admin.teams_intro') }}</p>
      <ng-container *safeCan="'teams.view'">
        @if (error()) { <p class="error-box" role="alert">{{ t('common.load_error') }}</p> }
        <div class="table-wrap">
          <p-table [value]="teams()" [loading]="loading()" styleClass="p-datatable-sm" dataKey="id">
            <ng-template #header>
              <tr>
                <th>{{ t('admin.team_name') }}</th>
                <th>{{ t('admin.team_body') }}</th>
                <th class="num">{{ t('nav.users') }}</th>
                <th class="num">{{ t('nav.events') }}</th>
                <th>{{ t('admin.state') }}</th>
                <th></th>
              </tr>
            </ng-template>
            <ng-template #body let-tm>
              <tr [class.inactive]="!tm.is_active">
                <td><b>{{ tm.name }}</b></td>
                <td>{{ tm.body | lookup: 'team_body' }}</td>
                <td class="num">{{ tm.users_count }}</td>
                <td class="num">{{ tm.events_count }}</td>
                <td><p-tag [value]="tm.is_active ? t('admin.active') : t('admin.inactive')" [severity]="tm.is_active ? 'success' : 'secondary'" /></td>
                <td class="actions-cell">
                  <ng-container *safeCan="'teams.manage'; mode: 'hide'">
                    <p-button icon="pi pi-pencil" [text]="true" size="small" (onClick)="open(tm)" [pTooltip]="t('common.edit')" tooltipPosition="left" />
                    @if (tm.is_active) {
                      <p-button icon="pi pi-ban" [text]="true" size="small" severity="danger" [disabled]="tm.events_count > 0" (onClick)="deactivate(tm)" [pTooltip]="tm.events_count > 0 ? t('admin.team_has_events') : t('admin.deactivate')" tooltipPosition="left" />
                    } @else {
                      <p-button icon="pi pi-check-circle" [text]="true" size="small" severity="success" (onClick)="reactivate(tm)" [pTooltip]="t('admin.reactivate')" tooltipPosition="left" />
                    }
                  </ng-container>
                </td>
              </tr>
            </ng-template>
            <ng-template #emptymessage><tr><td colspan="6" class="empty">@if (!loading()) { {{ t('admin.no_teams') }} }</td></tr></ng-template>
          </p-table>
        </div>
      </ng-container>

      @if (dialog(); as d) {
        <p-dialog [visible]="true" (visibleChange)="dialog.set(null)" [modal]="true" [header]="d.id ? t('common.edit') : t('admin.new_team')" [style]="{ width: 'min(520px, 96vw)' }">
          @if (dialogError(); as e) { <p class="error-box" role="alert">{{ e }}</p> }
          <div class="dialog-form">
            <div class="field span-2">
              <label for="td-name">{{ t('admin.team_name') }} *</label>
              <input pInputText id="td-name" [ngModel]="d.name" (ngModelChange)="patch({ name: $event })" maxlength="120" />
            </div>
            <div class="field span-2">
              <label for="td-body">{{ t('admin.team_body') }}</label>
              <p-select inputId="td-body" [options]="lookups.options('team_body')" optionLabel="label" optionValue="value" [ngModel]="d.body" (ngModelChange)="patch({ body: $event })" [showClear]="true" appendTo="body" styleClass="w-full" />
            </div>
          </div>
          <div class="dialog-actions">
            <p-button [label]="t('common.cancel')" severity="secondary" [text]="true" (onClick)="dialog.set(null)" />
            <p-button [label]="t('common.save')" icon="pi pi-check" [loading]="saving()" [disabled]="!d.name.trim()" (onClick)="save()" />
          </div>
        </p-dialog>
      }
    </ng-container>
  `,
})
export class TeamsPageComponent {
  readonly session = inject(SessionService);
  readonly lookups = inject(LookupsService);
  private readonly admin = inject(AdminService);
  private readonly filterOptions = inject(FilterOptionsService);
  private readonly messages = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly transloco = inject(TranslocoService);

  readonly teams = signal<TeamAdmin[]>([]);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly dialog = signal<{ id: string | null; name: string; body: string | null } | null>(null);
  readonly dialogError = signal<string | null>(null);
  readonly saving = signal(false);

  constructor() {
    void this.lookups.load();
    void this.reload();
  }

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(false);
    try {
      this.teams.set(await firstValueFrom(this.admin.teams()));
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  patch(p: Partial<{ name: string; body: string | null }>): void {
    const d = this.dialog();
    if (d) this.dialog.set({ ...d, ...p });
  }

  open(tm: TeamAdmin | null): void {
    this.dialogError.set(null);
    this.dialog.set(tm ? { id: tm.id, name: tm.name, body: tm.body } : { id: null, name: '', body: null });
  }

  async save(): Promise<void> {
    const d = this.dialog();
    if (!d) return;
    this.saving.set(true);
    this.dialogError.set(null);
    try {
      const body = { name: d.name.trim(), body: d.body };
      await firstValueFrom(d.id ? this.admin.patchTeam(d.id, body) : this.admin.createTeam(body));
      this.dialog.set(null);
      this.filterOptions.invalidate();
      this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
      await this.reload();
    } catch (err) {
      this.dialogError.set(errorMessage(err, this.transloco.translate('common.save_error')));
    } finally {
      this.saving.set(false);
    }
  }

  deactivate(tm: TeamAdmin): void {
    this.confirm.confirm({
      message: this.transloco.translate('admin.deactivate_team_confirm', { name: tm.name }),
      header: this.transloco.translate('admin.deactivate'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('admin.deactivate'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => void this.change(this.admin.deactivateTeam(tm.id)),
    });
  }

  reactivate(tm: TeamAdmin): void {
    void this.change(this.admin.patchTeam(tm.id, { is_active: true }));
  }

  private async change(op: import('rxjs').Observable<unknown>): Promise<void> {
    try {
      await firstValueFrom(op);
      this.filterOptions.invalidate();
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    }
  }
}
