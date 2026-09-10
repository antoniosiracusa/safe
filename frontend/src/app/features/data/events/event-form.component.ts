import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DatePickerModule } from 'primeng/datepicker';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TextareaModule } from 'primeng/textarea';

import { EventDetail, EventWrite } from '../../../core/api/rescue.models';
import { RescueService } from '../../../core/api/rescue.service';
import { FilterOptionsService } from '../../../core/filters/filter-options.service';
import { LookupsService } from '../../../core/lookups/lookups.service';
import { SessionService } from '../../../core/session/session.service';
import { TerritoryService } from '../../../core/territory/territory.service';
import { MapPickerComponent } from '../../../shared/map/map-picker.component';

export const TRISTATE = (t: (k: string) => string) => [
  { value: true, label: t('common.yes') },
  { value: false, label: t('common.no') },
];

/** Form di creazione/modifica evento. Le liste arrivano dai vocabolari e dal territorio della società. */
@Component({
  selector: 'safe-event-form',
  imports: [ReactiveFormsModule, TranslocoDirective, ButtonModule, SelectModule, DatePickerModule, InputNumberModule, InputTextModule, TextareaModule, CheckboxModule, MapPickerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './event-form.component.html',
  styleUrl: './form.scss',
})
export class EventFormComponent {
  readonly event = input<EventDetail | null>(null);
  readonly saved = output<EventDetail>();
  readonly cancelled = output<void>();

  readonly lookups = inject(LookupsService);
  readonly territory = inject(TerritoryService);
  readonly session = inject(SessionService);
  private readonly filterOptions = inject(FilterOptionsService);
  private readonly rescue = inject(RescueService);
  private readonly fb = inject(FormBuilder);

  readonly saving = signal(false);
  readonly serverErrors = signal<Record<string, string[]>>({});
  readonly generalError = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    dateandtime: this.fb.control<Date | null>(null, Validators.required),
    team: this.fb.control<string | null>(null, Validators.required),
    ski_area: this.fb.control<string | null>(null),
    zone: this.fb.control<string | null>(null),
    slope: this.fb.control<string | null>(null),
    difficulty: this.fb.control<string | null>(null),
    location_type: this.fb.control<string | null>(null),
    location_description: this.fb.control(''),
    lat: this.fb.control<number | null>(null, [Validators.min(-90), Validators.max(90)]),
    lon: this.fb.control<number | null>(null, [Validators.min(-180), Validators.max(180)]),
    altitude_m: this.fb.control<number | null>(null),
    cause: this.fb.control<string | null>(null),
    cause_note: this.fb.control(''),
    weather: this.fb.control<string | null>(null),
    snow_condition: this.fb.control<string | null>(null),
    wind: this.fb.control<string | null>(null),
    visibility: this.fb.control<string | null>(null),
    service_report: this.fb.control(false),
    witnesses: this.fb.control<boolean | null>(null),
    note: this.fb.control(''),
    event_type: this.fb.control<string | null>(null),
    caller: this.fb.control(''),
    call_received_at: this.fb.control<Date | null>(null),
    location_feature: this.fb.control<string | null>(null),
    traffic: this.fb.control<string | null>(null),
    snow_making: this.fb.control<string | null>(null),
  });

  /** Squadre selezionabili: tutte se l'utente può modificare qualsiasi squadra, altrimenti le proprie. */
  readonly teamOptions = computed(() => {
    if (this.session.can('events.edit_any_team')) return this.filterOptions.options().teams;
    return this.session.teams().map((t) => ({ value: t.id, label: t.name }));
  });
  readonly skiAreaValue = signal<string | null>(null);
  readonly zoneValue = signal<string | null>(null);
  readonly zoneOptions = computed(() => this.territory.zoneOptions(this.skiAreaValue()));
  readonly slopeOptions = computed(() => this.territory.slopeOptions(this.zoneValue(), this.skiAreaValue()));

  constructor() {
    void this.lookups.load();
    void this.territory.load();
    void this.filterOptions.load().catch(() => undefined);
    this.form.controls.ski_area.valueChanges.subscribe((v) => {
      this.skiAreaValue.set(v);
      const zone = this.form.controls.zone.value;
      if (zone && !this.territory.zoneOptions(v).some((z) => z.value === zone)) this.form.controls.zone.setValue(null);
    });
    this.form.controls.zone.valueChanges.subscribe((v) => {
      this.zoneValue.set(v);
      const slope = this.form.controls.slope.value;
      if (slope && !this.territory.slopeOptions(v).some((s) => s.value === slope)) this.form.controls.slope.setValue(null);
    });
    this.form.controls.slope.valueChanges.subscribe((slopeId) => {
      if (!slopeId) return;
      const zone = this.territory.zoneOf(slopeId);
      if (zone && this.form.controls.zone.value !== zone.id) this.form.controls.zone.setValue(zone.id);
      if (zone && this.form.controls.ski_area.value !== zone.ski_area.id) this.form.controls.ski_area.setValue(zone.ski_area.id);
      const slope = this.territory.slopes().find((s) => s.id === slopeId);
      if (slope?.difficulty && !this.form.controls.difficulty.value) this.form.controls.difficulty.setValue(slope.difficulty);
    });
  }

  ngOnInit(): void {
    const ev = this.event();
    if (ev) {
      this.form.patchValue({
        dateandtime: new Date(ev.dateandtime),
        team: ev.team?.id ?? null,
        ski_area: ev.ski_area?.id ?? null,
        zone: ev.zone?.id ?? null,
        slope: ev.slope?.id ?? null,
        difficulty: ev.difficulty,
        location_type: ev.location_type,
        location_description: ev.location_description ?? '',
        lat: ev.geometry?.coordinates[1] ?? null,
        lon: ev.geometry?.coordinates[0] ?? null,
        altitude_m: ev.altitude_m,
        cause: ev.cause,
        cause_note: ev.cause_note ?? '',
        weather: ev.weather,
        snow_condition: ev.snow_condition,
        wind: ev.wind,
        visibility: ev.visibility,
        service_report: ev.service_report,
        witnesses: ev.witnesses,
        note: ev.note ?? '',
        event_type: ev.extended.event_type,
        caller: ev.extended.caller ?? '',
        call_received_at: ev.extended.call_received_at ? new Date(`1970-01-01T${ev.extended.call_received_at}`) : null,
        location_feature: ev.extended.location_feature,
        traffic: ev.extended.traffic,
        snow_making: ev.extended.snow_making,
      });
    } else {
      const defaultTeam = this.session.teams().find((t) => t.is_default) ?? this.session.teams()[0];
      this.form.patchValue({ dateandtime: new Date(), team: defaultTeam?.id ?? null });
    }
  }

  private payload(): EventWrite {
    const v = this.form.getRawValue();
    const time = (d: Date | null) => (d ? d.toTimeString().slice(0, 8) : null);
    return {
      dateandtime: (v.dateandtime as Date).toISOString(),
      team: v.team as string,
      ski_area: v.ski_area,
      zone: v.zone,
      slope: v.slope,
      difficulty: v.difficulty,
      location_type: v.location_type,
      location_description: v.location_description ?? '',
      geometry: v.lat !== null && v.lon !== null ? { type: 'Point', coordinates: [v.lon, v.lat] } : null,
      altitude_m: v.altitude_m,
      cause: v.cause,
      cause_note: v.cause_note ?? '',
      weather: v.weather,
      snow_condition: v.snow_condition,
      wind: v.wind,
      visibility: v.visibility,
      service_report: v.service_report ?? false,
      witnesses: v.witnesses,
      note: v.note ?? '',
      extended: {
        event_type: v.event_type,
        caller: v.caller || null,
        call_received_at: time(v.call_received_at),
        location_feature: v.location_feature,
        traffic: v.traffic,
        snow_making: v.snow_making,
      },
    };
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.serverErrors.set({});
    this.generalError.set(null);
    const ev = this.event();
    const req = ev ? this.rescue.updateEvent(ev.id, this.payload()) : this.rescue.createEvent(this.payload());
    req.subscribe({
      next: (res) => {
        this.saving.set(false);
        this.saved.emit(res);
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        const body = err.error as { code?: string; fields?: Record<string, string[]>; detail?: string } | null;
        if (err.status === 400 && body?.fields) this.serverErrors.set(body.fields);
        else this.generalError.set(body?.code ?? 'save_error');
      },
    });
  }

  /** Posizione corrente del form come [lon, lat] per il selettore sulla mappa. */
  position(): [number, number] | null {
    const { lat, lon } = this.form.getRawValue();
    return lat !== null && lon !== null ? [lon, lat] : null;
  }

  setPosition(p: [number, number] | null): void {
    this.form.patchValue({ lon: p ? p[0] : null, lat: p ? p[1] : null });
    this.form.markAsDirty();
  }

  errorOf(field: string): string | null {
    const ctrl = this.form.get(field);
    if (ctrl?.touched && ctrl.invalid) return 'required';
    const s = this.serverErrors()[field];
    return s?.length ? s[0] : null;
  }
}
