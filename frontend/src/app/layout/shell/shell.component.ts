import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { TooltipModule } from 'primeng/tooltip';
import { filter, map, startWith } from 'rxjs/operators';

import { AuthService } from '../../core/auth/auth.service';
import { AppConfigService } from '../../core/config/app-config';
import { FilterStore } from '../../core/filters/filter.store';
import { SessionService } from '../../core/session/session.service';
import { KeyStoreService } from '../../core/crypto/key-store.service';
import { OfflineQueueService } from '../../core/pwa/offline-queue.service';
import { PwaService } from '../../core/pwa/pwa.service';
import { FilterBarComponent } from '../filter-bar/filter-bar.component';
import { KeyDialogComponent } from '../key-dialog/key-dialog.component';

export interface NavItem {
  path: string;
  labelKey: string;
  icon: string;
  permission?: string;
}
export interface NavSection {
  labelKey: string;
  items: NavItem[];
}

/** Menu laterale: le voci restano visibili anche senza permesso (icona lucchetto), come da specifica. */
export const NAV: NavSection[] = [
  { labelKey: 'nav.home', items: [{ path: 'home', labelKey: 'nav.home', icon: 'pi pi-home' }] },
  { labelKey: 'nav.pista', items: [{ path: 'pista', labelKey: 'nav.pista', icon: 'pi pi-mobile', permission: 'events.create' }] },
  {
    labelKey: 'nav.stats',
    items: [
      { path: 'stats/zone', labelKey: 'nav.stats_zone', icon: 'pi pi-chart-bar', permission: 'stats.view' },
      { path: 'stats/demographics', labelKey: 'nav.stats_demographics', icon: 'pi pi-users', permission: 'stats.view' },
      { path: 'stats/typology', labelKey: 'nav.stats_typology', icon: 'pi pi-tags', permission: 'stats.view' },
      { path: 'stats/geography', labelKey: 'nav.stats_geography', icon: 'pi pi-map-marker', permission: 'stats.view' },
      { path: 'stats/weather', labelKey: 'nav.stats_weather', icon: 'pi pi-cloud', permission: 'stats.view' },
      { path: 'stats/season', labelKey: 'nav.stats_season', icon: 'pi pi-calendar', permission: 'stats.advanced' },
    ],
  },
  {
    labelKey: 'nav.data',
    items: [
      { path: 'data/events', labelKey: 'nav.events', icon: 'pi pi-list', permission: 'events.view' },
      { path: 'data/persons', labelKey: 'nav.persons', icon: 'pi pi-id-card', permission: 'persons.view' },
    ],
  },
  { labelKey: 'nav.map', items: [{ path: 'map', labelKey: 'nav.map', icon: 'pi pi-map', permission: 'map.view' }] },
  {
    labelKey: 'nav.exports',
    items: [
      { path: 'exports/regional', labelKey: 'nav.exports_regional', icon: 'pi pi-building', permission: 'exports.regional' },
      { path: 'exports/dataset', labelKey: 'nav.exports_dataset', icon: 'pi pi-file-excel', permission: 'exports.dataset' },
    ],
  },
  {
    labelKey: 'nav.admin',
    items: [
      { path: 'admin/users', labelKey: 'nav.users', icon: 'pi pi-user', permission: 'users.view' },
      { path: 'admin/teams', labelKey: 'nav.teams', icon: 'pi pi-sitemap', permission: 'teams.view' },
      { path: 'admin/devices', labelKey: 'nav.devices', icon: 'pi pi-mobile', permission: 'devices.view' },
      { path: 'admin/territory', labelKey: 'nav.territory', icon: 'pi pi-compass', permission: 'territory.view' },
      { path: 'admin/lookups', labelKey: 'nav.lookups', icon: 'pi pi-book', permission: 'lookups.manage' },
      { path: 'admin/settings', labelKey: 'nav.settings', icon: 'pi pi-cog', permission: 'company.settings' },
      { path: 'admin/keys', labelKey: 'nav.keys', icon: 'pi pi-key', permission: 'crypto.manage_keys' },
      { path: 'admin/audit', labelKey: 'nav.audit', icon: 'pi pi-history', permission: 'audit.view' },
    ],
  },
];

@Component({
  selector: 'safe-shell',
  imports: [
    FormsModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    TranslocoDirective,
    ButtonModule,
    SelectModule,
    TooltipModule,
    FilterBarComponent,
    KeyDialogComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent {
  readonly session = inject(SessionService);
  readonly auth = inject(AuthService);
  readonly config = inject(AppConfigService);
  readonly filterStore = inject(FilterStore);
  readonly keyStore = inject(KeyStoreService);
  readonly pwa = inject(PwaService);
  readonly queue = inject(OfflineQueueService);
  readonly keyDialog = signal(false);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly transloco = inject(TranslocoService);

  readonly nav = NAV;
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });
  readonly langOptions = this.config.config.supportedLocales.map((l) => ({ value: l, label: l.toUpperCase() }));
  /** Sui telefoni (M8) il menu parte chiuso e si richiude dopo ogni navigazione: non deve coprire la pagina. */
  readonly sidebarOpen = signal(window.innerWidth > 900);

  closeSidebarOnPhone(): void {
    if (window.innerWidth <= 900) this.sidebarOpen.set(false);
  }
  readonly version = this.config.config.version;
  readonly brand = this.config.config.brand ?? {};

  /** La barra filtri compare solo sulle pagine che la dichiarano (data.filters = true). */
  readonly showFilters = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      startWith(null),
      map(() => {
        let r: ActivatedRoute | null = this.route;
        let show = false;
        while (r) {
          if (r.snapshot?.data?.['filters']) show = true;
          r = r.firstChild;
        }
        return show;
      }),
    ),
    { initialValue: false },
  );

  readonly keyState = computed(() => {
    const ks = this.session.keyStatus();
    if (!ks) return 'none';
    if (ks.grant === 'active') return 'granted';
    if (ks.user_key === 'present') return 'nogrant';
    return 'nokey';
  });

  /** ['/', lang, ...segmenti]: i percorsi con "/" vanno divisi, altrimenti la barra viene codificata. */
  link(path: string): string[] {
    return ['/', this.lang(), ...path.split('/')];
  }

  changeLang(lang: string): void {
    const tree = this.router.parseUrl(this.router.url);
    const segments = tree.root.children['primary']?.segments ?? [];
    if (segments.length) segments[0].path = lang;
    void this.router.navigateByUrl(tree);
    void this.session.setLocale(lang).catch(() => undefined);
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((v) => !v);
  }

  logout(): void {
    this.keyStore.lock();
    this.auth.logout();
  }
}
