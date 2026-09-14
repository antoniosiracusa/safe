import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslocoDirective } from '@jsverse/transloco';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { MessageModule } from 'primeng/message';
import { MultiSelectModule } from 'primeng/multiselect';
import { SelectModule } from 'primeng/select';
import { TextareaModule } from 'primeng/textarea';

import { Person, PersonWrite } from '../../../core/api/rescue.models';
import { RescueService } from '../../../core/api/rescue.service';
import { KeyStoreService } from '../../../core/crypto/key-store.service';
import { LookupsService } from '../../../core/lookups/lookups.service';

/** Dialogo di creazione/modifica persona: solo dati pseudonimizzati. I dati identificativi
 *  (nome, cognome, contatti) vengono cifrati nel browser in M7. */
@Component({
  selector: 'safe-person-form',
  imports: [FormsModule, ReactiveFormsModule, TranslocoDirective, DialogModule, ButtonModule, SelectModule, MultiSelectModule, InputNumberModule, InputTextModule, TextareaModule, MessageModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './person-form.component.html',
  styleUrl: '../events/form.scss',
})
export class PersonFormComponent implements OnInit {
  readonly eventId = input.required<string>();
  readonly person = input<Person | null>(null);
  readonly saved = output<Person>();
  readonly cancelled = output<void>();

  readonly lookups = inject(LookupsService);
  readonly keyStore = inject(KeyStoreService);
  private readonly rescue = inject(RescueService);
  private readonly fb = inject(FormBuilder);

  readonly visible = signal(true);
  readonly saving = signal(false);
  readonly serverErrors = signal<Record<string, string[]>>({});
  readonly generalError = signal<string | null>(null);
  readonly means = signal<(string | null)[]>([null]);
  readonly identityLoaded = signal(false);
  readonly identityLoading = signal(false);
  readonly identityError = signal(false);

  /** Dati identificativi: cifrati nel browser prima dell'invio, mai in chiaro verso il server. */
  readonly identity = this.fb.nonNullable.group({
    firstname: '', surname: '', birth_date: '', phone: '', email: '', address: '', insurance_code: '', delivered_to: '',
    document_type: '', document_issuer: '', document_number: '',
  });

  /** Tipi di documento di riconoscimento: il codice viene cifrato insieme agli altri dati identificativi. */
  readonly documentTypes = ['id_card', 'passport', 'driving_licence', 'other'];

  readonly form = this.fb.nonNullable.group({
    age: this.fb.control<number | null>(null, [Validators.min(0), Validators.max(120)]),
    gender: this.fb.control<string | null>(null),
    country_code: this.fb.control<string | null>(null),
    initials_firstname: this.fb.control('', [Validators.maxLength(3), Validators.pattern(/^[A-Za-z]{0,3}$/)]),
    initials_surname: this.fb.control('', [Validators.maxLength(3), Validators.pattern(/^[A-Za-z]{0,3}$/)]),
    role: this.fb.control<string | null>(null),
    helmet: this.fb.control<boolean | null>(null),
    equipment: this.fb.control<string | null>(null),
    equipment_owner: this.fb.control<string | null>(null),
    equipment_condition: this.fb.control<string | null>(null),
    equipment_note: this.fb.control(''),
    protections: this.fb.control<string[]>([]),
    conditions: this.fb.control<string[]>([]),
    first_aid: this.fb.control<string[]>([]),
    insurance: this.fb.control<string | null>(null),
    insurance_note: this.fb.control(''),
    accommodation: this.fb.control<string | null>(null),
    accommodation_note: this.fb.control(''),
    destination: this.fb.control<string | null>(null),
    destination_note: this.fb.control(''),
    diagnosis: this.fb.control<string | null>(null),
    secondary_diagnoses: this.fb.control<string[]>([]),
    diagnosis_note: this.fb.control(''),
    gravest_injury: this.fb.control<string | null>(null),
    injury_place: this.fb.control<string | null>(null),
    evacuation_means_note: this.fb.control(''),
    rescue_refusal: this.fb.control<string | null>(null),
    responsibility: this.fb.control<string | null>(null),
    administrative_violations: this.fb.control<boolean | null>(null),
    note: this.fb.control(''),
  });

  readonly bodyPartOptions = computed(() => this.lookups.options('body_part'));

  constructor() {
    void this.lookups.load();
    void this.keyStore.ensureLoaded();
    this.form.controls.gravest_injury.valueChanges.subscribe((code) => {
      const part = this.lookups.items('body_part').find((b) => b.code === code);
      if (part?.parent) this.form.controls.injury_place.setValue(part.parent);
    });
  }

  ngOnInit(): void {
    const p = this.person();
    if (!p) return;
    this.form.patchValue({
      age: p.age,
      gender: p.gender,
      country_code: p.country_code,
      initials_firstname: p.initials_firstname,
      initials_surname: p.initials_surname,
      role: p.extended.role,
      helmet: p.helmet,
      equipment: p.equipment,
      equipment_owner: p.equipment_owner,
      equipment_condition: p.extended.equipment_condition,
      equipment_note: p.equipment_note,
      protections: p.extended.protections,
      conditions: p.extended.conditions ?? [],
      first_aid: p.extended.first_aid ?? [],
      insurance: p.insurance,
      insurance_note: p.insurance_note,
      accommodation: p.accommodation,
      accommodation_note: p.accommodation_note,
      destination: p.destination,
      destination_note: p.destination_note,
      diagnosis: p.diagnosis,
      secondary_diagnoses: p.secondary_diagnoses,
      diagnosis_note: p.diagnosis_note,
      gravest_injury: p.gravest_injury,
      injury_place: p.injury_place,
      evacuation_means_note: p.evacuation_means_note,
      rescue_refusal: p.extended.rescue_refusal,
      responsibility: p.responsibility,
      administrative_violations: p.administrative_violations,
      note: p.note,
    });
    const sorted = [...p.evacuation_means].sort((a, b) => a.order - b.order).map((m) => m.mean);
    this.means.set(sorted.length ? sorted : [null]);
  }

  async loadIdentity(): Promise<void> {
    const p = this.person();
    if (!p) return;
    this.identityLoading.set(true);
    this.identityError.set(false);
    try {
      const data = await this.keyStore.readIdentity(p.id);
      this.identity.patchValue(data);
      this.identity.markAsPristine();
      this.identityLoaded.set(true);
    } catch {
      this.identityError.set(true);
    } finally {
      this.identityLoading.set(false);
    }
  }

  /** null = nessuna modifica ai dati cifrati; {pii: null} = cancellati; {pii: blob} = nuovi/aggiornati. */
  private async identityPayload(): Promise<{ pii: PersonWrite['pii'] } | null> {
    const p = this.person();
    const values = this.identity.getRawValue();
    const hasValues = Object.values(values).some((v) => v && v.trim());
    if (p?.has_identity && !this.identityLoaded()) return null; // cifrati e non toccati
    if (!hasValues) return p?.has_identity ? { pii: null } : null;
    if (!this.identity.dirty && this.identityLoaded()) return null;
    const pii = await this.keyStore.encryptIdentity(values);
    return pii ? { pii } : null;
  }

  setMean(i: number, value: string | null): void {
    this.means.update((arr) => arr.map((m, k) => (k === i ? value : m)));
  }

  addMean(): void {
    this.means.update((arr) => [...arr, null]);
  }

  removeMean(i: number): void {
    this.means.update((arr) => (arr.length > 1 ? arr.filter((_, k) => k !== i) : [null]));
  }

  meanOptions(i: number) {
    const chosen = new Set(this.means().filter((m, k) => m && k !== i));
    return this.lookups.options('evacuation_mean').filter((o) => !chosen.has(o.value));
  }

  private payload(): PersonWrite {
    const v = this.form.getRawValue();
    const means = this.means().filter((m): m is string => !!m).map((mean, i) => ({ mean, order: i + 1 }));
    return {
      age: v.age,
      gender: v.gender,
      country_code: v.country_code,
      initials_firstname: (v.initials_firstname ?? '').toUpperCase(),
      initials_surname: (v.initials_surname ?? '').toUpperCase(),
      role: v.role,
      helmet: v.helmet,
      equipment: v.equipment,
      equipment_owner: v.equipment_owner,
      equipment_condition: v.equipment_condition,
      equipment_note: v.equipment_note ?? '',
      protections: v.protections ?? [],
      conditions: v.conditions ?? [],
      first_aid: v.first_aid ?? [],
      insurance: v.insurance,
      insurance_note: v.insurance_note ?? '',
      accommodation: v.accommodation,
      accommodation_note: v.accommodation_note ?? '',
      destination: v.destination,
      destination_note: v.destination_note ?? '',
      diagnosis: v.diagnosis,
      secondary_diagnoses: v.secondary_diagnoses ?? [],
      diagnosis_note: v.diagnosis_note ?? '',
      gravest_injury: v.gravest_injury,
      injury_place: v.injury_place,
      evacuation_means: means,
      evacuation_means_note: v.evacuation_means_note ?? '',
      rescue_refusal: v.rescue_refusal,
      responsibility: v.responsibility,
      administrative_violations: v.administrative_violations,
      note: v.note ?? '',
    };
  }

  async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.serverErrors.set({});
    this.generalError.set(null);
    const p = this.person();
    let body: PersonWrite = this.payload();
    try {
      const extra = await this.identityPayload();
      if (extra) body = { ...body, ...extra };
    } catch {
      this.saving.set(false);
      this.generalError.set('encrypt_error');
      return;
    }
    const req = p ? this.rescue.updatePerson(p.id, body) : this.rescue.addPerson(this.eventId(), body);
    req.subscribe({
      next: (res) => {
        this.saving.set(false);
        this.visible.set(false);
        this.saved.emit(res);
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        const body = err.error as { code?: string; fields?: Record<string, string[]> } | null;
        if (err.status === 400 && body?.fields) this.serverErrors.set(body.fields);
        else this.generalError.set(body?.code ?? 'save_error');
      },
    });
  }

  errorOf(field: string): string | null {
    const ctrl = this.form.get(field);
    if (ctrl?.touched && ctrl.invalid) return 'invalid';
    const s = this.serverErrors()[field];
    return s?.length ? s[0] : null;
  }

  onHide(): void {
    if (this.visible()) return;
    this.cancelled.emit();
  }
}
