export type UserStatus = 'invited' | 'active' | 'disabled';

export interface AdminUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  locale: string;
  status: UserStatus;
  mfa_required: boolean;
  is_platform_admin: boolean;
  teams: { id: string; name: string; is_default: boolean }[];
  roles: string[];
  grants: string[];
  denies: string[];
  invited_at: string | null;
  activated_at: string | null;
  disabled_at: string | null;
  last_login_at: string | null;
  devices_count: number;
  created_at: string;
}

export interface InviteRequest {
  email: string;
  first_name: string;
  last_name: string;
  locale: string;
  teams: string[];
  default_team: string | null;
  roles: string[];
  mfa_required: boolean;
}

export interface UserPatch {
  first_name?: string;
  last_name?: string;
  locale?: string;
  mfa_required?: boolean;
  teams?: string[];
  default_team?: string | null;
}

export interface PermissionsPut {
  roles: string[];
  grants: string[];
  denies: string[];
}

export interface Role {
  id: string;
  code: string;
  name_it: string;
  name_en: string;
  name_de: string;
  is_system: boolean;
  is_custom: boolean;
  permissions: string[];
}

export interface TeamAdmin {
  id: string;
  name: string;
  body: string | null;
  is_active: boolean;
  users_count: number;
  events_count: number;
  created_at: string;
}

export type DeviceStatus = 'pending' | 'authorized' | 'revoked';

export interface Device {
  id: string;
  name: string;
  user: { id: string; email: string; name: string };
  platform: 'ios' | 'android';
  os_version: string;
  app_version: string;
  status: DeviceStatus;
  enrolled_at: string;
  authorized_at: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
}

export interface EnrollmentCode {
  code: string;
  expires_at: string;
  qr_payload: string;
  qr_svg: string;
}

export interface AdminSkiArea {
  id: string;
  name: string;
  regional_code: string;
  has_boundary: boolean;
  zones_count: number;
  is_active: boolean;
}
export interface AdminZone {
  id: string;
  name: string;
  ski_area: { id: string; name: string };
  slopes_count: number;
  is_active: boolean;
}
export interface AdminSlope {
  id: string;
  name: string;
  regional_code: string;
  difficulty: string | null;
  zone: { id: string; name: string; ski_area: string };
  has_geometry: boolean;
  events_count: number;
  is_active: boolean;
}
export interface AdminLift {
  id: string;
  name: string;
  lift_type: string;
  ski_area: { id: string; name: string };
  has_geometry: boolean;
  is_active: boolean;
}

export interface LookupAdminItem {
  id: string;
  dimension: string;
  code: string;
  labels: Record<string, string>;
  sort_order: number;
  is_custom: boolean;
  is_active: boolean;
  disabled_for_company: boolean;
  parent: string | null;
  color: string | null;
  mapping: Record<string, unknown>;
}

export interface CompanyInfo {
  id: string;
  name: string;
  slug: string;
  tenant_type: string;
  timezone: string;
  default_locale: string;
  retention_identity_years: number;
  retention_audit_years: number;
  settings: {
    auto_lock_hours: number;
    first_season: string | null;
    devices_need_authorization: boolean;
    validity_rules: { event_required: string[]; person_required: string[] };
    duplicate_rule: { minutes: number; fields: string[] };
    export_templates: Record<string, unknown>;
  };
  created_at: string;
}

export const EVENT_RULE_FIELDS = ['dateandtime', 'team', 'ski_area', 'zone', 'slope', 'location', 'location_type', 'cause', 'geometry', 'weather', 'snow_condition', 'difficulty'];
export const PERSON_RULE_FIELDS = ['age', 'gender', 'country_code', 'diagnosis', 'injury_place', 'equipment', 'helmet', 'evacuation_means', 'destination'];
export const DUP_RULE_FIELDS = ['date', 'slope', 'zone', 'gender', 'age_class_a01', 'equipment'];
export const LOOKUP_DIMENSIONS = [
  'cause', 'location_type', 'slope_difficulty', 'weather', 'snow_condition', 'wind', 'visibility', 'location_feature', 'traffic',
  'snow_making', 'event_type', 'gender', 'equipment', 'equipment_owner', 'equipment_condition', 'protection', 'insurance',
  'accommodation', 'destination', 'diagnosis', 'injury_place', 'body_part', 'evacuation_mean', 'responsibility', 'person_role',
  'rescue_refusal', 'team_body', 'condition', 'first_aid',
];
