-- Eseguito una sola volta alla creazione del volume PostgreSQL (sviluppo).
-- Crea il database di Keycloak e i ruoli applicativi previsti dal DDL (docs/02-ddl.sql).

CREATE USER keycloak WITH PASSWORD 'keycloak';
CREATE DATABASE keycloak OWNER keycloak;

-- Ruolo runtime soggetto a Row Level Security (non owner delle tabelle).
CREATE ROLE safe_app LOGIN PASSWORD 'safe_app';
-- Ruolo di amministrazione piattaforma (bypassa RLS, usato solo da comandi di management).
CREATE ROLE safe_admin LOGIN PASSWORD 'safe_admin' BYPASSRLS;

\connect safe
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;
GRANT CONNECT ON DATABASE safe TO safe_app, safe_admin;
GRANT USAGE ON SCHEMA public TO safe_app, safe_admin;
-- I GRANT sulle tabelle sono applicati dalle migrazioni Django (safe.apps.tenancy).
