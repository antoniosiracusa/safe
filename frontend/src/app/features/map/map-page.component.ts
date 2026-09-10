import { HttpParams } from '@angular/common/http';
import { AfterViewInit, ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, isDevMode, signal, untracked, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import type { FeatureCollection, MultiPolygon, Point } from 'geojson';
import mapboxgl from 'mapbox-gl';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { SelectButtonModule } from 'primeng/selectbutton';
import { TooltipModule } from 'primeng/tooltip';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import { CanDirective } from '../../core/authz/can.directive';
import { FilterStore } from '../../core/filters/filter.store';
import { DIFFICULTY_COLORS, MapStyle, MapboxService, firstSymbolLayer } from '../../core/map/mapbox.service';
import { SessionService } from '../../core/session/session.service';
import { EventDrawerComponent } from '../data/events/event-drawer.component';

type StyleCode = MapStyle['code'];
type Layer = 'boundaries' | 'slopes' | 'events' | 'heatmap';
const ALL_LAYERS: Layer[] = ['boundaries', 'slopes', 'events', 'heatmap'];
const DEFAULT_LAYERS: Layer[] = ['boundaries', 'slopes', 'events'];

/**
 * Mappa eventi (Mapbox GL JS): stili inverno/estate/satellite, layer attivabili (confini comprensorio,
 * piste e impianti, eventi in cluster, heatmap), popup con id, data/ora e collegamento al rapporto.
 * Il GeoJSON degli eventi contiene solo id e data/ora. Stile e layer sono nella URL.
 */
@Component({
  selector: 'safe-map-page',
  imports: [FormsModule, TranslocoDirective, ButtonModule, CheckboxModule, SelectButtonModule, TooltipModule, CanDirective, EventDrawerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './map-page.component.html',
  styleUrl: './map-page.component.scss',
})
export class MapPageComponent implements AfterViewInit {
  readonly session = inject(SessionService);
  readonly mapbox = inject(MapboxService);
  private readonly api = inject(ApiService);
  private readonly filterStore = inject(FilterStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly container = viewChild<ElementRef<HTMLDivElement>>('map');

  readonly styles = signal<MapStyle[]>([]);
  readonly style = signal<StyleCode>('winter');
  readonly layers = signal<Layer[]>(DEFAULT_LAYERS);
  readonly count = signal<number | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly selectedEvent = signal<string | null>(null);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });

  readonly styleOptions = computed(() => this.styles().map((s) => ({ value: s.code, label: this.transloco.translate(s.label_key) })));
  readonly allLayers = ALL_LAYERS;

  private map: mapboxgl.Map | null = null;
  private popup: mapboxgl.Popup | null = null;
  private events: FeatureCollection | null = null;
  private boundaries: FeatureCollection | null = null;
  private slopes: FeatureCollection | null = null;
  private lifts: FeatureCollection | null = null;
  private styleReady = false;

  constructor() {
    const qp = this.route.snapshot.queryParamMap;
    const style = qp.get('style') as StyleCode | null;
    if (style && ['winter', 'summer', 'satellite'].includes(style)) this.style.set(style);
    const layers = qp.get('layers');
    if (layers !== null) this.layers.set(layers.split(',').filter((l): l is Layer => ALL_LAYERS.includes(l as Layer)));
    if (qp.get('event')) this.selectedEvent.set(qp.get('event'));

    effect(() => {
      this.filterStore.httpParams();
      untracked(() => void this.loadEvents());
    });
    effect(() => {
      this.layers();
      untracked(() => this.applyLayerVisibility());
    });
    this.destroyRef.onDestroy(() => this.map?.remove());
  }

  ngAfterViewInit(): void {
    if (!this.mapbox.configured) return;
    void this.init();
  }

  private async init(): Promise<void> {
    try {
      const res = await firstValueFrom(this.api.get<{ styles: MapStyle[] }>('map/styles'));
      this.styles.set(res.styles);
    } catch {
      this.error.set('styles');
      return;
    }
    const el = this.container()?.nativeElement;
    if (!el) return;
    this.map = this.mapbox.create(el, this.styleUrl());
    if (isDevMode()) (window as unknown as { __safeMap?: mapboxgl.Map }).__safeMap = this.map; // diagnostica in sviluppo
    this.map.addControl(new mapboxgl.NavigationControl({ visualizePitch: false }), 'top-left');
    this.map.addControl(new mapboxgl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    this.map.on('error', (e) => {
      if (String(e.error?.message ?? '').match(/401|403|token/i)) this.error.set('token');
    });
    this.map.on('style.load', () => {
      this.styleReady = true;
      this.addLayers();
      this.applyLayerVisibility();
    });
    void Promise.all([
      firstValueFrom(this.api.get<FeatureCollection>('map/ski-areas.geojson')).then((b) => (this.boundaries = b)),
      firstValueFrom(this.api.get<FeatureCollection>('map/slopes.geojson')).then((s) => (this.slopes = s)),
      firstValueFrom(this.api.get<FeatureCollection>('map/lifts.geojson')).then((l) => (this.lifts = l)),
    ]).then(() => {
      this.refreshSources();
      this.fitToBoundaries();
    });
  }

  private styleUrl(): string {
    return this.styles().find((s) => s.code === this.style())?.url ?? 'mapbox://styles/mapbox/light-v11';
  }

  private async loadEvents(): Promise<void> {
    this.loading.set(true);
    try {
      let params: HttpParams = this.filterStore.httpParams();
      params = params.delete('lang');
      this.events = await firstValueFrom(this.api.get<FeatureCollection>('map/events.geojson', params));
      this.count.set(this.events.features.length);
      this.refreshSources();
    } catch {
      this.error.set('events');
    } finally {
      this.loading.set(false);
    }
  }

  /** Sorgenti e layer sono ricreati a ogni cambio di stile (Mapbox li scarta con lo stile). */
  private addLayers(): void {
    const map = this.map;
    if (!map) return;
    const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
    const symbol = firstSymbolLayer(map);
    const st = this.styles().find((s) => s.code === this.style());
    if (st?.terrain) this.mapbox.addTerrain(map);

    map.addSource('safe-boundaries', { type: 'geojson', data: this.boundaries ?? empty });
    map.addLayer({ id: 'safe-boundaries-fill', type: 'fill', source: 'safe-boundaries', paint: { 'fill-color': '#c8102e', 'fill-opacity': 0.05 } }, symbol);
    map.addLayer({ id: 'safe-boundaries-line', type: 'line', source: 'safe-boundaries', paint: { 'line-color': '#c8102e', 'line-width': 2, 'line-dasharray': [3, 2] } }, symbol);

    map.addSource('safe-lifts', { type: 'geojson', data: this.lifts ?? empty });
    map.addLayer({ id: 'safe-lifts', type: 'line', source: 'safe-lifts', paint: { 'line-color': '#111827', 'line-width': 2, 'line-dasharray': [1, 1.5] } }, symbol);
    map.addSource('safe-slopes', { type: 'geojson', data: this.slopes ?? empty });
    map.addLayer({
      id: 'safe-slopes', type: 'line', source: 'safe-slopes',
      paint: {
        'line-color': ['match', ['coalesce', ['get', 'difficulty'], 'unclassified'], 'ski_school', DIFFICULTY_COLORS['ski_school'], 'blue', DIFFICULTY_COLORS['blue'], 'red', DIFFICULTY_COLORS['red'], 'black', DIFFICULTY_COLORS['black'], DIFFICULTY_COLORS['unclassified']],
        'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 15, 6],
        'line-opacity': 0.85,
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    }, symbol);
    map.addLayer({ id: 'safe-slopes-label', type: 'symbol', source: 'safe-slopes', layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-size': 11, 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'] }, paint: { 'text-color': '#1f2937', 'text-halo-color': '#ffffff', 'text-halo-width': 1.2 } });

    map.addSource('safe-events-raw', { type: 'geojson', data: this.events ?? empty });
    map.addSource('safe-events', { type: 'geojson', data: this.events ?? empty, cluster: true, clusterMaxZoom: 15, clusterRadius: 45 });
    map.addLayer({ id: 'safe-heatmap', type: 'heatmap', source: 'safe-events-raw', paint: { 'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 12, 15, 30], 'heatmap-opacity': 0.75, 'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 15, 1.4] } }, symbol);
    map.addLayer({ id: 'safe-clusters', type: 'circle', source: 'safe-events', filter: ['has', 'point_count'], paint: { 'circle-color': ['step', ['get', 'point_count'], '#2a78d6', 25, '#1d5fb0', 100, '#12457f'], 'circle-radius': ['step', ['get', 'point_count'], 16, 25, 22, 100, 28], 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } });
    map.addLayer({ id: 'safe-cluster-count', type: 'symbol', source: 'safe-events', filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'] }, paint: { 'text-color': '#ffffff' } });
    map.addLayer({ id: 'safe-points', type: 'circle', source: 'safe-events', filter: ['!', ['has', 'point_count']], paint: { 'circle-color': '#c8102e', 'circle-radius': 7, 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } });

    map.on('click', 'safe-clusters', (e) => {
      const feature = e.features?.[0];
      const clusterId = feature?.properties?.['cluster_id'] as number | undefined;
      const source = map.getSource('safe-events') as mapboxgl.GeoJSONSource | undefined;
      if (clusterId === undefined || !source) return;
      source.getClusterExpansionZoom(clusterId, (err, zoom) => {
        if (err || zoom == null) return;
        map.easeTo({ center: (feature!.geometry as Point).coordinates as [number, number], zoom });
      });
    });
    map.on('click', 'safe-points', (e) => this.openPopup(e));
    for (const id of ['safe-clusters', 'safe-points']) {
      map.on('mouseenter', id, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', id, () => (map.getCanvas().style.cursor = ''));
    }
  }

  private refreshSources(): void {
    const map = this.map;
    if (!map || !this.styleReady) return;
    const set = (id: string, data: FeatureCollection | null) => {
      const src = map.getSource(id) as mapboxgl.GeoJSONSource | undefined;
      if (src && data) src.setData(data);
    };
    set('safe-boundaries', this.boundaries);
    set('safe-slopes', this.slopes);
    set('safe-lifts', this.lifts);
    set('safe-events', this.events);
    set('safe-events-raw', this.events);
  }

  private applyLayerVisibility(): void {
    const map = this.map;
    if (!map || !this.styleReady) return;
    const on = new Set(this.layers());
    const vis = (ids: string[], visible: boolean) =>
      ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'));
    vis(['safe-boundaries-fill', 'safe-boundaries-line'], on.has('boundaries'));
    vis(['safe-slopes', 'safe-slopes-label', 'safe-lifts'], on.has('slopes'));
    vis(['safe-clusters', 'safe-cluster-count', 'safe-points'], on.has('events'));
    vis(['safe-heatmap'], on.has('heatmap'));
  }

  private fitToBoundaries(): void {
    const map = this.map;
    const feats = this.boundaries?.features ?? [];
    if (!map || !feats.length) return;
    const bounds = new mapboxgl.LngLatBounds();
    for (const f of feats) {
      const coords = (f.geometry as MultiPolygon).coordinates.flat(2) as [number, number][];
      coords.forEach((c) => bounds.extend(c));
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 40, duration: 0 });
  }

  private openPopup(e: mapboxgl.MapMouseEvent & { features?: mapboxgl.GeoJSONFeature[] }): void {
    const map = this.map;
    const f = e.features?.[0];
    if (!map || !f) return;
    const id = String(f.properties?.['id']);
    const when = new Date(String(f.properties?.['dateandtime']));
    const t = (k: string) => this.transloco.translate(k);
    const html = `
      <div class="safe-popup">
        <strong>${t('events.event')} <code>${id.slice(-8).toUpperCase()}</code></strong>
        <div>${when.toLocaleString(this.lang(), { dateStyle: 'short', timeStyle: 'short' })}</div>
        <div class="actions">
          <button type="button" class="p-button p-button-sm p-button-text" data-open="${id}">${t('map.open_event')}</button>
          <button type="button" class="p-button p-button-sm p-button-text" disabled title="${t('placeholder.pdf_m5')}">PDF</button>
        </div>
      </div>`;
    this.popup?.remove();
    this.popup = new mapboxgl.Popup({ closeButton: true, maxWidth: '260px' })
      .setLngLat((f.geometry as Point).coordinates as [number, number])
      .setHTML(html)
      .addTo(map);
    this.popup.getElement()?.querySelector<HTMLButtonElement>('button[data-open]')?.addEventListener('click', () => this.openEvent(id));
  }

  openEvent(id: string): void {
    this.selectedEvent.set(id);
    void this.router.navigate([], { queryParams: { event: id }, queryParamsHandling: 'merge' });
  }

  closeDrawer(changed: boolean): void {
    this.selectedEvent.set(null);
    void this.router.navigate([], { queryParams: { event: null }, queryParamsHandling: 'merge' });
    if (changed) void this.loadEvents();
  }

  setStyle(code: StyleCode): void {
    if (code === this.style() || !this.map) return;
    this.style.set(code);
    this.styleReady = false;
    this.popup?.remove();
    this.map.setStyle(this.styleUrl());
    void this.router.navigate([], { queryParams: { style: code === 'winter' ? null : code }, queryParamsHandling: 'merge' });
  }

  toggleLayer(layer: Layer, on: boolean): void {
    const next = on ? [...new Set([...this.layers(), layer])] : this.layers().filter((l) => l !== layer);
    this.layers.set(ALL_LAYERS.filter((l) => next.includes(l)));
    const isDefault = next.length === DEFAULT_LAYERS.length && DEFAULT_LAYERS.every((l) => next.includes(l));
    void this.router.navigate([], { queryParams: { layers: isDefault ? null : this.layers().join(',') }, queryParamsHandling: 'merge' });
  }

  has(layer: Layer): boolean {
    return this.layers().includes(layer);
  }

  recenter(): void {
    this.fitToBoundaries();
  }
}
