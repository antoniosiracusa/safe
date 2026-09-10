/** Modelli dell'API eventi/persone (docs/03-openapi.yaml). I codici lookup sono stringhe; null = non classificato. */

export interface Ref {
  id: string;
  name: string;
}

export interface SlopeRef extends Ref {
  regional_code: string | null;
}

export interface ValidationError {
  field: string;
  code: string;
}

export interface EventRow {
  id: string;
  season: string;
  dateandtime: string;
  team: Ref | null;
  ski_area: Ref | null;
  zone: Ref | null;
  slope: SlopeRef | null;
  difficulty: string | null;
  location_type: string | null;
  location_description: string | null;
  cause: string | null;
  cause_note: string | null;
  weather: string | null;
  snow_condition: string | null;
  wind: string | null;
  visibility: string | null;
  service_report: boolean;
  witnesses: boolean | null;
  persons_count: number;
  valid: boolean;
  fully_valid: boolean;
  locked_at: string | null;
  has_geometry: boolean;
  created_at: string;
  updated_at: string;
}

export interface EventExtended {
  caller: string | null;
  call_received_at: string | null;
  time_since_incident: number | null;
  external_rescue_call_at: string | null;
  location_feature: string | null;
  traffic: string | null;
  snow_making: string | null;
  event_type: string | null;
  operators: { user_id: string | null; name: string }[];
}

export interface EventDetail extends EventRow {
  geometry: { type: 'Point'; coordinates: [number, number] } | null;
  altitude_m: number | null;
  extended: EventExtended;
  note: string | null;
  validation_errors: ValidationError[];
  unlock_count: number;
  last_unlocked_at: string | null;
  persons: Person[];
  created_by: Ref | null;
}

export interface EventWrite {
  client_uuid?: string;
  dateandtime: string;
  team: string;
  ski_area?: string | null;
  zone?: string | null;
  slope?: string | null;
  difficulty?: string | null;
  location_type?: string | null;
  location_description?: string;
  geometry?: { type: 'Point'; coordinates: [number, number] } | null;
  altitude_m?: number | null;
  cause?: string | null;
  cause_note?: string;
  weather?: string | null;
  snow_condition?: string | null;
  wind?: string | null;
  visibility?: string | null;
  service_report?: boolean;
  witnesses?: boolean | null;
  note?: string;
  extended?: Partial<Omit<EventExtended, 'operators'>> & { operators?: { name: string }[] };
}

export interface EvacuationMean {
  mean: string;
  order: number;
}

export interface Person {
  id: string;
  event_id: string;
  sequence: number;
  age: number | null;
  age_class: string;
  gender: string | null;
  country_code: string | null;
  initials_firstname: string;
  initials_surname: string;
  has_identity: boolean;
  pii_fields: string[];
  helmet: boolean | null;
  equipment: string | null;
  equipment_note: string;
  equipment_owner: string | null;
  insurance: string | null;
  insurance_note: string;
  accommodation: string | null;
  accommodation_note: string;
  destination: string | null;
  destination_note: string;
  diagnosis: string | null;
  diagnosis_note: string;
  secondary_diagnoses: string[];
  gravest_injury: string | null;
  injury_place: string | null;
  injuries: { body_part: string; rank: 'primary' | 'secondary' }[];
  evacuation_means: EvacuationMean[];
  evacuation_means_note: string;
  responsibility: string | null;
  administrative_violations: boolean | null;
  note: string;
  valid: boolean;
  validation_errors: ValidationError[];
  anonymized_at: string | null;
  extended: {
    role: string | null;
    equipment_condition: string | null;
    rescue_refusal: string | null;
    delivered_at: string | null;
    protections: string[];
  };
  event: {
    id: string;
    dateandtime: string;
    season: string;
    team_name: string;
    zone_name: string | null;
    slope_name: string | null;
    locked: boolean;
  };
  created_at: string;
  updated_at: string;
}

export type PersonWrite = Partial<
  Pick<
    Person,
    | 'sequence'
    | 'age'
    | 'gender'
    | 'country_code'
    | 'initials_firstname'
    | 'initials_surname'
    | 'helmet'
    | 'equipment'
    | 'equipment_note'
    | 'equipment_owner'
    | 'insurance'
    | 'insurance_note'
    | 'accommodation'
    | 'accommodation_note'
    | 'destination'
    | 'destination_note'
    | 'diagnosis'
    | 'diagnosis_note'
    | 'secondary_diagnoses'
    | 'gravest_injury'
    | 'injury_place'
    | 'injuries'
    | 'evacuation_means'
    | 'evacuation_means_note'
    | 'responsibility'
    | 'administrative_violations'
    | 'note'
  >
> & {
  client_uuid?: string;
  role?: string | null;
  equipment_condition?: string | null;
  rescue_refusal?: string | null;
  delivered_at?: string | null;
  protections?: string[];
  pii?: { ciphertext: string; key_wrapped: string; key_version: number; fields: string[] } | null;
};

export interface SkiArea {
  id: string;
  name: string;
  regional_code: string;
  has_boundary: boolean;
}
export interface Zone {
  id: string;
  name: string;
  ski_area: Ref;
}
export interface Slope {
  id: string;
  name: string;
  regional_code: string;
  difficulty: string | null;
  zone: { id: string; name: string; ski_area: string };
}
