import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import { TableLazyLoadEvent, TableModule } from 'primeng/table';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';

import { Person } from '../../../core/api/rescue.models';
import { RescueService } from '../../../core/api/rescue.service';
import { CanDirective } from '../../../core/authz/can.directive';
import { FilterStore } from '../../../core/filters/filter.store';
import { LookupLabelPipe } from '../../../core/lookups/lookup-label.pipe';
import { LookupsService } from '../../../core/lookups/lookups.service';
import { SessionService } from '../../../core/session/session.service';
import { StateTagComponent } from '../../../shared/ui/state-tag.component';
import { EventDrawerComponent } from '../events/event-drawer.component';

const PAGE_SIZE = 50;

@Component({
  selector: 'safe-persons-page',
  imports: [DatePipe, FormsModule, TranslocoDirective, TableModule, ButtonModule, SelectModule, InputNumberModule, ToastModule, TooltipModule, CanDirective, LookupLabelPipe, StateTagComponent, EventDrawerComponent],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './persons-page.component.html',
  styleUrl: '../data-page.scss',
})
export class PersonsPageComponent {
  readonly session = inject(SessionService);
  readonly lookups = inject(LookupsService);
  private readonly rescue = inject(RescueService);
  private readonly filterStore = inject(FilterStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);

  readonly rows = signal<Person[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly pageSize = PAGE_SIZE;
  readonly first = signal(0);
  readonly sortField = signal('event.dateandtime');
  readonly sortOrder = signal(-1);

  readonly gender = signal<string | null>(null);
  readonly country = signal<string | null>(null);
  readonly diagnosis = signal<string | null>(null);
  readonly equipment = signal<string | null>(null);
  readonly evacuation = signal<string | null>(null);
  readonly ageMin = signal<number | null>(null);
  readonly ageMax = signal<number | null>(null);

  readonly selectedEvent = signal<string | null>(null);
  readonly yesNo = computed(() => [
    { value: 'true', label: this.transloco.translate('common.yes') },
    { value: 'false', label: this.transloco.translate('common.no') },
  ]);

  private version = 0;

  constructor() {
    void this.lookups.load();
    const qp = this.route.snapshot.queryParamMap;
    this.gender.set(qp.get('gender'));
    this.country.set(qp.get('country_code'));
    this.diagnosis.set(qp.get('diagnosis'));
    this.equipment.set(qp.get('equipment'));
    this.evacuation.set(qp.get('evacuation_mean'));
    this.ageMin.set(qp.get('age_min') ? Number(qp.get('age_min')) : null);
    this.ageMax.set(qp.get('age_max') ? Number(qp.get('age_max')) : null);
    if (qp.get('event')) this.selectedEvent.set(qp.get('event'));
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
      .listPersons(this.filterStore.httpParams(), { page, page_size: PAGE_SIZE, ordering }, {
        gender: this.gender(), country_code: this.country(), diagnosis: this.diagnosis(), equipment: this.equipment(),
        evacuation_mean: this.evacuation(),
        age_min: this.ageMin() !== null ? String(this.ageMin()) : null,
        age_max: this.ageMax() !== null ? String(this.ageMax()) : null,
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
      queryParams: {
        gender: this.gender(), country_code: this.country(), diagnosis: this.diagnosis(), equipment: this.equipment(),
        evacuation_mean: this.evacuation(), age_min: this.ageMin(), age_max: this.ageMax(),
      },
      queryParamsHandling: 'merge',
    });
    this.reload(true);
  }

  clearLocalFilters(): void {
    this.gender.set(null);
    this.country.set(null);
    this.diagnosis.set(null);
    this.equipment.set(null);
    this.evacuation.set(null);
    this.ageMin.set(null);
    this.ageMax.set(null);
    this.applyLocalFilters();
  }

  open(row: Person): void {
    this.selectedEvent.set(row.event_id);
    void this.router.navigate([], { queryParams: { event: row.event_id }, queryParamsHandling: 'merge' });
  }

  closeDrawer(changed: boolean): void {
    this.selectedEvent.set(null);
    void this.router.navigate([], { queryParams: { event: null }, queryParamsHandling: 'merge' });
    if (changed) this.reload(false);
  }

  means(p: Person): string[] {
    return [...p.evacuation_means].sort((a, b) => a.order - b.order).map((m) => m.mean);
  }

  shortId(id: string): string {
    return id.slice(-8).toUpperCase();
  }
}
