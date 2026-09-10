-- ============================================================================
-- SAFE · DDL PostgreSQL 16 + PostGIS 3.4
-- Le migrazioni Django genereranno lo schema equivalente; questo file è il
-- riferimento di progetto (tabelle, vincoli, indici, trigger, RLS).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Ruoli database ------------------------------------------------------------
-- safe_owner : proprietario dello schema, usato solo dalle migrazioni
-- safe_app   : ruolo runtime (API, worker); soggetto a RLS, non owner
-- safe_admin : amministrazione piattaforma (creazione società), BYPASSRLS
-- CREATE ROLE safe_owner LOGIN; CREATE ROLE safe_app LOGIN; CREATE ROLE safe_admin LOGIN BYPASSRLS;

-- ============================================================================
-- 0. Funzioni di utilità
-- ============================================================================

CREATE OR REPLACE FUNCTION current_company_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.company_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION trg_set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- Classi di età parametriche (usate dagli aggregatori)
CREATE OR REPLACE FUNCTION age_class(p_age smallint, p_cluster text DEFAULT 'standard') RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN p_age IS NULL THEN 'unclassified'
    WHEN p_cluster = 'veneto_a01' THEN CASE
      WHEN p_age <= 10 THEN '0-10' WHEN p_age <= 20 THEN '11-20' WHEN p_age <= 30 THEN '21-30'
      WHEN p_age <= 40 THEN '31-40' WHEN p_age <= 50 THEN '41-50' WHEN p_age <= 60 THEN '51-60'
      WHEN p_age <= 70 THEN '61-70' WHEN p_age <= 80 THEN '71-80' ELSE '80+' END
    ELSE CASE
      WHEN p_age <= 17 THEN '0-17' WHEN p_age <= 24 THEN '18-24' WHEN p_age <= 34 THEN '25-34'
      WHEN p_age <= 44 THEN '35-44' WHEN p_age <= 54 THEN '45-54' WHEN p_age <= 64 THEN '55-64'
      ELSE '65+' END
  END
$$;

-- ============================================================================
-- 1. Tabelle globali (nessun tenant)
-- ============================================================================

CREATE TABLE season (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,                 -- '2025/2026'
  start_date  date NOT NULL,                        -- 2025-06-01
  end_date    date NOT NULL,                        -- 2026-05-31
  CONSTRAINT chk_season_range CHECK (end_date > start_date),
  CONSTRAINT excl_season_overlap EXCLUDE USING gist (daterange(start_date, end_date, '[]') WITH &&)
);

CREATE TABLE country (
  code    char(2) PRIMARY KEY,                      -- ISO 3166-1 alpha-2
  name_it text NOT NULL, name_en text NOT NULL, name_de text NOT NULL,
  is_eu   boolean NOT NULL DEFAULT false
);

CREATE TABLE istat_admin_unit (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  level        text NOT NULL CHECK (level IN ('region','province','municipality')),
  code         text NOT NULL,                       -- COD_REG / COD_PROV / PRO_COM_T
  name         text NOT NULL,
  parent_code  text,
  edition_year int  NOT NULL,
  geom         geometry(MultiPolygon, 4326) NOT NULL,
  UNIQUE (level, code, edition_year)
);
CREATE INDEX ix_istat_geom ON istat_admin_unit USING gist (geom);

CREATE TABLE permission (
  code        text PRIMARY KEY,                     -- 'events.view'
  module      text NOT NULL,
  description text NOT NULL,
  is_audited  boolean NOT NULL DEFAULT false
);

