import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom, forkJoin } from 'rxjs';

import { RescueService } from '../api/rescue.service';
import { SkiArea, Slope, Zone } from '../api/rescue.models';

/** Anagrafica territoriale per i form (comprensori → zone → piste), caricata una volta per sessione. */
@Injectable({ providedIn: 'root' })
export class TerritoryService {
  private readonly rescue = inject(RescueService);
  private loading: Promise<void> | null = null;

  readonly skiAreas = signal<SkiArea[]>([]);
  readonly zones = signal<Zone[]>([]);
  readonly slopes = signal<Slope[]>([]);
  readonly loaded = signal(false);

  readonly skiAreaOptions = computed(() => this.skiAreas().map((a) => ({ value: a.id, label: a.name })));

  load(): Promise<void> {
    if (this.loaded()) return Promise.resolve();
    if (!this.loading) {
      this.loading = firstValueFrom(
        forkJoin({ areas: this.rescue.skiAreas(), zones: this.rescue.zones(), slopes: this.rescue.slopes() }),
      )
        .then(({ areas, zones, slopes }) => {
          this.skiAreas.set(areas);
          this.zones.set(zones);
          this.slopes.set(slopes);
          this.loaded.set(true);
        })
        .finally(() => (this.loading = null));
    }
    return this.loading;
  }

  zoneOptions(skiAreaId: string | null): { value: string; label: string }[] {
    return this.zones()
      .filter((z) => !skiAreaId || z.ski_area.id === skiAreaId)
      .map((z) => ({ value: z.id, label: z.name }));
  }

  slopeOptions(zoneId: string | null, skiAreaId: string | null = null): { value: string; label: string; difficulty: string | null }[] {
    return this.slopes()
      .filter((s) => (zoneId ? s.zone.id === zoneId : !skiAreaId || s.zone.ski_area === skiAreaId))
      .map((s) => ({ value: s.id, label: s.regional_code ? `${s.name} (${s.regional_code})` : s.name, difficulty: s.difficulty }));
  }

  zoneOf(slopeId: string): Zone | undefined {
    const slope = this.slopes().find((s) => s.id === slopeId);
    return slope ? this.zones().find((z) => z.id === slope.zone.id) : undefined;
  }
}
