import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';
import { firstValueFrom } from 'rxjs';

import { EventWrite, PersonWrite, Slope } from '../../core/api/rescue.models';
import { RescueService } from '../../core/api/rescue.service';
import { KeyStoreService } from '../../core/crypto/key-store.service';
import { FilterOptionsService } from '../../core/filters/filter-options.service';
import { LookupsService } from '../../core/lookups/lookups.service';
import { OfflineQueueService, QueuedIntervention } from '../../core/pwa/offline-queue.service';
import { PwaService } from '../../core/pwa/pwa.service';
import { SessionService } from '../../core/session/session.service';
import { MapPickerComponent } from '../../shared/map/map-picker.component';

interface PersonDraft {
  age: number | null;
  gender: string | null;
  country_code: string | null;
  role: string | null;
  diagnosis: string | null;
  injury_place: string | null;
  mean: string | null;
  destination: string | null;
  firstname: string;
  surname: string;
  birth_date: string;
  phone: string;
}

interface Draft {
  dateandtime: string; // datetime-local
  team: string | null;
  zone: string | null;
  slope: string | null;
  location_type: string | null;
  location_description: string;
  cause: string | null;
  event_type: string | null;
  note: string;
  geometry: [number, number] | null;
  gps_accuracy: number | null;
}

/** Data/ora locale nel formato accettato da <input type="datetime-local">. */
function localNow(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}

function emptyPerson(): PersonDraft {
  return { age: null, gender: null, country_code: 'IT', role: null, diagnosis: null, injury_place: null, mean: null, destination: null, firstname: '', surname: '', birth_date: '', phone: '' };
}

/**
 * Modalità pista (M8.1): registrazione rapida dell'intervento dal telefono, in tre passi, con GPS,
 * persona soccorsa essenziale (dati identificativi cifrati sul dispositivo) e coda offline.
 */