CREATE TABLE company (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     text NOT NULL,
  slug                     text NOT NULL UNIQUE,
  tenant_type              text NOT NULL DEFAULT 'company' CHECK (tenant_type IN ('company','authority')),
  timezone                 text NOT NULL DEFAULT 'Europe/Rome',
  default_locale           text NOT NULL DEFAULT 'it',
  settings                 jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- settings: {"validity_rules": {...}, "auto_lock_hours": 48,
  --            "duplicate_rule": {"minutes": 30, "fields": [...]},
  --            "export_templates": {"veneto_a01": {...}}}
  retention_identity_years int NOT NULL DEFAULT 10,
  retention_audit_years    int NOT NULL DEFAULT 10,
  data_version             bigint NOT NULL DEFAULT 0,
  is_active                boolean NOT NULL DEFAULT true,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 2. Vocabolari controllati
-- ============================================================================

CREATE TABLE lookup_value (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid REFERENCES company(id) ON DELETE CASCADE,  -- NULL = globale
  dimension   text NOT NULL,
  code        text NOT NULL,
  label_it    text NOT NULL,
  label_en    text NOT NULL,
  label_de    text NOT NULL,
  sort_order  int  NOT NULL DEFAULT 100,
  is_active   boolean NOT NULL DEFAULT true,
  parent_id   uuid REFERENCES lookup_value(id),               -- body_part -> injury_place
  mapping     jsonb NOT NULL DEFAULT '{}'::jsonb,             -- {"veneto_a01": "Collisione altro sciatore"}
  color       text,                                           -- colore grafico suggerito
  CONSTRAINT chk_lookup_code CHECK (code ~ '^[a-z0-9_]+$')
);
CREATE UNIQUE INDEX ux_lookup_dim_code ON lookup_value (dimension, code, COALESCE(company_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX ix_lookup_dim ON lookup_value (dimension, sort_order);

CREATE TABLE company_lookup_disabled (          -- disattiva un valore globale per una società
  company_id      uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  lookup_value_id uuid NOT NULL REFERENCES lookup_value(id) ON DELETE CASCADE,
  PRIMARY KEY (company_id, lookup_value_id)
);

-- Verifica che una FK verso lookup_value punti alla dimensione attesa
CREATE OR REPLACE FUNCTION assert_lookup_dimension(p_id uuid, p_dimension text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT p_id IS NULL OR EXISTS (SELECT 1 FROM lookup_value WHERE id = p_id AND dimension = p_dimension)
$$;

-- ============================================================================
-- 3. Organizzazione
-- ============================================================================

CREATE TABLE team (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  name        text NOT NULL,
  body_id     uuid REFERENCES lookup_value(id),               -- dimension team_body
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, name),
  CONSTRAINT chk_team_body CHECK (assert_lookup_dimension(body_id, 'team_body'))
);

CREATE TABLE app_user (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     uuid NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
  oidc_subject   text UNIQUE,                                 -- sub Keycloak; NULL finché invitato
  keycloak_id    text UNIQUE,
  email          citext NOT NULL,
  first_name     text NOT NULL DEFAULT '',
  last_name      text NOT NULL DEFAULT '',
  locale         text NOT NULL DEFAULT 'it',
  status         text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active','disabled')),
  is_platform_admin boolean NOT NULL DEFAULT false,
  mfa_required   boolean NOT NULL DEFAULT false,
  invited_at     timestamptz,
  invited_by     uuid REFERENCES app_user(id),
  activated_at   timestamptz,
  disabled_at    timestamptz,
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, email)
);
CREATE INDEX ix_user_company_status ON app_user (company_id, status);

CREATE TABLE user_team (
  user_id    uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  team_id    uuid NOT NULL REFERENCES team(id) ON DELETE CASCADE,
  is_default boolean NOT NULL DEFAULT false,
  PRIMARY KEY (user_id, team_id)
);

CREATE TABLE role (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid REFERENCES company(id) ON DELETE CASCADE,  -- NULL = template globale
  code        text NOT NULL,
  name_it     text NOT NULL, name_en text NOT NULL, name_de text NOT NULL,
  is_system   boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX ux_role_code ON role (code, COALESCE(company_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE TABLE role_permission (
  role_id         uuid NOT NULL REFERENCES role(id) ON DELETE CASCADE,
  permission_code text NOT NULL REFERENCES permission(code) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_code)
);

CREATE TABLE user_role (
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES role(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE user_permission (
  user_id         uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  permission_code text NOT NULL REFERENCES permission(code) ON DELETE CASCADE,
  effect          text NOT NULL CHECK (effect IN ('grant','deny')),
  granted_by      uuid REFERENCES app_user(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, permission_code)
);

-- ============================================================================
-- 4. Territorio
-- ============================================================================

CREATE TABLE ski_area (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  name          text NOT NULL,
  regional_code text,
  boundary      geometry(MultiPolygon, 4326),
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, name)
);
CREATE INDEX ix_ski_area_boundary ON ski_area USING gist (boundary);

CREATE TABLE zone (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  ski_area_id uuid NOT NULL REFERENCES ski_area(id) ON DELETE CASCADE,
  name        text NOT NULL,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ski_area_id, name)
);
CREATE INDEX ix_zone_company ON zone (company_id, ski_area_id);

CREATE TABLE slope (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  zone_id       uuid NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  name          text NOT NULL,
  regional_code text,                                          -- es. 'C.1.24' (tracciato A01)
  difficulty_id uuid REFERENCES lookup_value(id),
  geom          geometry(MultiLineString, 4326),
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (zone_id, name),
  CONSTRAINT chk_slope_difficulty CHECK (assert_lookup_dimension(difficulty_id, 'slope_difficulty'))
);
CREATE INDEX ix_slope_company_zone ON slope (company_id, zone_id);
CREATE INDEX ix_slope_geom ON slope USING gist (geom);

CREATE TABLE lift (                                            -- layer cartografico impianti
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  ski_area_id uuid NOT NULL REFERENCES ski_area(id) ON DELETE CASCADE,
  name        text NOT NULL,
  lift_type   text,
  geom        geometry(LineString, 4326),
  is_active   boolean NOT NULL DEFAULT true
);
CREATE INDEX ix_lift_geom ON lift USING gist (geom);

-- ============================================================================
-- 5. Eventi e persone
-- ============================================================================

CREATE TABLE import_batch (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  job_id        uuid,                                          -- FK aggiunta dopo async_job
  source_format text NOT NULL,
  mapping       jsonb NOT NULL,
  rows_total    int NOT NULL DEFAULT 0,
  rows_ok       int NOT NULL DEFAULT 0,
  rows_error    int NOT NULL DEFAULT 0,
  report        jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by    uuid REFERENCES app_user(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE event (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id            uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  client_uuid           uuid,                                  -- idempotenza mobile
  legacy_id             text,                                  -- id nel sistema precedente
  import_batch_id       uuid REFERENCES import_batch(id),
  season_id             uuid NOT NULL REFERENCES season(id),   -- impostato da trigger
  dateandtime           timestamptz NOT NULL,
  team_id               uuid NOT NULL REFERENCES team(id),
  ski_area_id           uuid REFERENCES ski_area(id),
  zone_id               uuid REFERENCES zone(id),
  slope_id              uuid REFERENCES slope(id),
  difficulty_id         uuid REFERENCES lookup_value(id),
  location_type_id      uuid REFERENCES lookup_value(id),
  location_description  text,
  geom                  geometry(Point, 4326),
  altitude_m            numeric(6,1),
  cause_id              uuid REFERENCES lookup_value(id),
  cause_note            text,
  weather_id            uuid REFERENCES lookup_value(id),
  snow_condition_id     uuid REFERENCES lookup_value(id),
  wind_id               uuid REFERENCES lookup_value(id),
  visibility_id         uuid REFERENCES lookup_value(id),
  service_report        boolean NOT NULL DEFAULT false,
  witnesses             boolean,                               -- NULL = non classificato
  -- campi estesi (opzionali, dal rapporto di riferimento)
  caller                text,
  call_received_at      time,
  time_since_incident   interval,
  external_rescue_call_at time,
  location_feature_id   uuid REFERENCES lookup_value(id),
  traffic_id            uuid REFERENCES lookup_value(id),
  snow_making_id        uuid REFERENCES lookup_value(id),
  event_type_id         uuid REFERENCES lookup_value(id),
  note                  text,
  -- stato
  valid                 boolean NOT NULL DEFAULT false,
  fully_valid           boolean NOT NULL DEFAULT false,
  validation_errors     jsonb NOT NULL DEFAULT '[]'::jsonb,
  locked_at             timestamptz,
  locked_by             uuid REFERENCES app_user(id),
  unlock_count          int NOT NULL DEFAULT 0,
  last_unlocked_at      timestamptz,
  istat_comune_code     text,                                  -- calcolato da trigger spaziale
  created_by            uuid REFERENCES app_user(id),
  created_by_device_id  uuid,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  deleted_at            timestamptz,
  CONSTRAINT chk_event_difficulty   CHECK (assert_lookup_dimension(difficulty_id, 'slope_difficulty')),
  CONSTRAINT chk_event_location     CHECK (assert_lookup_dimension(location_type_id, 'location_type')),
  CONSTRAINT chk_event_cause        CHECK (assert_lookup_dimension(cause_id, 'cause')),
  CONSTRAINT chk_event_weather      CHECK (assert_lookup_dimension(weather_id, 'weather')),
  CONSTRAINT chk_event_snow         CHECK (assert_lookup_dimension(snow_condition_id, 'snow_condition')),
  CONSTRAINT chk_event_wind         CHECK (assert_lookup_dimension(wind_id, 'wind')),
  CONSTRAINT chk_event_visibility   CHECK (assert_lookup_dimension(visibility_id, 'visibility')),
  CONSTRAINT chk_event_feature      CHECK (assert_lookup_dimension(location_feature_id, 'location_feature')),
  CONSTRAINT chk_event_traffic      CHECK (assert_lookup_dimension(traffic_id, 'traffic')),
  CONSTRAINT chk_event_snowmaking   CHECK (assert_lookup_dimension(snow_making_id, 'snow_making')),
  CONSTRAINT chk_event_type         CHECK (assert_lookup_dimension(event_type_id, 'event_type'))
);
CREATE UNIQUE INDEX ux_event_client_uuid ON event (company_id, client_uuid) WHERE client_uuid IS NOT NULL;
CREATE UNIQUE INDEX ux_event_legacy      ON event (company_id, legacy_id) WHERE legacy_id IS NOT NULL;
CREATE INDEX ix_event_company_date   ON event (company_id, dateandtime DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_season_zone    ON event (company_id, season_id, zone_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_team_date      ON event (company_id, team_id, dateandtime) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_slope          ON event (company_id, slope_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_ski_area       ON event (company_id, ski_area_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_geom           ON event USING gist (geom) WHERE deleted_at IS NULL;
CREATE INDEX ix_event_locked         ON event (company_id, locked_at) WHERE deleted_at IS NULL;

CREATE TABLE event_operator (                                  -- operatori intervenuti (personale)
  event_id  uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
  user_id   uuid REFERENCES app_user(id),
  name      text,                                              -- se non utente del sistema
  position  smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (event_id, position)
);

CREATE TABLE person (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id               uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  event_id                 uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
  client_uuid              uuid,
  sequence                 smallint NOT NULL DEFAULT 1,        -- "Persona 1", "Persona 2"
  role_id                  uuid REFERENCES lookup_value(id),   -- esteso: coinvolto, testimone, ...
  -- dati pseudonimizzati in chiaro
  age                      smallint CHECK (age BETWEEN 0 AND 120),
  gender_id                uuid REFERENCES lookup_value(id),
  country_code             char(2) REFERENCES country(code),
  initials_firstname       varchar(3) CHECK (initials_firstname ~ '^[A-Z]{0,3}$'),
  initials_surname         varchar(3) CHECK (initials_surname ~ '^[A-Z]{0,3}$'),
  -- dati identificativi cifrati (client-side)
  pii_ciphertext           bytea,   -- XChaCha20-Poly1305(JSON{firstname,surname,birthplace,address,city,phone,email,insurance_code,skipass_code,delivered_to})
  pii_key_wrapped          bytea,   -- sealed box (X25519) della data key verso company_key.public_key
  pii_key_version          int,     -- company_key.version usata
  pii_fields               text[] NOT NULL DEFAULT '{}',       -- nomi dei campi presenti nel blob (mai i valori)
  -- attrezzatura e protezioni
  helmet                   boolean,                            -- NULL = non classificato
  equipment_id             uuid REFERENCES lookup_value(id),
  equipment_note           text,
  equipment_owner_id       uuid REFERENCES lookup_value(id),
  equipment_condition_id   uuid REFERENCES lookup_value(id),   -- esteso
  -- assicurazione, alloggio, destinazione
  insurance_id             uuid REFERENCES lookup_value(id),
  insurance_note           text,
  accommodation_id         uuid REFERENCES lookup_value(id),
  accommodation_note       text,
  destination_id           uuid REFERENCES lookup_value(id),
  destination_note         text,
  -- clinica
  diagnosis_id             uuid REFERENCES lookup_value(id),   -- diagnosi presunta principale
  diagnosis_note           text,
  gravest_injury_id        uuid REFERENCES lookup_value(id),   -- body_part principale
  injury_place_id          uuid REFERENCES lookup_value(id),   -- macro-sede
  evacuation_means_note    text,
  rescue_refusal_id        uuid REFERENCES lookup_value(id),   -- esteso
  delivered_at             time,                               -- esteso
  -- responsabilità
  responsibility_id        uuid REFERENCES lookup_value(id),
  administrative_violations boolean,                           -- NULL = non classificato
  note                     text,
  -- stato
  valid                    boolean NOT NULL DEFAULT false,
  validation_errors        jsonb NOT NULL DEFAULT '[]'::jsonb,
  anonymized_at            timestamptz,
  age_class_snapshot       text,                               -- valorizzato all'anonimizzazione
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  deleted_at               timestamptz,
  CONSTRAINT chk_person_role          CHECK (assert_lookup_dimension(role_id, 'person_role')),
  CONSTRAINT chk_person_gender        CHECK (assert_lookup_dimension(gender_id, 'gender')),
  CONSTRAINT chk_person_equipment     CHECK (assert_lookup_dimension(equipment_id, 'equipment')),
  CONSTRAINT chk_person_eq_owner      CHECK (assert_lookup_dimension(equipment_owner_id, 'equipment_owner')),
  CONSTRAINT chk_person_eq_condition  CHECK (assert_lookup_dimension(equipment_condition_id, 'equipment_condition')),
  CONSTRAINT chk_person_insurance     CHECK (assert_lookup_dimension(insurance_id, 'insurance')),
  CONSTRAINT chk_person_accommodation CHECK (assert_lookup_dimension(accommodation_id, 'accommodation')),
  CONSTRAINT chk_person_destination   CHECK (assert_lookup_dimension(destination_id, 'destination')),
  CONSTRAINT chk_person_diagnosis     CHECK (assert_lookup_dimension(diagnosis_id, 'diagnosis')),
  CONSTRAINT chk_person_gravest       CHECK (assert_lookup_dimension(gravest_injury_id, 'body_part')),
  CONSTRAINT chk_person_injury_place  CHECK (assert_lookup_dimension(injury_place_id, 'injury_place')),
  CONSTRAINT chk_person_refusal       CHECK (assert_lookup_dimension(rescue_refusal_id, 'rescue_refusal')),
  CONSTRAINT chk_person_responsib     CHECK (assert_lookup_dimension(responsibility_id, 'responsibility')),
  CONSTRAINT chk_person_pii_pair      CHECK ((pii_ciphertext IS NULL) = (pii_key_wrapped IS NULL))
);
CREATE UNIQUE INDEX ux_person_client_uuid ON person (company_id, client_uuid) WHERE client_uuid IS NOT NULL;
CREATE UNIQUE INDEX ux_person_event_seq   ON person (event_id, sequence);
CREATE INDEX ix_person_company_event ON person (company_id, event_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_person_country       ON person (company_id, country_code) WHERE deleted_at IS NULL;
CREATE INDEX ix_person_diagnosis     ON person (company_id, diagnosis_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_person_equipment     ON person (company_id, equipment_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_person_retention     ON person (company_id, anonymized_at) WHERE pii_ciphertext IS NOT NULL;

CREATE TABLE person_evacuation_mean (
  person_id uuid NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  mean_id   uuid NOT NULL REFERENCES lookup_value(id),
  "order"   smallint NOT NULL CHECK ("order" >= 1),
  PRIMARY KEY (person_id, "order"),
  UNIQUE (person_id, mean_id),
  CONSTRAINT chk_pem_mean CHECK (assert_lookup_dimension(mean_id, 'evacuation_mean'))
);
CREATE INDEX ix_pem_mean ON person_evacuation_mean (mean_id);

CREATE TABLE person_diagnosis (                                -- diagnosi secondarie
  person_id    uuid NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  diagnosis_id uuid NOT NULL REFERENCES lookup_value(id),
  PRIMARY KEY (person_id, diagnosis_id),
  CONSTRAINT chk_pd_dim CHECK (assert_lookup_dimension(diagnosis_id, 'diagnosis'))
);

CREATE TABLE person_injury (                                   -- mappa corporea
  person_id    uuid NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  body_part_id uuid NOT NULL REFERENCES lookup_value(id),
  rank         text NOT NULL CHECK (rank IN ('primary','secondary')),
  PRIMARY KEY (person_id, body_part_id),
  CONSTRAINT chk_pi_dim CHECK (assert_lookup_dimension(body_part_id, 'body_part'))
);

CREATE TABLE person_protection (                               -- esteso: altre protezioni
  person_id     uuid NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  protection_id uuid NOT NULL REFERENCES lookup_value(id),
  PRIMARY KEY (person_id, protection_id),
  CONSTRAINT chk_pp_dim CHECK (assert_lookup_dimension(protection_id, 'protection'))
);

-- ============================================================================
-- 6. Dispositivi mobili
-- ============================================================================

CREATE TABLE device_enrollment_code (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  code_hash   text NOT NULL UNIQUE,                            -- SHA-256 del codice nel QR
  created_by  uuid REFERENCES app_user(id),
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  used_by_device_id uuid
);

CREATE TABLE mobile_device (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  user_id      uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  install_id   text NOT NULL,                                  -- id installazione app
  name         text NOT NULL,
  platform     text NOT NULL CHECK (platform IN ('ios','android')),
  os_version   text,
  app_version  text,
  status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','authorized','revoked')),
  enrolled_at  timestamptz NOT NULL DEFAULT now(),
  authorized_at timestamptz,
  authorized_by uuid REFERENCES app_user(id),
  last_seen_at timestamptz,
  revoked_at   timestamptz,
  UNIQUE (company_id, install_id)
);
CREATE INDEX ix_device_company_status ON mobile_device (company_id, status);

-- ============================================================================
-- 7. Cifratura
-- ============================================================================

CREATE TABLE user_key (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               uuid NOT NULL UNIQUE REFERENCES app_user(id) ON DELETE CASCADE,
  company_id            uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  algorithm             text NOT NULL DEFAULT 'x25519-v1',
  public_key            bytea NOT NULL,
  private_key_encrypted bytea NOT NULL,                        -- secretbox(privkey, Argon2id(passphrase))
  kdf_params            jsonb NOT NULL,                        -- {"alg":"argon2id","salt":"…","ops":…,"mem":…}
  created_at            timestamptz NOT NULL DEFAULT now(),
  rotated_at            timestamptz
);

CREATE TABLE company_key (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  version     int  NOT NULL,
  algorithm   text NOT NULL DEFAULT 'x25519-sealedbox-v1',
  public_key  bytea NOT NULL,
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  created_by  uuid REFERENCES app_user(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  retired_at  timestamptz,
  UNIQUE (company_id, version)
);
CREATE UNIQUE INDEX ux_company_key_active ON company_key (company_id) WHERE status = 'active';

CREATE TABLE company_key_grant (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id          uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  company_key_id      uuid NOT NULL REFERENCES company_key(id) ON DELETE CASCADE,
  user_id             uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  wrapped_private_key bytea NOT NULL,                          -- sealed box verso user_key.public_key
  granted_by          uuid REFERENCES app_user(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  revoked_at          timestamptz,
  revoked_by          uuid REFERENCES app_user(id)
);
CREATE UNIQUE INDEX ux_grant_active ON company_key_grant (company_key_id, user_id) WHERE revoked_at IS NULL;

CREATE TABLE company_key_recovery (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id            uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  company_key_id        uuid NOT NULL REFERENCES company_key(id) ON DELETE CASCADE,
  method                text NOT NULL CHECK (method IN ('recovery_code','shamir_share')),
  share_index           smallint,                              -- per shamir
  share_threshold       smallint,
  encrypted_private_key bytea NOT NULL,                        -- secretbox(privkey, KDF(codice))
  kdf_params            jsonb NOT NULL,
  created_by            uuid REFERENCES app_user(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  used_at               timestamptz
);

-- ============================================================================
-- 8. Job, export, audit
-- ============================================================================

CREATE TABLE async_job (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  requested_by     uuid REFERENCES app_user(id),
  kind             text NOT NULL CHECK (kind IN ('pdf_report','export_dataset','export_regional','import_historical','rebuild_tiles','anonymize','reencrypt')),
  status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','cancelled')),
  params           jsonb NOT NULL DEFAULT '{}'::jsonb,         -- mai dati personali
  progress         smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  result_object_key text,                                      -- chiave su object storage
  result_filename  text,
  result_mime      text,
  error_code       text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  finished_at      timestamptz,
  expires_at       timestamptz                                 -- cancellazione file risultato
);
CREATE INDEX ix_job_company_status ON async_job (company_id, status, created_at DESC);
ALTER TABLE import_batch ADD CONSTRAINT fk_import_job FOREIGN KEY (job_id) REFERENCES async_job(id);

CREATE TABLE export_run (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id                uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  job_id                    uuid NOT NULL UNIQUE REFERENCES async_job(id) ON DELETE CASCADE,
  template_code             text NOT NULL,                     -- 'veneto_a01' | 'dataset_events' | 'dataset_persons'
  format                    text NOT NULL CHECK (format IN ('xlsx','xls','csv','pdf')),
  filters                   jsonb NOT NULL,
  administrative_area_code  text,                              -- codice ISTAT provincia/regione
  quality_preview           jsonb,                             -- {persons_total, excluded_in_buildings, duplicate_groups, exportable}
  row_count                 int,
  created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id              bigint GENERATED ALWAYS AS IDENTITY,
  company_id      uuid NOT NULL,
  actor_user_id   uuid,
  actor_device_id uuid,
  action          text NOT NULL,                               -- 'person.identity_read', 'event.unlock', ...
  object_type     text NOT NULL,
  object_id       uuid,
  event_id        uuid,                                        -- per raggruppare
  changed_fields  text[] NOT NULL DEFAULT '{}',                -- solo nomi, mai valori
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
  ip              inet,
  user_agent      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
CREATE INDEX ix_audit_company_time ON audit_log (company_id, created_at DESC);
CREATE INDEX ix_audit_object ON audit_log (company_id, object_type, object_id);
-- partizioni mensili create da job beat: audit_log_2026_09 ... ; REVOKE UPDATE, DELETE ON audit_log FROM safe_app;

-- ============================================================================
-- 9. Trigger
-- ============================================================================

-- updated_at
DO $$ DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['company','team','app_user','ski_area','zone','slope','event','person'] LOOP
    EXECUTE format('CREATE TRIGGER trg_%s_updated BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at()', t, t);
  END LOOP;
END $$;

-- season, istat_comune, altitude, coerenza territorio, company della persona
CREATE OR REPLACE FUNCTION trg_event_before() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_tz text; v_local date;
BEGIN
  SELECT timezone INTO v_tz FROM company WHERE id = NEW.company_id;
  v_local := (NEW.dateandtime AT TIME ZONE COALESCE(v_tz, 'Europe/Rome'))::date;
  SELECT id INTO NEW.season_id FROM season WHERE v_local BETWEEN start_date AND end_date;
  IF NEW.season_id IS NULL THEN RAISE EXCEPTION 'no season for date %', v_local USING ERRCODE = '23514'; END IF;

  IF NEW.zone_id IS NOT NULL THEN
    IF NEW.ski_area_id IS NULL THEN SELECT ski_area_id INTO NEW.ski_area_id FROM zone WHERE id = NEW.zone_id; END IF;
    IF NOT EXISTS (SELECT 1 FROM zone WHERE id = NEW.zone_id AND ski_area_id = NEW.ski_area_id AND company_id = NEW.company_id)
      THEN RAISE EXCEPTION 'zone/ski_area mismatch' USING ERRCODE = '23514'; END IF;
  END IF;
  IF NEW.slope_id IS NOT NULL THEN
    IF NEW.zone_id IS NULL THEN SELECT zone_id INTO NEW.zone_id FROM slope WHERE id = NEW.slope_id; END IF;
    IF NOT EXISTS (SELECT 1 FROM slope WHERE id = NEW.slope_id AND zone_id = NEW.zone_id AND company_id = NEW.company_id)
      THEN RAISE EXCEPTION 'slope/zone mismatch' USING ERRCODE = '23514'; END IF;
    IF NEW.difficulty_id IS NULL THEN SELECT difficulty_id INTO NEW.difficulty_id FROM slope WHERE id = NEW.slope_id; END IF;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM team WHERE id = NEW.team_id AND company_id = NEW.company_id)
    THEN RAISE EXCEPTION 'team belongs to another company' USING ERRCODE = '23514'; END IF;

  IF NEW.geom IS NOT NULL AND (TG_OP = 'INSERT' OR NOT ST_Equals(NEW.geom, OLD.geom)) THEN
    SELECT code INTO NEW.istat_comune_code FROM istat_admin_unit
      WHERE level = 'municipality' AND ST_Intersects(geom, NEW.geom)
      ORDER BY edition_year DESC LIMIT 1;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_event_before BEFORE INSERT OR UPDATE ON event FOR EACH ROW EXECUTE FUNCTION trg_event_before();

CREATE OR REPLACE FUNCTION trg_person_before() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  SELECT company_id INTO NEW.company_id FROM event WHERE id = NEW.event_id;
  IF NEW.gravest_injury_id IS NOT NULL AND NEW.injury_place_id IS NULL THEN
    SELECT parent_id INTO NEW.injury_place_id FROM lookup_value WHERE id = NEW.gravest_injury_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_person_before BEFORE INSERT OR UPDATE ON person FOR EACH ROW EXECUTE FUNCTION trg_person_before();

-- invalidazione cache statistiche
CREATE OR REPLACE FUNCTION trg_bump_data_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE company SET data_version = data_version + 1 WHERE id = COALESCE(NEW.company_id, OLD.company_id);
  RETURN NULL;
END $$;
CREATE TRIGGER trg_event_version  AFTER INSERT OR UPDATE OR DELETE ON event  FOR EACH ROW EXECUTE FUNCTION trg_bump_data_version();
CREATE TRIGGER trg_person_version AFTER INSERT OR UPDATE OR DELETE ON person FOR EACH ROW EXECUTE FUNCTION trg_bump_data_version();

-- ============================================================================
-- 10. Row Level Security
-- ============================================================================

DO $$ DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'team','app_user','ski_area','zone','slope','lift','import_batch','event','person',
    'device_enrollment_code','mobile_device','user_key','company_key','company_key_grant',
    'company_key_recovery','async_job','export_run','audit_log','company_lookup_disabled'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (company_id = current_company_id()) WITH CHECK (company_id = current_company_id())', t);
  END LOOP;
END $$;

-- company: la riga del tenant corrente
ALTER TABLE company ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON company USING (id = current_company_id());

-- lookup_value / role: globali (company_id IS NULL) + propri
ALTER TABLE lookup_value ENABLE ROW LEVEL SECURITY;
CREATE POLICY lookup_visible ON lookup_value USING (company_id IS NULL OR company_id = current_company_id())
  WITH CHECK (company_id = current_company_id());
ALTER TABLE role ENABLE ROW LEVEL SECURITY;
CREATE POLICY role_visible ON role USING (company_id IS NULL OR company_id = current_company_id())
  WITH CHECK (company_id = current_company_id());

-- tabelle figlie senza company_id: protette per join (policy via EXISTS)
ALTER TABLE person_evacuation_mean ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_person ON person_evacuation_mean USING (EXISTS (SELECT 1 FROM person p WHERE p.id = person_id));
ALTER TABLE person_diagnosis ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_person ON person_diagnosis USING (EXISTS (SELECT 1 FROM person p WHERE p.id = person_id));
ALTER TABLE person_injury ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_person ON person_injury USING (EXISTS (SELECT 1 FROM person p WHERE p.id = person_id));
ALTER TABLE person_protection ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_person ON person_protection USING (EXISTS (SELECT 1 FROM person p WHERE p.id = person_id));
ALTER TABLE event_operator ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_event ON event_operator USING (EXISTS (SELECT 1 FROM event e WHERE e.id = event_id));
ALTER TABLE user_team ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_user ON user_team USING (EXISTS (SELECT 1 FROM app_user u WHERE u.id = user_id));
ALTER TABLE user_role ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_user ON user_role USING (EXISTS (SELECT 1 FROM app_user u WHERE u.id = user_id));
ALTER TABLE user_permission ENABLE ROW LEVEL SECURITY;
CREATE POLICY via_user ON user_permission USING (EXISTS (SELECT 1 FROM app_user u WHERE u.id = user_id));

-- Privilegi runtime
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO safe_app;
-- REVOKE UPDATE, DELETE ON audit_log FROM safe_app;   -- append-only
-- REVOKE ALL ON permission, season, country, istat_admin_unit FROM safe_app; GRANT SELECT ON ... TO safe_app;

-- ============================================================================
-- 11. Seed minimo (estratto)
-- ============================================================================

INSERT INTO season (code, start_date, end_date) VALUES
  ('2023/2024','2023-06-01','2024-05-31'), ('2024/2025','2024-06-01','2025-05-31'),
  ('2025/2026','2025-06-01','2026-05-31'), ('2026/2027','2026-06-01','2027-05-31');

INSERT INTO lookup_value (dimension, code, label_it, label_en, label_de, sort_order, mapping) VALUES
  ('cause','accidental_fall','Caduta accidentale','Accidental fall','Sturz',10,'{"veneto_a01":"Caduta accidentale"}'),
  ('cause','collision_person','Collisione con persona/e','Collision with person(s)','Kollision mit Person(en)',20,'{"veneto_a01":"Collisione altro sciatore"}'),
  ('cause','collision_fixed_obstacle','Collisione con ostacolo fisso','Collision with fixed obstacle','Kollision mit festem Hindernis',25,'{"veneto_a01":"Collisione ostacolo fisso"}'),
  ('cause','collision_mobile_obstacle','Collisione con ostacolo mobile','Collision with mobile obstacle','Kollision mit beweglichem Hindernis',30,'{"veneto_a01":"Collisione ostacolo mobile"}'),
  ('cause','illness','Malore','Illness','Unwohlsein',40,'{"veneto_a01":"Malore"}'),
  ('cause','lift','Incidente impianto di risalita','Lift accident','Liftunfall',50,'{"veneto_a01":"Incidente impianto risalita"}'),
  ('cause','other','Altro','Other','Sonstiges',90,'{"veneto_a01":"Altro"}'),
  ('equipment','ski','Sci','Ski','Ski',10,'{"veneto_a01":"Sci"}'),
  ('equipment','snowboard','Snowboard','Snowboard','Snowboard',20,'{"veneto_a01":"Snowboard"}'),
  ('equipment','ski_touring','Sci alpinismo','Ski touring','Skitouren',30,'{"veneto_a01":"Altro"}'),
  ('equipment','telemark','Telemark','Telemark','Telemark',40,'{"veneto_a01":"Altro"}'),
  ('equipment','other','Altro','Other','Sonstiges',90,'{"veneto_a01":"Altro"}'),
  ('evacuation_mean','akja','Akja/Toboga','Akja/Toboggan','Akja',10,'{}'),
  ('evacuation_mean','snowmobile','Motoslitta','Snowmobile','Schneemobil',20,'{}'),
  ('evacuation_mean','ambulance','Ambulanza','Ambulance','Krankenwagen',30,'{}'),
  ('evacuation_mean','helicopter_118','Elicottero 118','Helicopter 118','Hubschrauber 118',40,'{}'),
  ('evacuation_mean','lift','Impianto','Lift','Lift',50,'{}'),
  ('evacuation_mean','car','Autovettura','Car','Auto',60,'{}'),
  ('evacuation_mean','autonomous','Autonomamente','Autonomously','Selbständig',70,'{}'),
  ('evacuation_mean','other','Altro','Other','Sonstiges',90,'{}'),
  ('injury_place','lower_limbs','Arti inferiori','Lower limbs','Untere Gliedmaßen',10,'{}'),
  ('injury_place','upper_limbs','Arti superiori','Upper limbs','Obere Gliedmaßen',20,'{}'),
  ('injury_place','head_face','Cranio o faccia','Head or face','Kopf oder Gesicht',30,'{}'),
  ('injury_place','trunk','Tronco','Trunk','Rumpf',40,'{}'),
  ('weather','clear','Sereno','Clear','Heiter',10,'{}'),
  ('weather','partly_cloudy','Parzialmente nuvoloso','Partly cloudy','Teilweise bewölkt',20,'{}'),
  ('weather','cloudy','Nuvoloso','Cloudy','Bewölkt',30,'{}'),
  ('weather','snow','Neve','Snow','Schnee',40,'{}'),
  ('weather','rain','Pioggia','Rain','Regen',50,'{}'),
  ('weather','fog','Nebbia','Fog','Nebel',60,'{}'),
  ('snow_condition','packed','Compatta','Packed','Kompakt',10,'{}'),
  ('snow_condition','hard','Dura','Hard','Hart',20,'{}'),
  ('snow_condition','fresh','Fresca','Fresh','Neuschnee',30,'{}'),
  ('snow_condition','powder','Farinosa','Powder','Pulver',40,'{}'),
  ('snow_condition','wet','Umida/Bagnata','Wet','Nass',50,'{}'),
  ('snow_condition','crusty','Crostosa','Crusty','Harsch',60,'{}'),
  ('wind','none','Assente','None','Kein Wind',10,'{}'),
  ('wind','light','Debole','Light','Schwach',20,'{}'),
  ('wind','moderate','Moderato','Moderate','Mäßig',30,'{}'),
  ('wind','strong','Forte','Strong','Stark',40,'{}'),
  ('visibility','good','Buona','Good','Gut',10,'{}'),
  ('visibility','fair','Sufficiente','Fair','Ausreichend',20,'{}'),
  ('visibility','poor','Scarsa','Poor','Schlecht',30,'{}'),
  ('gender','male','Maschile','Male','Männlich',10,'{"veneto_a01":"Maschio"}'),
  ('gender','female','Femminile','Female','Weiblich',20,'{"veneto_a01":"Femmina"}'),
  ('gender','other','Altro','Other','Divers',30,'{}'),
  ('slope_difficulty','ski_school','Campo scuola','Ski school','Übungshang',5,'{}'),
  ('slope_difficulty','blue','Azzurra','Blue','Blau',10,'{}'),
  ('slope_difficulty','red','Rossa','Red','Rot',20,'{}'),
  ('slope_difficulty','black','Nera','Black','Schwarz',30,'{}'),
  ('location_type','open_slope','Pista aperta','Open slope','Geöffnete Piste',10,'{}'),
  ('location_type','off_piste','Fuoripista','Off-piste','Abseits der Piste',20,'{}'),
  ('location_type','closed_slope','Pista chiusa','Closed slope','Gesperrte Piste',30,'{}'),
  ('location_type','lift','Impianto','Lift','Lift',40,'{}'),
  ('location_type','race_slope','Pista gara','Race slope','Rennpiste',50,'{}'),
  ('location_type','building','Edificio','Building','Gebäude',60,'{"regional_export_exclude": true}'),
  ('location_type','snowpark','Snowpark/Cross/Halfpipe','Snowpark','Snowpark',70,'{}'),
  ('location_type','trail','Sentieri, escursioni','Trails','Wanderwege',80,'{}'),
  ('location_type','lift_station','Partenza/arrivo impianto','Lift station','Liftstation',85,'{}'),
  ('location_type','other','Altro','Other','Sonstiges',90,'{}'),
  ('team_body','operator','Gestore','Operator','Betreiber',10,'{}'),
  ('team_body','carabinieri','Carabinieri','Carabinieri','Carabinieri',20,'{}'),
  ('team_body','alpine_troops','Truppe Alpine','Alpine Troops','Gebirgsjäger',30,'{}'),
  ('team_body','police','Polizia','Police','Polizei',40,'{}'),
  ('team_body','finance_guard','Guardia di Finanza','Finance Guard','Finanzpolizei',50,'{}'),
  ('team_body','alpine_rescue','Soccorso Alpino','Alpine Rescue','Bergrettung',60,'{}'),
  ('team_body','ems_118','118','EMS 118','Rettungsdienst 118',70,'{}'),
  ('team_body','other','Altro','Other','Sonstiges',90,'{}');
-- diagnosis, accommodation, destination, insurance, responsibility, body_part, person_role,
-- equipment_owner, equipment_condition, protection, rescue_refusal, location_feature, traffic,
-- snow_making, event_type: seed completo nella migrazione 0002_seed_lookups.
