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
    const base = (await res.json()) as AppConfig;
    // Override locale opzionale (non versionato): token e valori specifici della postazione.
    let local: Partial<AppConfig> = {};
    try {
      const l = await fetch('config/app-config.local.json', { cache: 'no-store' });
      if (l.ok) local = (await l.json()) as Partial<AppConfig>;
    } catch {
      /* nessun override */
    }
    this.cfg = { ...base, ...local, map: { ...base.map, ...(local.map ?? {}) }, oidc: { ...base.oidc, ...(local.oidc ?? {}) } };
    return this.cfg;
  }
}
