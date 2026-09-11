import { DatePipe, SlicePipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DatePickerModule } from 'primeng/datepicker';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableLazyLoadEvent, TableModule } from 'primeng/table';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { AdminUser } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { ApiService, Paginated } from '../../core/api/api.service';
import { JobsService } from '../../core/api/jobs.service';
import { CanDirective } from '../../core/authz/can.directive';
import { SessionService } from '../../core/session/session.service';

interface AuditRow {
  id: number;
  created_at: string;
  actor_user_id: string | null;
  actor: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  event_id: string | null;
  changed_fields: string[];
  metadata: Record<string, unknown>;
  ip: string | null;
}

const PAGE = 50;

/** Gestione · Audit log: chi ha fatto cosa e quando (mai valori di dati personali). */
@Component({
  selector: 'safe-admin-audit',
  imports: [DatePipe, SlicePipe, FormsModule, TranslocoDirective, ButtonModule, DatePickerModule, InputTextModule, SelectModule, TableModule, ToastModule, TooltipModule, CanDirective],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  template: `
    <ng-container *transloco="let t">
      <p-toast />
      <div class="page-head">
        <h1>{{ t('nav.audit') }}</h1>
        <div class="head-actions">
          <p-button [label]="t('audit.export')" icon="pi pi-download" [outlined]="true" size="small" [loading]="exporting()" (onClick)="exportCsv()" />
        </div>
      </div>
      <p class="intro">{{ t('audit.intro') }}</p>
      <ng-container *safeCan="'audit.view'">
        <form class="toolbar" (submit)="$event.preventDefault(); reload(true)">
          <div class="field">
            <label for="au-action">{{ t('audit.action') }}</label>
            <p-select inputId="au-action" [options]="actions()" [ngModel]="action()" (ngModelChange)="action.set($event); reload(true)" name="action" [placeholder]="t('filters.all')" [showClear]="true" [filter]="true" [editable]="true" appendTo="body" styleClass="w-full" />
          </div>
          <div class="field">
            <label for="au-actor">{{ t('admin.user') }}</label>
            <p-select inputId="au-actor" [options]="users()" optionLabel="email" optionValue="id" [ngModel]="actor()" (ngModelChange)="actor.set($event); reload(true)" name="actor" [placeholder]="t('filters.all')" [showClear]="true" [filter]="true" appendTo="body" styleClass="w-full" />
          </div>
          <div class="field">
            <label for="au-from">{{ t('filters.from') }}</label>
            <p-datePicker inputId="au-from" [ngModel]="from()" (ngModelChange)="from.set($event); reload(true)" name="from" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body" styleClass="w-full" />
          </div>
          <div class="field">
            <label for="au-to">{{ t('filters.to') }}</label>
            <p-datePicker inputId="au-to" [ngModel]="to()" (ngModelChange)="to.set($event); reload(true)" name="to" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body" styleClass="w-full" />
          </div>
          <div class="field">
            <label for="au-obj">{{ t('audit.object_id') }}</label>
            <input pInputText id="au-obj" [ngModel]="objectId()" (ngModelChange)="objectId.set($event)" name="object" placeholder="uuid" />
          </div>
          <p-button type="submit" icon="pi pi-search" [text]="true" [attr.aria-label]="t('common.search')" />
        </form>
        @if (error()) { <p class="error-box" role="alert">{{ t('common.load_error') }}</p> }
        <div class="table-wrap">
          <p-table [value]="rows()" [lazy]="true" (onLazyLoad)="onLazyLoad($event)" [paginator]="true" [rows]="pageSize" [totalRecords]="total()" [first]="first()" [loading]="loading()" [scrollable]="true" scrollHeight="flex" styleClass="p-datatable-sm" [tableStyle]="{ 'min-width': '1000px' }" [showCurrentPageReport]="true" [currentPageReportTemplate]="t('common.page_report')">
            <ng-template #header>
              <tr>
                <th>{{ t('audit.when') }}</th>
                <th>{{ t('admin.user') }}</th>
                <th>{{ t('audit.action') }}</th>
                <th>{{ t('audit.object') }}</th>
                <th>{{ t('audit.details') }}</th>
                <th>IP</th>
              </tr>
            </ng-template>
            <ng-template #body let-r>
              <tr>
                <td>{{ r.created_at | date: 'dd/MM/yyyy HH:mm:ss' }}</td>
                <td>{{ r.actor || (r.actor_user_id ? shortId(r.actor_user_id) : '—') }}</td>
                <td><code>{{ r.action }}</code></td>
                <td>{{ r.object_type }} @if (r.object_id) { <code>{{ shortId(r.object_id) }}</code> } @if (r.event_id && r.event_id !== r.object_id) { <span class="muted">· {{ t('fields.event') }} <code>{{ shortId(r.event_id) }}</code></span> }</td>
                <td class="muted">@if (r.changed_fields?.length) { {{ r.changed_fields.join(', ') }} } @if (hasMeta(r)) { <span [pTooltip]="metaText(r)" tooltipPosition="left">{{ metaText(r) | slice: 0 : 80 }}</span> }</td>
                <td>{{ r.ip || '—' }}</td>
              </tr>
            </ng-template>
            <ng-template #emptymessage><tr><td colspan="6" class="empty">@if (!loading()) { — }</td></tr></ng-template>
          </p-table>
        </div>
      </ng-container>
    </ng-container>
  `,
})
export class AuditPageComponent {
  readonly session = inject(SessionService);
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);
  private readonly admin = inject(AdminService);
  private readonly jobs = inject(JobsService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  readonly rows = signal<AuditRow[]>([]);
  readonly total = signal(0);
  readonly first = signal(0);
  readonly pageSize = PAGE;
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly exporting = signal(false);
  readonly actions = signal<string[]>([]);
  readonly users = signal<AdminUser[]>([]);
  readonly action = signal<string | null>(null);
  readonly actor = signal<string | null>(null);
  readonly from = signal<Date | null>(null);
  readonly to = signal<Date | null>(null);
  readonly objectId = signal('');
  private version = 0;

  constructor() {
    void firstValueFrom(this.api.get<string[]>('audit-logs/actions')).then((a) => this.actions.set(a)).catch(() => undefined);
    if (this.session.can('users.view')) void firstValueFrom(this.admin.users()).then((u) => this.users.set(u)).catch(() => undefined);
  }

  private params(): HttpParams {
    let p = new HttpParams();
    if (this.action()) p = p.set('action', this.action() as string);
    if (this.actor()) p = p.set('actor', this.actor() as string);
    if (this.from()) p = p.set('date_from', this.iso(this.from() as Date));
    if (this.to()) p = p.set('date_to', this.iso(this.to() as Date));
    const obj = this.objectId().trim();
    if (obj) p = p.set('object_id', obj);
    return p;
  }

  private iso(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  onLazyLoad(e: TableLazyLoadEvent): void {
    this.first.set(e.first ?? 0);
    this.reload(false);
  }

  reload(resetPage: boolean): void {
    if (resetPage) this.first.set(0);
    const v = ++this.version;
    this.loading.set(true);
    this.error.set(false);
    const page = Math.floor(this.first() / PAGE) + 1;
    this.api.get<Paginated<AuditRow>>('audit-logs', this.params().set('page', String(page)).set('page_size', String(PAGE))).subscribe({
      next: (res) => {
        if (v !== this.version) return;
        this.rows.set(res.results);
        this.total.set(res.count);
        this.loading.set(false);
      },
      error: () => {
        if (v !== this.version) return;
        this.loading.set(false);
        this.error.set(true);
      },
    });
  }

  async exportCsv(): Promise<void> {
    this.exporting.set(true);
    try {
      const blob = await firstValueFrom(this.http.get(this.api.url('audit-logs/export'), { params: this.params(), responseType: 'blob' }));
      this.jobs.saveBlob(blob, 'audit-log.csv');
    } catch {
      this.messages.add({ severity: 'error', summary: this.transloco.translate('common.load_error') });
    } finally {
      this.exporting.set(false);
    }
  }

  shortId(id: string): string {
    return id.slice(-8).toUpperCase();
  }

  hasMeta(r: AuditRow): boolean {
    return !!r.metadata && Object.keys(r.metadata).length > 0;
  }

  metaText(r: AuditRow): string {
    return Object.entries(r.metadata)
      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
      .join(' · ');
  }
}
