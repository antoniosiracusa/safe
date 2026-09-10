-- Eseguito una sola volta alla creazione del volume PostgreSQL (sviluppo e CI).
-- Il superuser (postgres) non viene mai usato dall'applicazione: la RLS non si applica ai superuser.

-- Database di Keycloak
CREATE USER keycloak WITH PASSWORD 'keycloak';
CREATE DATABASE keycloak OWNER keycloak;

-- Ruolo applicativo: proprietario dello schema ma NON superuser, così FORCE ROW LEVEL SECURITY
-- si applica anche a lui. CREATEDB serve al test runner di Django.
CREATE ROLE safe_owner LOGIN PASSWORD 'safe' CREATEDB;
CREATE DATABASE safe OWNER safe_owner;

-- Ruolo di amministrazione piattaforma (bypassa RLS): solo per comandi di management dedicati.
CREATE ROLE safe_admin LOGIN PASSWORD 'safe_admin' BYPASSRLS;
GRANT CONNECT ON DATABASE safe TO safe_admin;

\connect safe
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
GRANT USAGE ON SCHEMA public TO safe_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE safe_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO safe_admin;

-- Il template dei database di test deve avere PostGIS: Django lo crea da template1.
\connect template1
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
