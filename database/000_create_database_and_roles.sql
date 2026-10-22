-- Creates the dedicated reporting database and its roles. Run once as a superuser (or a role with CREATEDB and
-- CREATEROLE) connected to the maintenance database, passing passwords at run time so they never enter Git:
--
--   psql -v ON_ERROR_STOP=1 -d postgres \
--        -v writer_password="$REPORT_WRITER_PASSWORD" -v reader_password="$REPORT_READER_PASSWORD" \
--        -f database/000_create_database_and_roles.sql
--
-- Re-running is safe: existing roles and the database are left untouched (passwords are not changed).

SELECT 'CREATE ROLE report_owner NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_owner')
\gexec

SELECT format('CREATE ROLE report_writer LOGIN PASSWORD %L CONNECTION LIMIT 10 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'writer_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_writer')
\gexec

SELECT format('CREATE ROLE report_reader LOGIN PASSWORD %L CONNECTION LIMIT 5 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_reader')
\gexec

SELECT 'CREATE DATABASE marketing_reports OWNER report_owner ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'marketing_reports')
\gexec

REVOKE ALL ON DATABASE marketing_reports FROM PUBLIC;
GRANT CONNECT ON DATABASE marketing_reports TO report_writer, report_reader;
