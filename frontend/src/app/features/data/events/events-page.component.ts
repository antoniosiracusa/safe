import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';
import { TableLazyLoadEvent, TableModule } from 'primeng/table';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';

import { EventRow } from '../../../core/api/rescue.models';
import { RescueService } from '../../../core/api/rescue.service';
import { CanDirective } from '../../../core/authz/can.directive';
import { FilterStore } from '../../../core/filters/filter.store';
import { LookupLabelPipe } from '../../../core/lookups/lookup-label.pipe';
import { LookupsService } from '../../../core/lookups/lookups.service';
import { SessionService } from '../../../core/session/session.service';
import { TerritoryService } from '../../../core/territory/territory.service';
import { StateTagComponent } from '../../../shared/ui/state-tag.component';
import { EventDrawerComponent } from './event-drawer.component';

const PAGE_SIZE = 50;

@Component({
  selector: 'safe-events-page',
  imports: [
    DatePipe, FormsModule, TranslocoDirective, TableModule, ButtonModule, SelectModule, MultiSelectModule, InputTextModule,
    ToastModule, TooltipModule, CanDirective, LookupLabelPipe, StateTagComponent, EventDrawerComponent,
  ],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './events-page.component.html',
  styleUrl: '../data-page.scss',
})
export class EventsPageComponent {
  readonly session = inject(SessionService);
  readonly lookups = inject(LookupsService);
  readonly territory = inject(TerritoryService);
  private readonly rescue = inject(RescueService);
  private readonly filterStore = inject(FilterStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  readonly rows = signal<EventRow[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly pageSize = PAGE_SIZE;
  readonly first = signal(0);
  readonly sortField = signal<string>('dateandtime');
  readonly sortOrder = signal<number>(-1);

  // filtri specifici della tabella, riflessi nella URL come quelli globali
  readonly cause = signal<string[]>([]);
  readonly slope = signal<string | null>(null);
  readonly locked = signal<string | null>(null);
  readonly search = signal<string>('');

  readonly selected = signal<string | null>(null);
  readonly creating = signal(false);

  readonly lockedOptions = computed(() => [
    { value: 'true', label: this.transloco.translate('state.locked') },
    { value: 'false', label: this.transloco.translate('state.open') },
  ]);
  readonly slopeOptions = computed(() => this.territory.slopeOptions(this.filterStore.filters().zone, this.filterStore.filters().ski_area));

  private version = 0;

  constructor() {
    void this.lookups.load();
    void this.territory.load();
    const qp = this.route.snapshot.queryParamMap;
    this.cause.set(qp.getAll('cause'));
    this.slope.set(qp.get('slope'));
    this.locked.set(qp.get('locked'));
    this.search.set(qp.get('search') ?? '');
    if (qp.get('event')) this.selected.set(qp.get('event'));
    // ricarica quando cambiano i filtri globali
    effect(() => {
      this.filterStore.httpParams();
      untracked(() => this.reload(true));
    });
  }

  onLazyLoad(e: TableLazyLoadEvent): void {
    this.first.set(e.first ?? 0);
    if (e.sortField && typeof e.sortField === 'string') this.sortField.set(e.sortField);
    if (e.sortOrder) this.sortOrder.set(e.sortOrder);
    this.reload(false);
  }

  reload(resetPage: boolean): void {
    if (resetPage) this.first.set(0);
    const v = ++this.version;
    this.loading.set(true);
    this.error.set(false);
    const page = Math.floor(this.first() / PAGE_SIZE) + 1;
    const ordering = `${this.sortOrder() < 0 ? '-' : ''}${this.sortField().replace('.', '__')}`;
    this.rescue
      .listEvents(this.filterStore.httpParams(), { page, page_size: PAGE_SIZE, ordering }, {
        cause: this.cause(), slope: this.slope(), locked: this.locked(), search: this.search() || null,
      })
      .subscribe({
        next: (res) => {
          if (v !== this.version) return;
          this.rows.set(res.results);
          this.total.set(res.count);
          this.loading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          if (v !== this.version) return;
          this.loading.set(false);
          if (err.status !== 403) this.error.set(true);
        },
      });
  }

  applyLocalFilters(): void {
    void this.router.navigate([], {
      queryParams: { cause: this.cause().length ? this.cause() : null, slope: this.slope(), locked: this.locked(), search: this.search() || null },
      queryParamsHandling: 'merge',
    });
    this.reload(true);
  }

  clearLocalFilters(): void {
    this.cause.set([]);
    this.slope.set(null);
    this.locked.set(null);
    this.search.set('');
    this.applyLocalFilters();
  }

  open(row: EventRow): void {
    this.selected.set(row.id);
    void this.router.navigate([], { queryParams: { event: row.id }, queryParamsHandling: 'merge' });
  }

  closeDrawer(changed: boolean): void {
    this.selected.set(null);
    this.creating.set(false);
    void this.router.navigate([], { queryParams: { event: null }, queryParamsHandling: 'merge' });
    if (changed) this.reload(false);
  }

  onCreated(id: string): void {
    this.messages.add({ severity: 'success', summary: this.transloco.translate('events.created') });
    this.creating.set(false);
    this.selected.set(id);
    this.reload(true);
  }

  shortId(id: string): string {
    return id.slice(-8).toUpperCase();
  }
}
