import { Injectable, inject } from '@angular/core';
import mapboxgl from 'mapbox-gl';

import { AppConfigService } from '../config/app-config';

export interface MapStyle {
  code: 'winter' | 'summer' | 'satellite';
  label_key: string;
  url: string;
  terrain: boolean;
}

export const DIFFICULTY_COLORS: Record<string, string> = {
  ski_school: '#2f9e44',
  blue: '#1c7ed6',
  red: '#e03131',
  black: '#212529',
  unclassified: '#868e96',
};

/** Accesso a Mapbox GL JS: token da configurazione runtime, stili dal server. */
@Injectable({ providedIn: 'root' })
export class MapboxService {
  private readonly config = inject(AppConfigService);

  get token(): string {
    return this.config.config.map?.mapboxToken ?? '';
  }

  get configured(): boolean {
    return this.token.startsWith('pk.');
  }

  get defaultCenter(): [number, number] {
    return this.config.config.map?.defaultCenter ?? [12.1, 46.45];
  }

  get defaultZoom(): number {
    return this.config.config.map?.defaultZoom ?? 11;
  }

  /** Crea una mappa. Il token viene passato per istanza, mai salvato in storage. */
  create(container: HTMLElement, style: string, options: Partial<mapboxgl.MapOptions> = {}): mapboxgl.Map {
    return new mapboxgl.Map({
      container,
      style,
      accessToken: this.token,
      center: this.defaultCenter,
      zoom: this.defaultZoom,
      attributionControl: true,
      cooperativeGestures: false,
      ...options,
    });
  }

  /** Rilievo e ombreggiatura (stile invernale): DEM Mapbox + hillshade. */
  addTerrain(map: mapboxgl.Map): void {
    if (map.getSource('mapbox-dem')) return;
    map.addSource('mapbox-dem', { type: 'raster-dem', url: 'mapbox://mapbox.mapbox-terrain-dem-v1', tileSize: 512, maxzoom: 14 });
    map.addLayer({ id: 'safe-hillshade', type: 'hillshade', source: 'mapbox-dem', paint: { 'hillshade-exaggeration': 0.35, 'hillshade-shadow-color': '#5c6b7a' } }, firstSymbolLayer(map));
  }
}

export function firstSymbolLayer(map: mapboxgl.Map): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === 'symbol')?.id;
}
