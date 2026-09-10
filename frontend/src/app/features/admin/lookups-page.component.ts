import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { LOOKUP_DIMENSIONS, LookupAdminItem } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { LookupsService } from '../../core/lookups/lookups.service';
import { SessionService } from '../../core/session/session.service';

interface LookupForm {
  id: string | null;
  code: string;
  it: string;
  en: string;
  de: string;
  sort_order: number;
  color: string;
  a01: string;
}

@Component({
  selector: 'safe-admin-lookups',
  imports: [FormsModule, TranslocoDirective, ButtonModule, DialogModule, InputNumberModule, InputTextModule, SelectModule, TableModule, TagModule, ToastModule, TooltipModule, CanDirective],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  template: `
    <ng-container *transloco="let t">
      <p-toast />
      <div class="page-head">
        <h1>{{ t('nav.lookups') }}</h1>
        <ng-container *safeCan="'lookups.manage'; mode: 'hide'">
          <p-button [label]="t('admin.new_value')" icon="pi pi-plus" (onClick)="open(null)" />
        </ng-container>
      </div>
      <p class="intro">{{ t('admin.lookups_intro') }}</p>
      <ng-container *safeCan="'lookups.manage'">
        <div class="toolbar">
          <div class="field">
            <label for="lk-dim">{{ t('admin.dimension') }}</label>
            <p-select inputId="lk-dim" [options]="dimensionOptions()" optionLabel="label" optionValue="value" [ngModel]="dimension()" (ngModelChange)="dimension.set($event)" [filter]="true" appendTo="body" styleClass="w-full" />
          </div>
        </div>
        @if (error()) { <p class="error-box" role="alert">{{ t('common.load_error') }}</p> }
        <div class="table-wrap">
          <p-table [value]="items()" [loading]="loading()" styleClass="p-datatable-sm" dataKey="id" [tableStyle]="{ 'min-width': '860px' }">
            <ng-template #header>
              <tr>
                <th>{{ t('admin.code') }}</th>
                <th>IT</th><th>EN</th><th>DE</th>
                <th class="num">{{ t('admin.sort_order') }}</th>
                <th>A01</th>
                <th>{{ t('admin.origin') }}</th>
                <th>{{ t('admin.state') }}</th>
                <th></th>
              </tr>
            </ng-template>
            <ng-template #body let-v>
              <tr [class.inactive]="!v.is_active || v.disabled_for_company">
                <td><code>{{ v.code }}</code> @if (v.color) { <span class="swatch" [style.background]="v.color"></span> } @if (v.parent) { <span class="muted">← {{ v.parent }}</span> }</td>
                <td>{{ v.labels.it }}</td><td>{{ v.labels.en }}</td><td>{{ v.labels.de }}</td>
                <td class="num">{{ v.sort_order }}</td>
                <td>{{ v.mapping?.veneto_a01 || '—' }}</td>
                <td><p-tag [value]="v.is_custom ? t('admin.custom') : t('admin.standard')" [severity]="v.is_custom ? 'info' : 'secondary'" /></td>
                <td>
                  @if (v.disabled_for_company) { <p-tag [value]="t('admin.disabled_here')" severity="warn" /> }
                  @else if (!v.is_active) { <p-tag [value]="t('admin.inactive')" severity="secondary" /> }
                  @else { <p-tag [value]="t('admin.active')" severity="success" /> }
                </td>
                <td class="actions-cell">
                  @if (v.is_custom) {
                    <p-button icon="pi pi-pencil" [text]="true" size="small" (onClick)="open(v)" [pTooltip]="t('common.edit')" tooltipPosition="left" />
                    <p-button [icon]="v.is_active ? 'pi pi-ban' : 'pi pi-check-circle'" [text]="true" size="small" [severity]="v.is_active ? 'danger' : 'success'" (onClick)="setActive(v, !v.is_active)" [pTooltip]="v.is_active ? t('admin.deactivate') : t('admin.reactivate')" tooltipPosition="left" />
                  } @else {
                    <p-button [icon]="v.disabled_for_company ? 'pi pi-check-circle' : 'pi pi-ban'" [text]="true" size="small" [severity]="v.disabled_for_company ? 'success' : 'danger'" (onClick)="setActive(v, v.disabled_for_company)" [pTooltip]="v.disabled_for_company ? t('admin.enable_here') : t('admin.disable_here')" tooltipPosition="left" />
                  }
                </td>
              </tr>
            </ng-template>
            <ng-template #emptymessage><tr><td colspan="9" class="empty">@if (!loading()) { — }</td></tr></ng-template>
          </p-table>
        </div>
      </ng-container>

      @if (dialog(); as d) {
        <p-dialog [visible]="true" (visibleChange)="dialog.set(null)" [modal]="true" [header]="d.id ? t('common.edit') : t('admin.new_value')" [style]="{ width: 'min(640px, 96vw)' }">
          @if (dialogError(); as e) { <p class="error-box" role="alert">{{ e }}</p> }
          <div class="dialog-form">
            <div class="field">
              <label for="lk-code">{{ t('admin.code') }} *</label>
              <input pInputText id="lk-code" [ngModel]="d.code" (ngModelChange)="patch({ code: $event })" [disabled]="!!d.id" maxlength="60" placeholder="es. urto_drone" />
              <small class="muted">{{ t('admin.code_hint') }}</small>
            </div>
            <div class="field">
              <label for="lk-sort">{{ t('admin.sort_order') }}</label>
              <p-inputNumber inputId="lk-sort" [ngModel]="d.sort_order" (ngModelChange)="patch({ sort_order: $event })" [min]="0" [max]="32767" styleClass="w-full" />
            </div>
            <div class="field"><label for="lk-it">IT *</label><input pInputText id="lk-it" [ngModel]="d.it" (ngModelChange)="patch({ it: $event })" maxlength="120" /></div>
            <div class="field"><label for="lk-en">EN</label><input pInputText id="lk-en" [ngModel]="d.en" (ngModelChange)="patch({ en: $event })" maxlength="120" /></div>
            <div class="field"><label for="lk-de">DE</label><input pInputText id="lk-de" [ngModel]="d.de" (ngModelChange)="patch({ de: $event })" maxlength="120" /></div>
            <div class="field"><label for="lk-color">{{ t('admin.color') }}</label><input pInputText id="lk-color" type="color" [ngModel]="d.color || '#888888'" (ngModelChange)="patch({ color: $event })" /></div>
            @if (dimension() === 'cause' || dimension() === 'equipment') {
              <div class="field span-2">
                <label for="lk-a01">{{ t('admin.a01_mapping') }}</label>
                <p-select inputId="lk-a01" [options]="a01Options()" optionLabel="label" optionValue="value" [ngModel]="d.a01" (ngModelChange)="patch({ a01: $event })" appendTo="body" styleClass="w-full" />
              </div>
            }
          </div>
          <div class="dialog-actions">
            <p-button [label]="t('common.cancel')" severity="secondary" [text]="true" (onClick)="dialog.set(null)" />
            <p-button [label]="t('common.save')" icon="pi pi-check" [loading]="saving()" [disabled]="!d.code.trim() || !d.it.trim()" (onClick)="save()" />
          </div>
        </p-dialog>
      }
    </ng-container>
  `,
})
export class LookupsPageComponent {
  readonly session = inject(SessionService);
  private readonly admin = inject(AdminService);
  private readonly lookups = inject(LookupsService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  readonly dimension = signal('cause');
  readonly items = signal<LookupAdminItem[]>([]);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly dialog = signal<LookupForm | null>(null);
  readonly dialogError = signal<string | null>(null);
  readonly saving = signal(false);

  readonly dimensionOptions = computed(() =>
    LOOKUP_DIMENSIONS.map((d) => {
      const key = `fields.${d === 'evacuation_mean' ? 'evacuation_means' : d === 'person_role' ? 'role' : d}`;
      const label = this.transloco.translate(key);
      return { value: d, label: label === key ? d : `${label} (${d})` };
    }),
  );
  readonly a01Options = computed(() =>
    (this.dimension() === 'cause'
      ? ['Caduta accidentale', 'Collisione altro sciatore', 'Collisione ostacolo fisso', 'Collisione ostacolo mobile', 'Malore', 'Incidente impianto risalita', 'Altro']
      : ['Sci', 'Snowboard', 'Altro']
    ).map((v) => ({ value: v, label: v })),
  );

  constructor() {
    effect(() => {
      this.dimension();
      untracked(() => void this.reload());
    });
  }

  async reload(): Promise<void> {
    if (!this.session.can('lookups.manage')) return;
    this.loading.set(true);
    this.error.set(false);
    try {
      this.items.set(await firstValueFrom(this.admin.lookupValues(this.dimension())));
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  open(v: LookupAdminItem | null): void {
    this.dialogError.set(null);
    this.dialog.set({
      id: v?.id ?? null, code: v?.code ?? '', it: v?.labels['it'] ?? '', en: v?.labels['en'] ?? '', de: v?.labels['de'] ?? '',
      sort_order: v?.sort_order ?? 100, color: v?.color ?? '', a01: String(v?.mapping?.['veneto_a01'] ?? 'Altro'),
    });
  }

  patch(p: Partial<LookupForm>): void {
    const d = this.dialog();
    if (d) this.dialog.set({ ...d, ...p });
  }

  async save(): Promise<void> {
    const d = this.dialog();
    if (!d || this.saving()) return;
    this.saving.set(true);
    this.dialogError.set(null);
    const mapping: Record<string, string> = {};
    if (this.dimension() === 'cause' || this.dimension() === 'equipment') mapping['veneto_a01'] = d.a01;
    const body: Record<string, unknown> = {
      labels: { it: d.it.trim(), en: d.en.trim(), de: d.de.trim() }, sort_order: d.sort_order, color: d.color || null, mapping,
    };
    try {
      await firstValueFrom(
        d.id ? this.admin.patchLookup(this.dimension(), d.id, body) : this.admin.createLookup(this.dimension(), { ...body, code: d.code.trim() }),
      );
      this.dialog.set(null);
      this.lookups.loaded.set(false);
      void this.lookups.load();
      this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
      await this.reload();
    } catch (err) {
      this.dialogError.set(errorMessage(err, this.transloco.translate('common.save_error')));
    } finally {
      this.saving.set(false);
    }
  }

  async setActive(v: LookupAdminItem, active: boolean): Promise<void> {
    try {
      await firstValueFrom(this.admin.patchLookup(this.dimension(), v.id, { is_active: active }));
      this.lookups.loaded.set(false);
      void this.lookups.load();
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    }
  }
}
