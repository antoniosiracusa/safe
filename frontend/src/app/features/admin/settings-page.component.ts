import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectButtonModule } from 'primeng/selectbutton';
import { ToastModule } from 'primeng/toast';
import { firstValueFrom } from 'rxjs';

import { CompanyInfo, DUP_RULE_FIELDS, EVENT_RULE_FIELDS, PERSON_RULE_FIELDS } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { DatePipe } from '@angular/common';
import { CanDirective } from '../../core/authz/can.directive';
import { ApiService } from '../../core/api/api.service';
import { AsyncJob, JobsService } from '../../core/api/jobs.service';
import { SessionService } from '../../core/session/session.service';

interface RetentionStatus {
  retention_identity_years: number;
  retention_audit_years: number;
  identity_cutoff: string;
  persons_due: number;
  persons_anonymized_total: number;
  last_run: { at: string; persons_anonymized: number; audit_rows_purged: number } | null;
}

interface SettingsForm {
  name: string;
  timezone: string;
  default_locale: string;
  auto_lock_hours: number;
  devices_need_authorization: boolean;
  event_required: string[];
  person_required: string[];
  dup_minutes: number;
  dup_fields: string[];
}

@Component({
  selector: 'safe-admin-settings',
  imports: [DatePipe, FormsModule, TranslocoDirective, ButtonModule, CheckboxModule, InputNumberModule, InputTextModule, MultiSelectModule, SelectButtonModule, ToastModule, CanDirective],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  template: `
    <ng-container *transloco="let t">
      <p-toast />
      <div class="page-head"><h1>{{ t('nav.settings') }}</h1></div>
      <p class="intro">{{ t('admin.settings_intro') }}</p>
      <ng-container *safeCan="'company.settings'">
        @if (error()) { <p class="error-box" role="alert">{{ error() }}</p> }
        @if (form(); as f) {
          <section class="card">
            <h2>{{ t('admin.company') }}</h2>
            <div class="dialog-form" style="min-width: 0">
              <div class="field"><label for="st-name">{{ t('admin.company_name') }}</label><input pInputText id="st-name" [ngModel]="f.name" (ngModelChange)="patch({ name: $event })" maxlength="200" /></div>
              <div class="field"><label for="st-tz">{{ t('admin.timezone') }}</label><input pInputText id="st-tz" [ngModel]="f.timezone" (ngModelChange)="patch({ timezone: $event })" placeholder="Europe/Rome" /></div>
              <div class="field">
                <label for="st-locale">{{ t('admin.default_locale') }}</label>
                <p-selectButton inputId="st-locale" [options]="localeOptions" optionLabel="label" optionValue="value" [ngModel]="f.default_locale" (ngModelChange)="patch({ default_locale: $event })" [allowEmpty]="false" />
              </div>
              <div class="field"><span class="lbl">{{ t('admin.slug') }}</span><code>{{ company()?.slug }}</code> <span class="muted">{{ company()?.tenant_type }}</span></div>
            </div>
          </section>
          <section class="card">
            <h2>{{ t('admin.rules') }}</h2>
            <div class="dialog-form" style="min-width: 0">
              <div class="field">
                <label for="st-lock">{{ t('admin.auto_lock_hours') }}</label>
                <p-inputNumber inputId="st-lock" [ngModel]="f.auto_lock_hours" (ngModelChange)="patch({ auto_lock_hours: $event })" [min]="0" [max]="720" suffix=" h" styleClass="w-full" />
                <small class="muted">{{ t('admin.auto_lock_hint') }}</small>
              </div>
              <div class="field">
                <span class="lbl">&nbsp;</span>
                <div class="check">
                  <p-checkbox inputId="st-dev" [binary]="true" [ngModel]="f.devices_need_authorization" (ngModelChange)="patch({ devices_need_authorization: $event })" />
                  <label for="st-dev">{{ t('admin.devices_need_authorization') }}</label>
                </div>
              </div>
              <div class="field">
                <label for="st-evreq">{{ t('admin.event_required') }}</label>
                <p-multiSelect inputId="st-evreq" [options]="eventFieldOptions()" optionLabel="label" optionValue="value" [ngModel]="f.event_required" (ngModelChange)="patch({ event_required: $event })" appendTo="body" styleClass="w-full" [maxSelectedLabels]="3" [selectedItemsLabel]="t('filters.selected')" />
              </div>
              <div class="field">
                <label for="st-preq">{{ t('admin.person_required') }}</label>
                <p-multiSelect inputId="st-preq" [options]="personFieldOptions()" optionLabel="label" optionValue="value" [ngModel]="f.person_required" (ngModelChange)="patch({ person_required: $event })" appendTo="body" styleClass="w-full" [maxSelectedLabels]="3" [selectedItemsLabel]="t('filters.selected')" />
              </div>
              <div class="field">
                <label for="st-dupm">{{ t('admin.dup_minutes') }}</label>
                <p-inputNumber inputId="st-dupm" [ngModel]="f.dup_minutes" (ngModelChange)="patch({ dup_minutes: $event })" [min]="1" [max]="1440" suffix=" min" styleClass="w-full" />
              </div>
              <div class="field">
                <label for="st-dupf">{{ t('admin.dup_fields') }}</label>
                <p-multiSelect inputId="st-dupf" [options]="dupFieldOptions()" optionLabel="label" optionValue="value" [ngModel]="f.dup_fields" (ngModelChange)="patch({ dup_fields: $event })" appendTo="body" styleClass="w-full" [maxSelectedLabels]="3" [selectedItemsLabel]="t('filters.selected')" />
              </div>
            </div>
            <p class="muted" style="margin-top: 0.75rem">{{ t('admin.validity_hint') }}</p>
          </section>
          <ng-container *safeCan="'company.retention'; mode: 'hide'">
            <section class="card">
              <h2>{{ t('retention.title') }}</h2>
              <p class="muted">{{ t('retention.intro') }}</p>
              @if (retention(); as r) {
                <div class="dialog-form" style="min-width: 0">
                  <div class="field">
                    <label for="rt-id">{{ t('retention.identity_years') }}</label>
                    <p-inputNumber inputId="rt-id" [ngModel]="r.retention_identity_years" (ngModelChange)="patchRetention({ retention_identity_years: $event })" [min]="1" [max]="30" [suffix]="' ' + t('retention.years')" styleClass="w-full" />
                  </div>
                  <div class="field">
                    <label for="rt-au">{{ t('retention.audit_years') }}</label>
                    <p-inputNumber inputId="rt-au" [ngModel]="r.retention_audit_years" (ngModelChange)="patchRetention({ retention_audit_years: $event })" [min]="1" [max]="30" [suffix]="' ' + t('retention.years')" styleClass="w-full" />
                  </div>
                  <div class="field"><span class="lbl">{{ t('retention.due') }}</span><b>{{ r.persons_due }}</b> <span class="muted">{{ t('retention.due_hint', { date: (r.identity_cutoff | date: 'dd/MM/yyyy') }) }}</span></div>
                  <div class="field"><span class="lbl">{{ t('retention.last_run') }}</span>@if (r.last_run) { {{ r.last_run.at | date: 'dd/MM/yyyy HH:mm' }} · {{ r.last_run.persons_anonymized }} {{ t('retention.anonymized') }} } @else { — } <span class="muted">({{ r.persons_anonymized_total }} {{ t('retention.total_anonymized') }})</span></div>
                </div>
                <div class="actions" style="display: flex; gap: 0.5rem; margin-top: 0.75rem">
                  <p-button [label]="t('retention.save')" icon="pi pi-check" [outlined]="true" [loading]="retentionBusy() === 'save'" (onClick)="saveRetention()" />
                  <p-button [label]="t('retention.run_now')" icon="pi pi-play" severity="warn" [outlined]="true" [loading]="retentionBusy() === 'run'" [disabled]="!r.persons_due" (onClick)="runRetention()" />
                </div>
              }
            </section>
          </ng-container>
          <div class="dialog-actions" style="justify-content: flex-start">
            <p-button [label]="t('common.save')" icon="pi pi-check" [loading]="saving()" (onClick)="save()" />
            <p-button [label]="t('common.cancel')" severity="secondary" [text]="true" (onClick)="reset()" />
          </div>
        }
      </ng-container>
    </ng-container>
  `,
})
export class SettingsPageComponent {
  readonly session = inject(SessionService);
  private readonly admin = inject(AdminService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  readonly retention = signal<RetentionStatus | null>(null);
  readonly retentionBusy = signal<string | null>(null);
  readonly company = signal<CompanyInfo | null>(null);
  readonly form = signal<SettingsForm | null>(null);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly localeOptions = [
    { value: 'it', label: 'IT' },
    { value: 'en', label: 'EN' },
    { value: 'de', label: 'DE' },
  ];
  readonly eventFieldOptions = computed(() => EVENT_RULE_FIELDS.map((f) => ({ value: f, label: this.fieldLabel(f) })));
  readonly personFieldOptions = computed(() => PERSON_RULE_FIELDS.map((f) => ({ value: f, label: this.fieldLabel(f) })));
  readonly dupFieldOptions = computed(() => DUP_RULE_FIELDS.map((f) => ({ value: f, label: this.transloco.translate('admin.dup_' + f) })));

  constructor() {
    void this.load();
    if (this.session.can('company.retention')) void this.loadRetention();
  }

  async loadRetention(): Promise<void> {
    try {
      this.retention.set(await firstValueFrom(this.api.get<RetentionStatus>('company/retention')));
    } catch {
      this.retention.set(null);
    }
  }

  patchRetention(p: Partial<RetentionStatus>): void {
    const r = this.retention();
    if (r) this.retention.set({ ...r, ...p });
  }

  async saveRetention(): Promise<void> {
    const r = this.retention();
    if (!r) return;
    this.retentionBusy.set('save');
    try {
      this.retention.set(await firstValueFrom(this.api.patch<RetentionStatus>('company/retention', { retention_identity_years: r.retention_identity_years, retention_audit_years: r.retention_audit_years })));
      this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.retentionBusy.set(null);
    }
  }

  async runRetention(): Promise<void> {
    this.retentionBusy.set('run');
    try {
      const job = await firstValueFrom(this.api.post<AsyncJob>('company/retention/run', {}));
      const done = await this.jobs.waitFor(job);
      const n = (done.result as { persons_anonymized?: number } | null)?.persons_anonymized ?? 0;
      this.messages.add({ severity: 'success', summary: this.transloco.translate('retention.run_done', { n }) });
      await this.loadRetention();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    } finally {
      this.retentionBusy.set(null);
    }
  }

  private fieldLabel(f: string): string {
    const key = `fields.${f === 'country_code' ? 'country' : f}`;
    const label = this.transloco.translate(key);
    return label === key ? f : label;
  }

  async load(): Promise<void> {
    try {
      const c = await firstValueFrom(this.admin.company());
      this.company.set(c);
      this.reset();
    } catch (err) {
      this.error.set(errorMessage(err, this.transloco.translate('common.load_error')));
    }
  }

  reset(): void {
    const c = this.company();
    if (!c) return;
    this.form.set({
      name: c.name, timezone: c.timezone, default_locale: c.default_locale, auto_lock_hours: c.settings.auto_lock_hours,
      devices_need_authorization: c.settings.devices_need_authorization, event_required: [...c.settings.validity_rules.event_required],
      person_required: [...c.settings.validity_rules.person_required], dup_minutes: c.settings.duplicate_rule.minutes,
      dup_fields: [...c.settings.duplicate_rule.fields],
    });
  }

  patch(p: Partial<SettingsForm>): void {
    const f = this.form();
    if (f) this.form.set({ ...f, ...p });
  }

  async save(): Promise<void> {
    const f = this.form();
    if (!f || this.saving()) return;
    this.saving.set(true);
    this.error.set(null);
    try {
      const c = await firstValueFrom(
        this.admin.patchCompany({
          name: f.name.trim(), timezone: f.timezone.trim(), default_locale: f.default_locale,
          settings: {
            auto_lock_hours: f.auto_lock_hours, devices_need_authorization: f.devices_need_authorization,
            validity_rules: { event_required: f.event_required, person_required: f.person_required },
            duplicate_rule: { minutes: f.dup_minutes, fields: f.dup_fields },
          },
        }),
      );
      this.company.set(c);
      this.reset();
      void this.session.reload();
      this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
    } catch (err) {
      this.error.set(errorMessage(err, this.transloco.translate('common.save_error')));
    } finally {
      this.saving.set(false);
    }
  }
}
