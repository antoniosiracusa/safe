#!/bin/bash
# Eseguito solo alla prima inizializzazione del volume: ruoli e database con le password di .env.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<SQL
CREATE ROLE safe_owner LOGIN PASSWORD '${SAFE_DB_PASSWORD}' CREATEDB;
CREATE ROLE safe_admin LOGIN PASSWORD '${SAFE_DB_PASSWORD}' BYPASSRLS;
CREATE ROLE keycloak LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';
CREATE DATABASE safe OWNER safe_owner;
CREATE DATABASE keycloak OWNER keycloak;
\connect safe
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
GRANT ALL ON SCHEMA public TO safe_owner;
SQL
