#!/bin/sh
# Runs once, on first start of an empty data directory, inside the official postgres image
# (mounted at /docker-entrypoint-initdb.d). Creates the reporting database, roles and tables.
# Passwords come from Docker secrets, never from Git.
set -eu

SECRETS_DIR="${SECRETS_DIR:-/run/secrets}"
SQL_DIR="${SQL_DIR:-/sql}"
read_secret() { tr -d '\r\n' < "$SECRETS_DIR/$1"; }

writer_password="$(read_secret reports_db_writer_password)"
reader_password="$(read_secret reports_db_reader_password)"
[ "${#writer_password}" -ge 16 ] && [ "${#reader_password}" -ge 16 ] || { echo "passwords must be at least 16 characters" >&2; exit 1; }

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres \
     -v writer_password="$writer_password" -v reader_password="$reader_password" \
     -f "$SQL_DIR/000_create_database_and_roles.sql"
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname marketing_reports \
     -f "$SQL_DIR/001_reports_schema.sql"
