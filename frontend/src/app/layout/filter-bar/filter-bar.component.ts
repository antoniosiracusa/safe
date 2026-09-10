import { ChangeDetectionStrategy, Component, computed, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DatePickerModule } from 'primeng/datepicker';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';

import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { FilterStore } from '../../core/filters/filter.store';

function toIso(d: Date | null): string | null {
  if (!d) return null;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fromIso(s: string | null): Date | null {
  return s ? new Date(`${s}T00:00:00`) : null;
}

/** Barra filtri globale: squadra, periodo (stagione o date), comprensorio, zona, solo validi, reset.
 *  Legge e scrive la query string tramite FilterStore. */
@Component({
  selector: 'safe-filter-bar',
  imports: [FormsModule, TranslocoDirective, SelectModule, MultiSelectModule, DatePickerModule, CheckboxModule, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './filter-bar.component.html',
  styleUrl: './filter-bar.component.scss',
})
export class FilterBarComponent implements OnInit {
  readonly store = inject(FilterStore);
  readonly optionsService = inject(FilterOptionsService);

  readonly filters = this.store.filters;
  readonly options = this.optionsService.options;
  readonly zonesForArea = computed(() => {
    const area = this.filters().ski_area;
    const zones = this.options().zones;
    return area ? zones.filter((z) => z.ski_area === area) : zones;
  });
  readonly dateFrom = computed(() => fromIso(this.filters().date_from));
  readonly dateTo = computed(() => fromIso(this.filters().date_to));
  readonly periodMode = computed(() => (this.filters().date_from || this.filters().date_to ? 'dates' : 'season'));

  ngOnInit(): void {
    void this.optionsService.load().catch(() => undefined);
  }

  setTeams(team: string[]): void {
    this.store.apply({ team });
  }

  setSeason(season: string | null): void {
    this.store.apply({ season, date_from: null, date_to: null });
  }

  setDateFrom(d: Date | null): void {
    this.store.apply({ date_from: toIso(d) });
  }

  setDateTo(d: Date | null): void {
    this.store.apply({ date_to: toIso(d) });
  }

  setSkiArea(ski_area: string | null): void {
    const zone = this.filters().zone;
    const zoneStillValid = zone && this.options().zones.some((z) => z.value === zone && z.ski_area === ski_area);
    this.store.apply({ ski_area, zone: zoneStillValid ? zone : null });
  }

  setZone(zone: string | null): void {
    const z = this.options().zones.find((x) => x.value === zone);
    this.store.apply({ zone, ski_area: z ? z.ski_area : this.filters().ski_area });
  }

  setValidOnly(valid_only: boolean): void {
    this.store.apply({ valid_only });
  }

  reset(): void {
    this.store.reset();
  }
}