@Component({
  selector: 'safe-pista',
  imports: [FormsModule, RouterLink, DatePipe, TranslocoDirective, ButtonModule, InputTextModule, SelectModule, TagModule, TextareaModule, MapPickerComponent],
  template: `
    <ng-container *transloco="let t">
      @if (view() === 'list') {
        <div class="head">
          <h1>{{ t('pista.title') }}</h1>
          @if (queue.pending() > 0) { <p-tag severity="warn" [value]="t('pista.queue', { n: queue.pending() })" /> }
        </div>
        <p class="intro">{{ t('pista.intro') }}</p>
        <p-button class="big" [label]="t('pista.new')" icon="pi pi-plus" size="large" styleClass="w-full" (onClick)="startNew()" />

        <h2>{{ t('pista.today') }}</h2>
        @if (queue.items().length === 0) {
          <p class="muted">{{ t('pista.none') }}</p>
        }
        @for (it of queue.items(); track it.id) {
          <div class="item" [class.error]="it.status === 'error'">
            <div class="row">
              <b>{{ it.event.dateandtime | date: 'dd/MM HH:mm' }}</b>
              <p-tag [severity]="statusSeverity(it)" [value]="t('pista.' + it.status)" />
            </div>
            <div class="row small">
              <span>{{ zoneName(it.event.zone) }}@if (it.event.slope) { · {{ slopeName(it.event.slope) }} }</span>
              <span>{{ it.persons.length }} <i class="pi pi-user" aria-hidden="true"></i></span>
            </div>
            @if (it.status === 'error' && it.last_error) { <p class="err">{{ it.last_error }}</p> }
            <div class="row actions">
              @if (it.status === 'sent' && it.server_id) {
                <a [routerLink]="['/', lang(), 'data', 'events']" [queryParams]="{ event: it.server_id }">{{ t('pista.open_portal') }} · {{ it.server_code }}</a>
              }
              @if (it.status === 'error') {
                <p-button [label]="t('pista.retry')" icon="pi pi-refresh" size="small" [text]="true" (onClick)="queue.retry(it.id)" />
              }
              @if (it.status !== 'sent') {
                <p-button [label]="t('pista.remove_person')" icon="pi pi-trash" size="small" [text]="true" severity="danger" (onClick)="remove(it)" />
              }
            </div>
          </div>
        }
      } @else {
        <div class="head">
          <h1>{{ t('pista.new') }}</h1>
          <span class="steps">{{ step() }}/3</span>
        </div>
        <div class="stepbar"><span [class.on]="step() >= 1">{{ t('pista.step_where') }}</span><span [class.on]="step() >= 2">{{ t('pista.step_what') }}</span><span [class.on]="step() >= 3">{{ t('pista.step_who') }}</span></div>

        @if (step() === 1) {
          <label for="f-zone">{{ t('pista.zone') }}</label>
          <p-select inputId="f-zone" [options]="zoneOptions()" optionLabel="label" optionValue="value" [ngModel]="draft.zone" (ngModelChange)="onZone($event)" [showClear]="true" appendTo="body" styleClass="w-full" />
          <label for="f-slope">{{ t('pista.slope') }}</label>
          <p-select inputId="f-slope" [options]="slopeOptions()" optionLabel="label" optionValue="value" [(ngModel)]="draft.slope" [filter]="slopeOptions().length > 8" [showClear]="true" [placeholder]="t('pista.slope_none')" appendTo="body" styleClass="w-full" />
          @if (!draft.slope) {
            <label for="f-location_type">{{ t('pista.location_type') }}</label>
            <p-select inputId="f-location_type" [options]="lookups.options('location_type')" optionLabel="label" optionValue="value" [(ngModel)]="draft.location_type" [showClear]="true" appendTo="body" styleClass="w-full" />
            <label for="f-location_description">{{ t('pista.location_description') }}</label>
            <input id="f-location_description" pInputText [(ngModel)]="draft.location_description" maxlength="200" class="w-full" />
          }
          <span class="lbl">{{ t('pista.gps') }}</span>
          <div class="gps">
            <p-button [label]="gpsBusy() ? t('pista.gps_wait') : t('pista.gps_get')" icon="pi pi-map-marker" [loading]="gpsBusy()" (onClick)="locate()" />
            <span class="muted">
              @if (gpsError()) { {{ t('pista.gps_error') }} }
              @else if (draft.geometry && draft.gps_accuracy !== null) {
                {{ draft.gps_accuracy > 50 ? t('pista.gps_poor', { m: draft.gps_accuracy }) : t('pista.gps_ok', { m: draft.gps_accuracy }) }}
              } @else if (!draft.geometry) { {{ t('pista.gps_missing') }} }
            </span>
          </div>
          <safe-map-picker [value]="draft.geometry" (changed)="draft.geometry = $event" />
        }

        @if (step() === 2) {
          <label for="f-when">{{ t('pista.when') }} *</label>
          <input id="f-when" type="datetime-local" [(ngModel)]="draft.dateandtime" class="native w-full" />
          <label for="f-team">{{ t('pista.team') }} *</label>
          <p-select inputId="f-team" [options]="teamOptions()" optionLabel="label" optionValue="value" [(ngModel)]="draft.team" appendTo="body" styleClass="w-full" />
          <label for="f-cause">{{ t('pista.cause') }}</label>
          <p-select inputId="f-cause" [options]="lookups.options('cause')" optionLabel="label" optionValue="value" [(ngModel)]="draft.cause" [filter]="true" [showClear]="true" appendTo="body" styleClass="w-full" />
          <label for="f-event_type">{{ t('pista.event_type') }}</label>
          <p-select inputId="f-event_type" [options]="lookups.options('event_type')" optionLabel="label" optionValue="value" [(ngModel)]="draft.event_type" [showClear]="true" appendTo="body" styleClass="w-full" />
          <label for="f-note">{{ t('pista.note') }}</label>
          <textarea id="f-note" pTextarea [(ngModel)]="draft.note" rows="2" maxlength="300" class="w-full"></textarea>
          <p class="muted small">{{ t('pista.note_hint') }}</p>
        }

        @if (step() === 3) {
          <h2>{{ t('pista.persons') }}</h2>
          @if (persons.length === 0) { <p class="muted">{{ t('pista.no_persons') }}</p> }
          @for (p of persons; track $index; let i = $index) {
            <div class="person">
              <div class="row"><b>{{ t('pista.person_n', { n: i + 1 }) }}</b><p-button icon="pi pi-trash" [text]="true" size="small" severity="danger" (onClick)="persons.splice(i, 1)" /></div>
              <div class="grid2">
                <div><label [attr.for]="'p-age-' + i">{{ t('pista.age') }}</label><input [id]="'p-age-' + i" type="number" inputmode="numeric" min="0" max="120" [(ngModel)]="p.age" class="native w-full" /></div>
                <div><label [attr.for]="'p-gender-' + i">{{ t('pista.gender') }}</label><p-select [inputId]="'p-gender-' + i" [options]="lookups.options('gender')" optionLabel="label" optionValue="value" [(ngModel)]="p.gender" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-country-' + i">{{ t('pista.country') }}</label><p-select [inputId]="'p-country-' + i" [options]="lookups.countryOptions()" optionLabel="label" optionValue="value" [(ngModel)]="p.country_code" [filter]="true" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-role-' + i">{{ t('pista.role') }}</label><p-select [inputId]="'p-role-' + i" [options]="lookups.options('person_role')" optionLabel="label" optionValue="value" [(ngModel)]="p.role" [showClear]="true" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-diagnosis-' + i">{{ t('pista.diagnosis') }}</label><p-select [inputId]="'p-diagnosis-' + i" [options]="lookups.options('diagnosis')" optionLabel="label" optionValue="value" [(ngModel)]="p.diagnosis" [filter]="true" [showClear]="true" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-injury_place-' + i">{{ t('pista.injury_place') }}</label><p-select [inputId]="'p-injury_place-' + i" [options]="lookups.options('injury_place')" optionLabel="label" optionValue="value" [(ngModel)]="p.injury_place" [showClear]="true" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-mean-' + i">{{ t('pista.mean') }}</label><p-select [inputId]="'p-mean-' + i" [options]="lookups.options('evacuation_mean')" optionLabel="label" optionValue="value" [(ngModel)]="p.mean" [showClear]="true" appendTo="body" styleClass="w-full" /></div>
                <div><label [attr.for]="'p-destination-' + i">{{ t('pista.destination') }}</label><p-select [inputId]="'p-destination-' + i" [options]="lookups.options('destination')" optionLabel="label" optionValue="value" [(ngModel)]="p.destination" [showClear]="true" appendTo="body" styleClass="w-full" /></div>
              </div>
              <h3><i class="pi pi-lock" aria-hidden="true"></i> {{ t('pista.identity') }}</h3>
              @if (identityAvailable()) {
                <p class="muted small">{{ t('pista.identity_hint') }}</p>
                <div class="grid2">
                  <div><label [attr.for]="'p-firstname-' + i">{{ t('pista.firstname') }}</label><input [id]="'p-firstname-' + i" pInputText [(ngModel)]="p.firstname" autocomplete="off" class="w-full" /></div>
                  <div><label [attr.for]="'p-surname-' + i">{{ t('pista.surname') }}</label><input [id]="'p-surname-' + i" pInputText [(ngModel)]="p.surname" autocomplete="off" class="w-full" /></div>
                  <div><label [attr.for]="'p-birth_date-' + i">{{ t('pista.birth_date') }}</label><input [id]="'p-birth_date-' + i" type="date" [(ngModel)]="p.birth_date" class="native w-full" /></div>
                  <div><label [attr.for]="'p-phone-' + i">{{ t('pista.phone') }}</label><input [id]="'p-phone-' + i" type="tel" [(ngModel)]="p.phone" autocomplete="off" class="native w-full" /></div>
                </div>
              } @else {
                <p class="muted small">{{ t('pista.identity_unavailable') }}</p>
              }
            </div>
          }
          <p-button [label]="t('pista.add_person')" icon="pi pi-user-plus" [outlined]="true" styleClass="w-full" (onClick)="persons.push(newPerson())" />
        }

        @if (error()) { <p class="err">{{ error() }}</p> }
        <div class="footer">
          <p-button [label]="t('pista.back')" icon="pi pi-arrow-left" severity="secondary" [outlined]="true" (onClick)="back()" />
          @if (step() < 3) {
            <p-button [label]="t('pista.next')" icon="pi pi-arrow-right" iconPos="right" (onClick)="step.set(step() + 1)" />
          } @else {
            <p-button [label]="t('pista.save')" icon="pi pi-send" [loading]="saving()" (onClick)="save()" />
          }
        </div>
      }
    </ng-container>
  `,
  styles: `
    :host { display: block; max-width: 560px; margin: 0 auto; padding-bottom: 5rem; }
    .head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
    h1 { margin: 0; font-size: 1.4rem; }
    h2 { font-size: 1.05rem; margin: 1.25rem 0 0.5rem; }
    h3 { font-size: 0.95rem; margin: 0.9rem 0 0.2rem; display: flex; gap: 0.4rem; align-items: center; }
    .intro { color: var(--p-text-muted-color); margin: 0.25rem 0 1rem; }
    .muted { color: var(--p-text-muted-color); }
    .small { font-size: 0.85rem; }
    .err { color: #b00020; font-size: 0.9rem; }
    label, .lbl { display: block; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--p-text-muted-color); margin: 0.8rem 0 0.25rem; }
    .w-full { width: 100%; }
    .native { padding: 0.65rem 0.75rem; border: 1px solid var(--p-surface-300); border-radius: 6px; font: inherit; background: var(--p-surface-0); }
    .steps { color: var(--p-text-muted-color); }
    .stepbar { display: flex; gap: 0.4rem; margin: 0.5rem 0 0.25rem; }
    .stepbar span { flex: 1; text-align: center; font-size: 0.8rem; padding: 0.3rem; border-radius: 999px; background: var(--p-surface-100); color: var(--p-text-muted-color); }
    .stepbar span.on { background: #c8102e; color: #fff; }
    .gps { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 0.75rem; }
    .grid2 label { margin-top: 0.6rem; }
    .person, .item { background: var(--p-surface-0); border: 1px solid var(--p-surface-200); border-radius: 8px; padding: 0.75rem 0.9rem; margin-bottom: 0.75rem; }
    .item.error { border-color: #e5a4a4; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
    .row.small { font-size: 0.85rem; color: var(--p-text-muted-color); margin-top: 0.2rem; }
    .row.actions { justify-content: flex-end; margin-top: 0.3rem; }
    .row.actions a { margin-right: auto; font-size: 0.9rem; }
    .footer { position: fixed; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; gap: 0.5rem; padding: 0.6rem 1rem calc(0.6rem + env(safe-area-inset-bottom)); background: var(--p-surface-0); border-top: 1px solid var(--p-surface-200); z-index: 5; }
    :host ::ng-deep .big .p-button { font-size: 1.1rem; padding: 0.9rem; }
    @media (max-width: 480px) { .grid2 { grid-template-columns: 1fr; } }
  `,
})
export class PistaPageComponent {
  readonly session = inject(SessionService);
  readonly lookups = inject(LookupsService);
  readonly queue = inject(OfflineQueueService);
  readonly pwa = inject(PwaService);
  private readonly filterOptions = inject(FilterOptionsService);
  private readonly rescue = inject(RescueService);
  private readonly keyStore = inject(KeyStoreService);
  private readonly transloco = inject(TranslocoService);
  readonly lang = toSignal(this.transloco.langChanges$, { initialValue: this.transloco.getActiveLang() });

