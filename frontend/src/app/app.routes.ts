import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';
import { AppConfigService } from './core/config/app-config';
import { detectLang, langGuard, langMatch } from './core/i18n/lang.guard';
import { HomeComponent } from './features/home/home.component';
import { NotProvisionedComponent } from './features/not-provisioned/not-provisioned.component';
import { PlaceholderComponent } from './features/placeholder/placeholder.component';
import { EventsPageComponent } from './features/data/events/events-page.component';
import { PersonsPageComponent } from './features/data/persons/persons-page.component';
import { ShellComponent } from './layout/shell/shell.component';
import { ZonePageComponent } from './features/stats/zone-page.component';
import { DemographicsPageComponent } from './features/stats/demographics-page.component';
import { TypologyPageComponent } from './features/stats/typology-page.component';
import { GeographyPageComponent } from './features/stats/geography-page.component';
import { WeatherPageComponent } from './features/stats/weather-page.component';
import { SeasonPageComponent } from './features/stats/season-page.component';

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
      { path: 'stats/zone', component: ZonePageComponent, data: { filters: true } },
      { path: 'stats/demographics', component: DemographicsPageComponent, data: { filters: true } },
      { path: 'stats/typology', component: TypologyPageComponent, data: { filters: true } },
      { path: 'stats/geography', component: GeographyPageComponent, data: { filters: true } },
      { path: 'stats/weather', component: WeatherPageComponent, data: { filters: true } },
      { path: 'stats/season', component: SeasonPageComponent, data: { filters: true } },
      { path: 'data/events', component: EventsPageComponent, data: { filters: true } },
      { path: 'data/persons', component: PersonsPageComponent, data: { filters: true } },
      placeholder('map', 'nav.map', 'map.view', 'M4'),
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
