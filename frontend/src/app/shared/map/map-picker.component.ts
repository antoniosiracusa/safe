import { AfterViewInit, ChangeDetectionStrategy, Component, DestroyRef, ElementRef, effect, inject, input, output, signal, untracked, viewChild } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import mapboxgl from 'mapbox-gl';
import { ButtonModule } from 'primeng/button';

import { MapboxService } from '../../core/map/mapbox.service';

/** Selettore di posizione: clic sulla mappa o trascinamento del marker → (lon, lat). */
@Component({
  selector: 'safe-map-picker',
  imports: [TranslocoDirective, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="picker" *transloco="let t">
      @if (!mapbox.configured) {
        <p class="hint">{{ t('map.token_missing') }}</p>
      } @else {
        <div #map class="map" role="application" [attr.aria-label]="t('map.picker_label')"></div>
        <div class="row">
          <span class="hint">{{ t('map.picker_hint') }}</span>
          <p-button type="button" icon="pi pi-times" [text]="true" size="small" severity="secondary" [label]="t('map.picker_clear')" [disabled]="!value()" (onClick)="clear()" />
        </div>
      }
    </div>
  `,
  styles: `
    .picker { display: flex; flex-direction: column; gap: 0.35rem; }
    .map { height: 260px; border-radius: 6px; border: 1px solid var(--p-surface-200); overflow: hidden; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
    .hint { font-size: 0.78rem; color: var(--p-text-muted-color); }
  `,
})
export class MapPickerComponent implements AfterViewInit {
  readonly value = input<[number, number] | null>(null);
  readonly changed = output<[number, number] | null>();
  readonly mapbox = inject(MapboxService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly container = viewChild<ElementRef<HTMLDivElement>>('map');
  private map: mapboxgl.Map | null = null;
  private marker: mapboxgl.Marker | null = null;
  readonly ready = signal(false);

  constructor() {
    effect(() => {
      const v = this.value();
      untracked(() => this.placeMarker(v, false));
    });
    this.destroyRef.onDestroy(() => this.map?.remove());
  }

  ngAfterViewInit(): void {
    const el = this.container()?.nativeElement;
    if (!el || !this.mapbox.configured) return;
    const v = this.value();
    this.map = this.mapbox.create(el, 'mapbox://styles/mapbox/outdoors-v12', { center: v ?? undefined, zoom: v ? 14 : undefined });
    this.map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-left');
    this.map.on('load', () => {
      this.ready.set(true);
      this.placeMarker(this.value(), false);
    });
    this.map.on('click', (e) => this.placeMarker([e.lngLat.lng, e.lngLat.lat], true));
  }

  private placeMarker(v: [number, number] | null, emit: boolean): void {
    if (!this.map || !this.ready()) return;
    if (!v) {
      this.marker?.remove();
      this.marker = null;
      return;
    }
    if (!this.marker) {
      this.marker = new mapboxgl.Marker({ color: '#c8102e', draggable: true }).setLngLat(v).addTo(this.map);
      this.marker.on('dragend', () => {
        const p = this.marker!.getLngLat();
        this.changed.emit([Number(p.lng.toFixed(6)), Number(p.lat.toFixed(6))]);
      });
    } else {
      this.marker.setLngLat(v);
    }
    if (emit) this.changed.emit([Number(v[0].toFixed(6)), Number(v[1].toFixed(6))]);
  }

  clear(): void {
    this.placeMarker(null, false);
    this.changed.emit(null);
  }
}
