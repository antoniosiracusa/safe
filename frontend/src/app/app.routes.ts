import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';
import { AppConfigService } from './core/config/app-config';
import { detectLang, langGuard, langMatch } from './core/i18n/lang.guard';
import { HomeComponent } from './features/home/home.component';
import { NotProvisionedComponent } from './features/not-provisioned/not-provisioned.component';
import { PlaceholderComponent } from './features/placeholder/placeholder.component';
import { ShellComponent } from './layout/shell/shell.component';

/** Pagine delle milestone successive: già instradate (con permesso e filtri) come segnaposto. */
const placeholder = (
  path: string,
  titleKey: string,
  permission: string,
  milestone: string,
  filters = true,
) => ({ path, component: PlaceholderComponent, data: { titleKey, permission, milestone, filters } });

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    canActivate: [
      () => {
        const cfg = inject(AppConfigService).config;
        return inject(Router).createUrlTree([detectLang(cfg.supportedLocales, cfg.defaultLocale), 'home']);
      },
    ],
    children: [],
  },
  { path: 'not-provisioned', component: NotProvisionedComponent },
  {
    path: ':lang',
    canMatch: [langMatch],
    canActivate: [langGuard, authGuard],
    component: ShellComponent,
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'home' },
      { path: 'home', component: HomeComponent },
      { path: 'stats/zone', loadComponent: () => import('./features/stats/zone-page.component').then((m) => m.ZonePageComponent), data: { filters: true } },
      { path: 'stats/demographics', loadComponent: () => import('./features/stats/demographics-page.component').then((m) => m.DemographicsPageComponent), data: { filters: true } },
      { path: 'stats/typology', loadComponent: () => import('./features/stats/typology-page.component').then((m) => m.TypologyPageComponent), data: { filters: true } },
      { path: 'stats/geography', loadComponent: () => import('./features/stats/geography-page.component').then((m) => m.GeographyPageComponent), data: { filters: true } },
      { path: 'stats/weather', loadComponent: () => import('./features/stats/weather-page.component').then((m) => m.WeatherPageComponent), data: { filters: true } },
      { path: 'stats/season', loadComponent: () => import('./features/stats/season-page.component').then((m) => m.SeasonPageComponent), data: { filters: true } },
      { path: 'data/events', loadComponent: () => import('./features/data/events/events-page.component').then((m) => m.EventsPageComponent), data: { filters: true } },
      { path: 'data/persons', loadComponent: () => import('./features/data/persons/persons-page.component').then((m) => m.PersonsPageComponent), data: { filters: true } },
      { path: 'map', loadComponent: () => import('./features/map/map-page.component').then((m) => m.MapPageComponent), data: { filters: true } },
      placeholder('exports/regional', 'nav.exports_regional', 'exports.regional', 'M5'),
      placeholder('exports/dataset', 'nav.exports_dataset', 'exports.dataset', 'M5'),
      placeholder('admin/users', 'nav.users', 'users.view', 'M6', false),
      placeholder('admin/teams', 'nav.teams', 'teams.view', 'M6', false),
      placeholder('admin/devices', 'nav.devices', 'devices.view', 'M6', false),
      placeholder('admin/territory', 'nav.territory', 'territory.view', 'M6', false),
      placeholder('admin/keys', 'nav.keys', 'crypto.manage_keys', 'M7', false),
      placeholder('admin/audit', 'nav.audit', 'audit.view', 'M7', false),
      { path: '**', redirectTo: 'home' },
    ],
  },
  { path: '**', redirectTo: '' },
];
