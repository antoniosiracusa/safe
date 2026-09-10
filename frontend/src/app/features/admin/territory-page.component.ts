import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TextareaModule } from 'primeng/textarea';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { AdminLift, AdminSkiArea, AdminSlope, AdminZone } from '../../core/api/admin.models';
import { AdminService } from '../../core/api/admin.service';
import { errorMessage } from '../../core/api/errors';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { LookupsService } from '../../core/lookups/lookups.service';
import { SessionService } from '../../core/session/session.service';
import { TerritoryService } from '../../core/territory/territory.service';

type Kind = 'ski-areas' | 'zones' | 'slopes' | 'lifts';

interface EditForm {
  kind: Kind;
  id: string | null;
  name: string;
  regional_code: string;
  difficulty: string | null;
  lift_type: string;
  geojson: string;
  is_active: boolean;
}

/** Gestione territorio a tre colonne: comprensori → zone → piste (+ impianti del comprensorio). */
@Component({
  selector: 'safe-admin-territory',
  imports: [FormsModule, TranslocoDirective, ButtonModule, DialogModule, InputTextModule, SelectModule, TextareaModule, ToastModule, TooltipModule, CanDirective],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin-page.scss',
  templateUrl: './territory-page.component.html',
})
export class TerritoryPageComponent {
  readonly session = inject(SessionService);
  readonly lookups = inject(LookupsService);
  private readonly admin = inject(AdminService);
  private readonly territory = inject(TerritoryService);
  private readonly filterOptions = inject(FilterOptionsService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  readonly areas = signal<AdminSkiArea[]>([]);
  readonly zones = signal<AdminZone[]>([]);
  readonly slopes = signal<AdminSlope[]>([]);
  readonly lifts = signal<AdminLift[]>([]);
  readonly selectedArea = signal<string | null>(null);
  readonly selectedZone = signal<string | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly showLifts = signal(false);

  readonly areaZones = computed(() => this.zones().filter((z) => z.ski_area.id === this.selectedArea()));
  readonly zoneSlopes = computed(() => this.slopes().filter((s) => s.zone.id === this.selectedZone()));
  readonly areaLifts = computed(() => this.lifts().filter((l) => l.ski_area.id === this.selectedArea()));
  readonly area = computed(() => this.areas().find((a) => a.id === this.selectedArea()) ?? null);
  readonly zone = computed(() => this.zones().find((z) => z.id === this.selectedZone()) ?? null);

  readonly dialog = signal<EditForm | null>(null);
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
      const [areas, zones, slopes, lifts] = await Promise.all([
        firstValueFrom(this.admin.skiAreas()),
        firstValueFrom(this.admin.zones()),
        firstValueFrom(this.admin.slopes()),
        firstValueFrom(this.admin.lifts()),
      ]);
      this.areas.set(areas);
      this.zones.set(zones);
      this.slopes.set(slopes);
      this.lifts.set(lifts);
      if (!this.selectedArea() && areas.length) this.selectedArea.set(areas[0].id);
      if (this.selectedZone() && !zones.some((z) => z.id === this.selectedZone())) this.selectedZone.set(null);
    } catch {
      this.error.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  selectArea(id: string): void {
    this.selectedArea.set(id);
    this.selectedZone.set(null);
  }

  open(kind: Kind, item: AdminSkiArea | AdminZone | AdminSlope | AdminLift | null): void {
    this.dialogError.set(null);
    const s = item as Partial<AdminSlope & AdminSkiArea & AdminLift> | null;
    this.dialog.set({
      kind,
      id: item?.id ?? null,
      name: item?.name ?? '',
      regional_code: s?.regional_code ?? '',
      difficulty: s?.difficulty ?? null,
      lift_type: s?.lift_type ?? '',
      geojson: '',
      is_active: item?.is_active ?? true,
    });
  }

  patch(p: Partial<EditForm>): void {
    const d = this.dialog();
    if (d) this.dialog.set({ ...d, ...p });
  }

  async save(): Promise<void> {
    const d = this.dialog();
    if (!d || this.saving()) return;
    this.saving.set(true);
    this.dialogError.set(null);
    const body: Record<string, unknown> = { name: d.name.trim(), is_active: d.is_active };
    if (d.kind === 'ski-areas') body['regional_code'] = d.regional_code.trim();
    if (d.kind === 'zones' && !d.id) body['ski_area_id'] = this.selectedArea();
    if (d.kind === 'slopes') {
      body['regional_code'] = d.regional_code.trim();
      body['difficulty'] = d.difficulty;
      if (!d.id) body['zone_id'] = this.selectedZone();
    }
    if (d.kind === 'lifts') {
      body['lift_type'] = d.lift_type.trim();
      if (!d.id) body['ski_area_id'] = this.selectedArea();
    }
    if (d.geojson.trim()) {
      try {
        body[d.kind === 'ski-areas' ? 'boundary' : 'geom'] = JSON.parse(d.geojson);
      } catch {
        this.dialogError.set(this.transloco.translate('admin.geojson_invalid'));
        this.saving.set(false);
        return;
      }
    }
    try {
      await firstValueFrom(this.admin.save(d.kind, d.id, body));
      this.dialog.set(null);
      this.invalidate();
      this.messages.add({ severity: 'success', summary: this.transloco.translate('admin.saved') });
      await this.reload();
    } catch (err) {
      this.dialogError.set(errorMessage(err, this.transloco.translate('common.save_error')));
    } finally {
      this.saving.set(false);
    }
  }

  async toggle(kind: Kind, item: { id: string; is_active: boolean }): Promise<void> {
    try {
      await firstValueFrom(item.is_active ? this.admin.deactivate(kind, item.id) : this.admin.save(kind, item.id, { is_active: true }));
      this.invalidate();
      await this.reload();
    } catch (err) {
      this.messages.add({ severity: 'error', summary: errorMessage(err, this.transloco.translate('common.save_error')) });
    }
  }

  private invalidate(): void {
    this.territory.loaded.set(false);
    this.filterOptions.invalidate();
  }

  difficultyLabel(code: string | null): string {
    return this.lookups.label('slope_difficulty', code);
  }
}
