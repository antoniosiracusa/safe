import { Injectable } from '@angular/core';

/** Configurazione runtime caricata da /config/app-config.json: stesso build in tutti gli ambienti. */
export interface AppConfig {
  version: string;
  oidc: { issuer: string; clientId: string };
  apiBaseUrl: string;
  wsBaseUrl: string;
  map: { provider: 'mapbox'; mapboxToken: string; defaultCenter: [number, number]; defaultZoom: number };
  defaultLocale: string;
  supportedLocales: string[];
}

@Injectable({ providedIn: 'root' })
export class AppConfigService {
  private cfg: AppConfig | null = null;

  get config(): AppConfig {
    if (!this.cfg) {
      throw new Error('AppConfig non caricata: provideAppInitializer mancante');
    }
    return this.cfg;
  }

  async load(): Promise<AppConfig> {
    const res = await fetch('config/app-config.json', { cache: 'no-store' });
    if (!res.ok) {
      throw new Error(`Impossibile caricare la configurazione (${res.status})`);
    }
    this.cfg = (await res.json()) as AppConfig;
    return this.cfg;
  }
}