  readonly view = signal<'list' | 'new'>('list');
  readonly step = signal(1);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly gpsBusy = signal(false);
  readonly gpsError = signal(false);
  private readonly slopes = signal<Slope[]>([]);
  readonly identityAvailable = computed(() => !!this.keyStore.companyKey());

  draft: Draft = this.emptyDraft();
  persons: PersonDraft[] = [];

  readonly teamOptions = computed(() => this.session.teams().map((t) => ({ value: t.id, label: t.name })));
  readonly zoneOptions = computed(() => this.filterOptions.options().zones.map((z) => ({ value: z.value, label: z.label })));
  readonly slopeOptions = computed(() => {
    const zone = this.draftZone();
    return this.slopes()
      .filter((s) => !zone || s.zone.id === zone)
      .map((s) => ({ value: s.id, label: s.regional_code ? `${s.name} (${s.regional_code})` : s.name }));
  });
  private readonly draftZone = signal<string | null>(null);

  constructor() {
    // dati di riferimento: in rete dal server, senza rete dalla cache del service worker
    void Promise.allSettled([
      this.filterOptions.load(),
      this.lookups.load(),
      firstValueFrom(this.rescue.slopes()).then((s) => this.slopes.set(s)),
      this.keyStore.loadCompanyKey(),
    ]);
  }

