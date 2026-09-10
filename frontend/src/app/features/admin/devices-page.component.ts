import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { Device, DeviceStatus, EnrollmentCode } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { SessionService } from '../../core/session/session.service';

@Component({
  selector: 'safe-admin-devices',
  imports: [
    DatePipe, FormsModule, TranslocoDirective, ButtonModule, ConfirmDialogModule, DialogModule, InputTextModule, TableModule, TagModule,
    ToastModule, TooltipModule, CanDirective,
  ],
  providers: [MessageService, ConfirmationService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  template: `
    <ng-container *transloco="let t">
      <p-toast />
      <p-confirmDialog />
      <div class="page-head">
        <h1>{{ t('nav.devices') }}</h1>
        <ng-container *safeCan="'devices.manage'; mode: 'hide'">
          <p-button [label]="t('admin.new_enrollment')" icon="pi pi-qrcode" (onClick)="newCode()" [loading]="codeLoading()" />
        </ng-container>
      </div>
      <p class="intro">{{ t('admin.devices_intro') }}</p>
      <ng-container *safeCan="'devices.view'">
        <div class="kpis">
          @for (s of statuses; track s) {
            <button type="button" class="kpi" [class.active]="filter() === s" (click)="filter.set(filter() === s ? null : s)">
              <span class="label">{{ t('admin.device_' + s) }}</span><span class="value">{{ summary()[s] ?? 0 }}</span>
            </button>
          }
        </div>
        @if (error()) { <p class="error-box" role="alert">{{ t('common.load_error') }}</p> }
        <div class="table-wrap">
          <p-table [value]="rows()" [loading]="loading()" styleClass="p-datatable-sm" dataKey="id" [tableStyle]="{ 'min-width': '860px' }">
            <ng-template #header>
              <tr>
                <th>{{ t('admin.device') }}</th>
                <th>{{ t('admin.user') }}</th>
                <th>{{ t('admin.platform') }}</th>
                <th>{{ t('admin.app_version') }}</th>
                <th>{{ t('admin.enrolled_at') }}</th>
                <th>{{ t('admin.last_seen') }}</th>
                <th>{{ t('admin.state') }}</th>
                <th></th>
              </tr>
            </ng-template>
            <ng-template #body let-d>
              <tr>
                <td><b>{{ d.name }}</b></td>
                <td>{{ d.user.name || d.user.email }}<div class="muted">{{ d.user.email }}</div></td>
                <td>{{ d.platform === 'ios' ? 'iOS' : 'Android' }} <span class="muted">{{ d.os_version }}</span></td>
                <td>{{ d.app_version || '—' }}</td>
                <td>{{ d.enrolled_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>{{ d.last_seen_at ? (d.last_seen_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                <td><p-tag [value]="t('admin.device_' + d.status)" [severity]="severity(d.status)" /></td>
                <td class="actions-cell">
                  @if (d.status === 'pending' && session.can('devices.authorize')) {
                    <p-button icon="pi pi-check" [text]="true" size="small" severity="success" [loading]="busy() === d.id" (onClick)="authorize(d)" [pTooltip]="t('admin.authorize')" tooltipPosition="left" />
                  }
                  @if (d.status !== 'revoked' && session.can('devices.manage')) {
                    <p-button icon="pi pi-pencil" [text]="true" size="small" (onClick)="rename.set({ id: d.id, name: d.name })" [pTooltip]="t('admin.rename')" tooltipPosition="left" />
                    <p-button icon="pi pi-ban" [text]="true" size="small" severity="danger" [loading]="busy() === d.id" (onClick)="revoke(d)" [pTooltip]="t('admin.revoke')" tooltipPosition="left" />
                  }
                </td>
              </tr>
            </ng-template>
            <ng-template #emptymessage><tr><td colspan="8" class="empty">@if (!loading()) { {{ t('admin.no_devices') }} }</td></tr></ng-template>
          </p-table>
        </div>
      </ng-container>

      @if (code(); as c) {
        <p-dialog [visible]="true" (visibleChange)="code.set(null)" [modal]="true" [header]="t('admin.new_enrollment')" [style]="{ width: 'min(480px, 96vw)' }">
          <div class="qr">
            <img [src]="c.qr_svg" alt="QR" />
            <p class="muted" style="text-align: center">{{ t('admin.enrollment_hint', { minutes: 15 }) }}</p>
            <code>{{ c.code }}</code>
            <span class="muted">{{ t('admin.expires_at') }} {{ c.expires_at | date: 'HH:mm' }}</span>
          </div>
          <div class="dialog-actions">
            <p-button [label]="t('common.cancel')" severity="secondary" [text]="true" (onClick)="code.set(null)" />
          </div>
        </p-dialog>
      }
      @if (rename(); as r) {
        <p-dialog [visible]="true" (visibleChange)="rename.set(null)" [modal]="true" [header]="t('admin.rename')" [style]="{ width: 'min(420px, 96vw)' }">
          <div class="dialog-form">
            <div class="field span-2">
              <label for="dv-name">{{ t('admin.device') }}</label>
              <input pInputText id="dv-name" [ngModel]="r.name" (ngModelChange)="patchRename($event)" maxlength="120" />
            </div>
          </div>
          <div class="dialog-actions">
            <p-button [label]="t('common.cancel')" severity="secondary" [text]="true" (onClick)="rename.set(null)" />
            <p-button [label]="t('common.save')" icon="pi pi-check" [disabled]="!r.name.trim()" (onClick)="saveRename()" />
          </div>
        </p-dialog>
      }
    </ng-container>
  `,
})
export class DevicesPageComponent {
  readonly session = inject(SessionService);
  private readonly admin = inject(AdminService);
  private readonly messages = inject(MessageService);
  private readonly confirm = inject(ConfirmationService);
  private readonly transloco = inject(TranslocoService);

  readonly statuses: DeviceStatus[] = ['pending', 'authorized', 'revoked'];
  readonly devices = signal<Device[]>([]);
  readonly summary = signal<Record<string, number>>({});
  readonly filter = signal<DeviceStatus | null>(null);
  readonly rows = computed(() => this.devices().filter((d) => !this.filter() || d.status === this.filter()));
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly busy = signal<string | null>(null);
  readonly code = signal<EnrollmentCode | null>(null);
  readonly codeLoading = signal(false);
  readonly rename = signal<{ id: string; name: string } | null>(null);

  constructor() {
    void this.reload();
  }

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(false);
    try {
      const [devices, summary] = await Promise.all([firstValueFrom(this.admin.devices()), firstValueFrom(this.admin.deviceSummary())]);
      this.devices.set(devices);
      this.summary.set(summary);
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  async newCode(): Promise<void> {
    this.codeLoading.set(true);
    try {
      this.code.set(await firstValueFrom(this.admin.enrollmentCode()));
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.codeLoading.set(false);
    }
  }

  async authorize(d: Device): Promise<void> {
    await this.run(d.id, this.admin.authorizeDevice(d.id));
  }

  revoke(d: Device): void {
    this.confirm.confirm({
      message: this.transloco.translate('admin.revoke_confirm', { name: d.name }),
      header: this.transloco.translate('admin.revoke'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('admin.revoke'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => void this.run(d.id, this.admin.revokeDevice(d.id)),
    });
  }

  patchRename(name: string): void {
    const r = this.rename();
    if (r) this.rename.set({ ...r, name });
  }

  async saveRename(): Promise<void> {
    const r = this.rename();
    if (!r) return;
    this.rename.set(null);
    await this.run(r.id, this.admin.renameDevice(r.id, r.name.trim()));
  }

  private async run(id: string, op: import('rxjs').Observable<unknown>): Promise<void> {
    this.busy.set(id);
    try {
      await firstValueFrom(op);
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.busy.set(null);
    }
  }

  severity(s: DeviceStatus): 'success' | 'warn' | 'danger' {
    return s === 'authorized' ? 'success' : s === 'pending' ? 'warn' : 'danger';
  }
}
