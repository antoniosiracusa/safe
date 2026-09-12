import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { toSignal } from '@angular/core/rxjs-interop';

import { HttpParams } from '@angular/common/http';
import { ButtonModule } from 'primeng/button';
import { GeneralKpi, StatsService } from '../../core/api/stats.service';
import { PwaService } from '../../core/pwa/pwa.service';
import { SessionService } from '../../core/session/session.service';
import { signal } from '@angular/core';

interface ModuleCard {
  path: string;
  labelKey: string;
  descKey: string;
  icon: string;
  permission: string;
}

const MODULES: ModuleCard[] = [
  { path: 'pista', labelKey: 'pista.title', descKey: 'pista.intro', icon: 'pi pi-mobile', permission: 'events.create' },
  { path: 'stats/zone', labelKey: 'nav.stats', descKey: 'home.stats_desc', icon: 'pi pi-chart-bar', permission: 'stats.view' },
  { path: 'data/events', labelKey: 'nav.data', descKey: 'home.data_desc', icon: 'pi pi-list', permission: 'events.view' },
  { path: 'map', labelKey: 'nav.map', descKey: 'home.map_desc', icon: 'pi pi-map', permission: 'map.view' },
  { path: 'exports/regional', labelKey: 'nav.exports', descKey: 'home.exports_desc', icon: 'pi pi-building', permission: 'exports.regional' },
  { path: 'admin/users', labelKey: 'nav.admin', descKey: 'home.admin_desc', icon: 'pi pi-cog', permission: 'users.view' },
];

@Component({
  selector: 'safe-home',
  imports: [RouterLink, TranslocoDirective, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('home.welcome', { name: session.displayName() }) }}</h1>
      <p class="sub">{{ session.company()?.name }}</p>

      <section class="facts" [attr.aria-label]="t('home.session')">
        @if (kpi(); as k) {
          <div><span class="k">{{ t('home.kpi_season', { season: k.current_season }) }}</span><span class="v">{{ k.current_season_events }}</span></div>
          <div><span class="k">{{ t('home.kpi_events') }}</span><span class="v">{{ k.total_events }}</span></div>
          <div><span class="k">{{ t('home.kpi_persons') }}</span><span class="v">{{ k.total_persons }}</span></div>
          <div><span class="k">{{ t('home.kpi_invalid') }}</span><span class="v">{{ k.invalid_events }}</span></div>
        }
        <div><span class="k">{{ t('home.teams') }}</span><span class="v">{{ session.teams().length }}</span></div>
        <div><span class="k">{{ t('home.permissions') }}</span><span class="v">{{ activePermissions() }}</span></div>
        <div>
          <span class="k">{{ t('home.key') }}</span>
          <span class="v small">{{ t('shell.key_' + keyState()) }}</span>
        </div>
      </section>

      @if (!pwa.standalone()) {
        <section class="install" [attr.aria-label]="t('pwa.install_title')">
          <i class="pi pi-mobile" aria-hidden="true"></i>
          <div>
            <h3>{{ t('pwa.install_title') }}</h3>
            <p>{{ t('pwa.install_desc') }}</p>
            @if (pwa.isIOS) {
              <p class="how">{{ t('pwa.install_ios') }}</p>
            } @else if (pwa.canPromptInstall()) {
              <p-button type="button" [label]="t('pwa.install_button')" icon="pi pi-download" size="small" (onClick)="pwa.promptInstall()" />
            }
          </div>
        </section>
      }

      <h2>{{ t('home.modules') }}</h2>
      <div class="cards">
        @for (m of modules; track m.path) {
          @let allowed = session.can(m.permission);
          <a class="card" [class.locked]="!allowed" [routerLink]="link(m.path)" queryParamsHandling="preserve">
            <i [class]="m.icon" aria-hidden="true"></i>
            <h3>{{ t(m.labelKey) }} @if (!allowed) { <i class="pi pi-lock" aria-hidden="true"></i> }</h3>
            <p>{{ allowed ? t(m.descKey) : t('locked.title') }}</p>
            @if (!allowed) { <p class="hint">{{ t('locked.contact') }}</p> }
          </a>
        }
      </div>
    </ng-container>
  `,
  styles: `
    h1 { margin: 0; font-size: 1.6rem; }
    .sub { margin: 0.2rem 0 1.25rem; color: var(--p-text-muted-color); }
    .facts { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
    .facts div { background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-radius: 6px; padding: 0.75rem 1rem; min-width: 10rem; display: flex; flex-direction: column; gap: 0.2rem; }
    .k { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--p-text-muted-color); }
    .v { font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .v.small { font-size: 1rem; }
    h2 { font-size: 1.1rem; margin: 0 0 0.75rem; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem; }
    .card { display: block; background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-radius: 6px; padding: 1rem; text-decoration: none; color: var(--p-text-color); }
    .card:hover { border-color: var(--p-primary-color); }
    .card:focus-visible { outline: 2px solid var(--p-primary-color); }
    .card i { font-size: 1.4rem; color: #c8102e; }
    .card h3 { margin: 0.5rem 0 0.25rem; font-size: 1rem; display: flex; gap: 0.4rem; align-items: center; }
    .card h3 i { font-size: 0.8rem; color: var(--p-text-muted-color); }
    .card p { margin: 0; font-size: 0.9rem; color: var(--p-text-muted-color); }
    .card.locked { opacity: 0.75; border-style: dashed; }
    .card.locked i:first-child { color: var(--p-text-muted-color); }
    .hint { font-size: 0.8rem !important; margin-top: 0.25rem !important; }
    .install { display: flex; gap: 1rem; align-items: flex-start; background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-left: 4px solid #c8102e; border-radius: 6px; padding: 0.9rem 1rem; margin-bottom: 1.5rem; }
    .install > i { font-size: 1.6rem; color: #c8102e; margin-top: 0.1rem; }
    .install h3 { margin: 0 0 0.25rem; font-size: 1rem; }
    .install p { margin: 0 0 0.4rem; font-size: 0.9rem; color: var(--p-text-muted-color); }
    .install .how { color: var(--p-text-color); }
  `,
})
export class HomeComponent {
  readonly session = inject(SessionService);
  readonly pwa = inject(PwaService);
  private readonly transloco = inject(TranslocoService);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });
  readonly modules = MODULES;
  private readonly stats = inject(StatsService);
  readonly kpi = signal<GeneralKpi | null>(null);

  constructor() {
    this.stats.general(new HttpParams()).subscribe({ next: (k) => this.kpi.set(k), error: () => undefined });
  }

  link(path: string): string[] {
    return ['/', this.lang(), ...path.split('/')];
  }

  activePermissions(): number {
    return Object.values(this.session.permissions()).filter(Boolean).length;
  }

  keyState(): string {
    const ks = this.session.keyStatus();
    if (!ks) return 'none';
    if (ks.grant === 'active') return 'granted';
    return ks.user_key === 'present' ? 'nogrant' : 'nokey';
  }
}