  private emptyDraft(): Draft {
    const def = this.session.teams().find((t) => t.is_default) ?? this.session.teams()[0];
    return { dateandtime: localNow(), team: def?.id ?? null, zone: null, slope: null, location_type: null, location_description: '', cause: null, event_type: null, note: '', geometry: null, gps_accuracy: null };
  }

  newPerson(): PersonDraft {
    return emptyPerson();
  }

  onZone(zone: string | null): void {
    this.draft.zone = zone;
    this.draft.slope = null;
    this.draftZone.set(zone);
  }

  startNew(): void {
    this.draft = this.emptyDraft();
    this.persons = [];
    this.draftZone.set(null);
    this.error.set(null);
    this.gpsError.set(false);
    this.step.set(1);
    this.view.set('new');
    void this.locate();
  }

  back(): void {
    if (this.step() > 1) this.step.set(this.step() - 1);
    else this.view.set('list');
  }

  /** Posizione GPS una sola volta, alta precisione; l'utente può correggerla sulla mappa. */
  async locate(): Promise<void> {
    if (!('geolocation' in navigator)) {
      this.gpsError.set(true);
      return;
    }
    this.gpsBusy.set(true);
    this.gpsError.set(false);
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }),
      );
      this.draft.geometry = [Number(pos.coords.longitude.toFixed(6)), Number(pos.coords.latitude.toFixed(6))];
      this.draft.gps_accuracy = Math.round(pos.coords.accuracy);
    } catch {
      this.gpsError.set(true);
    } finally {
      this.gpsBusy.set(false);
    }
  }

  statusSeverity(it: QueuedIntervention): 'success' | 'warn' | 'danger' | 'info' {
    return it.status === 'sent' ? 'success' : it.status === 'error' ? 'danger' : it.status === 'sending' ? 'info' : 'warn';
  }

  zoneName(id: string | null | undefined): string {
    return this.filterOptions.options().zones.find((z) => z.value === id)?.label ?? '';
  }

  slopeName(id: string): string {
    return this.slopes().find((s) => s.id === id)?.name ?? '';
  }

  async remove(it: QueuedIntervention): Promise<void> {
    if (!confirm(this.transloco.translate('pista.delete_confirm'))) return;
    await this.queue.remove(it.id);
  }

  async save(): Promise<void> {
    this.error.set(null);
    const d = this.draft;
    if (!d.dateandtime || !d.team || (!d.zone && !d.location_type)) {
      this.error.set(this.transloco.translate('pista.required'));
      return;
    }
    this.saving.set(true);
    try {
      const zone = this.filterOptions.options().zones.find((z) => z.value === d.zone);
      const event: EventWrite = {
        dateandtime: new Date(d.dateandtime).toISOString(),
        team: d.team,
        ski_area: zone?.ski_area ?? null,
        zone: d.zone,
        slope: d.slope,
        location_type: d.slope ? null : d.location_type,
        location_description: d.slope ? '' : d.location_description.trim(),
        geometry: d.geometry ? { type: 'Point', coordinates: d.geometry } : null,
        cause: d.cause,
        note: d.note.trim(),
        extended: d.event_type ? { event_type: d.event_type } : undefined,
      };
      const persons: PersonWrite[] = [];
      for (const p of this.persons) {
        const identity: Record<string, string> = { firstname: p.firstname, surname: p.surname, birth_date: p.birth_date, phone: p.phone };
        const hasIdentity = Object.values(identity).some((v) => v && v.trim());
        const pii = hasIdentity && this.identityAvailable() ? await this.keyStore.encryptIdentity(identity) : null;
        persons.push({
          age: p.age,
          gender: p.gender,
          country_code: p.country_code,
          role: p.role,
          diagnosis: p.diagnosis,
          injury_place: p.injury_place,
          evacuation_means: p.mean ? [{ mean: p.mean, order: 1 }] : [],
          destination: p.destination,
          initials_firstname: p.firstname.trim().slice(0, 1).toUpperCase(),
          initials_surname: p.surname.trim().slice(0, 1).toUpperCase(),
          pii: pii ?? undefined,
        });
      }
      await this.queue.enqueue(event, persons, d.gps_accuracy);
      this.view.set('list');
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : String(err));
    } finally {
      this.saving.set(false);
    }
  }
}
