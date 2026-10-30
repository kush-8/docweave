-- Operator-reviewed recovery only. Passwords are psql variables supplied privately through stdin.
-- This changes credentials, creates the restricted worker if absent, and preserves application rows.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL standard_conforming_strings=on;
ALTER ROLE docweave_migrator PASSWORD :'migration_password';
ALTER ROLE docweave_runtime PASSWORD :'runtime_password';
SELECT format('CREATE ROLE docweave_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='docweave_worker')
\gexec
ALTER ROLE docweave_worker PASSWORD :'worker_password';
GRANT CONNECT ON DATABASE :"DBNAME" TO docweave_worker;
GRANT USAGE ON SCHEMA app,public TO docweave_worker;
CREATE SCHEMA IF NOT EXISTS queue AUTHORIZATION docweave_migrator;
COMMIT;
