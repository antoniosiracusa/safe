import { inject } from '@angular/core';
import { CanActivateFn, CanMatchFn, Router } from '@angular/router';
import { TranslocoService } from '@jsverse/transloco';

import { AppConfigService } from '../config/app-config';

export const LANG_STORAGE_KEY = 'safe.lang';

/** Sceglie la lingua iniziale: preferenza salvata → lingua del browser → default di configurazione. */
export function detectLang(supported: string[], fallback: string): string {
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY);
    if (saved && supported.includes(saved)) return saved;
  } catch {
    /* storage non disponibile */
  }
  const browser = (navigator.language || '').slice(0, 2).toLowerCase();
  return supported.includes(browser) ? browser : fallback;
}

/** Il segmento :lang deve essere una lingua supportata, altrimenti la rotta non corrisponde. */
export const langMatch: CanMatchFn = (_route, segments) => {
  const config = inject(AppConfigService).config;
  return segments.length > 0 && config.supportedLocales.includes(segments[0].path);
};

/** Attiva la lingua della URL e la memorizza. */
export const langGuard: CanActivateFn = (route) => {
  const lang = route.paramMap.get('lang');
  const transloco = inject(TranslocoService);
  const config = inject(AppConfigService).config;
  const router = inject(Router);
  if (!lang || !config.supportedLocales.includes(lang)) {
    return router.createUrlTree([detectLang(config.supportedLocales, config.defaultLocale), 'home']);
  }
  transloco.setActiveLang(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    /* ignora */
  }
  return true;
};
