import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';
import { AppConfigService } from './core/config/app-config';
import { detectLang, langGuard, langMatch } from './core/i18n/lang.guard';
import { HomeComponent } from './features/home/home.component';
import { NotProvisionedComponent } from './features/not-provisioned/not-provisioned.component';
import { ShellComponent } from './layout/shell/shell.component';

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
      { path: 'pista', loadComponent: () => import('./features/pista/pista-page.component').then((m) => m.PistaPageComponent), data: { filters: false } },
      { path: 'stats/zone', loadComponent: () => import('./features/stats/zone-page.component').then((m) => m.ZonePageComponent), data: { filters: true } },
      { path: 'stats/demographics', loadComponent: () => import('./features/stats/demographics-page.component').then((m) => m.DemographicsPageComponent), data: { filters: true } },
      { path: 'stats/typology', loadComponent: () => import('./features/stats/typology-page.component').then((m) => m.TypologyPageComponent), data: { filters: true } },
      { path: 'stats/geography', loadComponent: () => import('./features/stats/geography-page.component').then((m) => m.GeographyPageComponent), data: { filters: true } },
      { path: 'stats/weather', loadComponent: () => import('./features/stats/weather-page.component').then((m) => m.WeatherPageComponent), data: { filters: true } },
      { path: 'stats/season', loadComponent: () => import('./features/stats/season-page.component').then((m) => m.SeasonPageComponent), data: { filters: true } },
      { path: 'data/events', loadComponent: () => import('./features/data/events/events-page.component').then((m) => m.EventsPageComponent), data: { filters: true } },
      { path: 'data/persons', loadComponent: () => import('./features/data/persons/persons-page.component').then((m) => m.PersonsPageComponent), data: { filters: true } },
      { path: 'map', loadComponent: () => import('./features/map/map-page.component').then((m) => m.MapPageComponent), data: { filters: true } },
      { path: 'exports/regional', loadComponent: () => import('./features/exports/regional-page.component').then((m) => m.RegionalPageComponent), data: { filters: false } },
      { path: 'exports/dataset', loadComponent: () => import('./features/exports/dataset-page.component').then((m) => m.DatasetPageComponent), data: { filters: true } },
      { path: 'admin/users', loadComponent: () => import('./features/admin/users-page.component').then((m) => m.UsersPageComponent) },
      { path: 'admin/teams', loadComponent: () => import('./features/admin/teams-page.component').then((m) => m.TeamsPageComponent) },
      { path: 'admin/devices', loadComponent: () => import('./features/admin/devices-page.component').then((m) => m.DevicesPageComponent) },
      { path: 'admin/territory', loadComponent: () => import('./features/admin/territory-page.component').then((m) => m.TerritoryPageComponent) },
      { path: 'admin/lookups', loadComponent: () => import('./features/admin/lookups-page.component').then((m) => m.LookupsPageComponent) },
      { path: 'admin/settings', loadComponent: () => import('./features/admin/settings-page.component').then((m) => m.SettingsPageComponent) },
      { path: 'admin/keys', loadComponent: () => import('./features/admin/keys-page.component').then((m) => m.KeysPageComponent) },
      { path: 'admin/audit', loadComponent: () => import('./features/admin/audit-page.component').then((m) => m.AuditPageComponent) },
      { path: '**', redirectTo: 'home' },
    ],
  },
  { path: 'offline', loadComponent: () => import('./features/pista/offline-page.component').then((m) => m.OfflinePageComponent) },
  { path: '**', redirectTo: '' },
];
