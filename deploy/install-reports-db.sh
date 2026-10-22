#!/bin/sh
# Installs the marketing_reports database into an EXISTING PostgreSQL container (option A).
#
# Two stages, on purpose:
#   1. without --yes: runs database/preflight.sql and stops, so you can read the result.
#   2. with --yes   : creates the passwords (files, mode 600), the database, roles and tables.
#
# Passwords are generated here and written only to files in --password-dir. They are fed to psql through
# stdin, so they never appear on a command line, in `ps`, or on screen.
#
#   deploy/install-reports-db.sh --container <postgres container> --admin-user <superuser>
#   deploy/install-reports-db.sh --container <postgres container> --admin-user <superuser> --yes
#
# If the admin role needs a password, export PGPASSWORD in your shell first; it is passed by name only.
set -eu

container=""; admin=""; yes=0; password_dir="./reports_db_secrets"
while [ $# -gt 0 ]; do
  case "$1" in
    --container) container="$2"; shift 2 ;;
    --admin-user) admin="$2"; shift 2 ;;
    --password-dir) password_dir="$2"; shift 2 ;;
    --yes) yes=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done
[ -n "$container" ] && [ -n "$admin" ] || { echo "usage: --container NAME --admin-user USER [--password-dir DIR] [--yes]" >&2; exit 64; }

here=$(cd "$(dirname "$0")/.." && pwd)
sql_dir="$here/database"
for f in preflight.sql 000_create_database_and_roles.sql 001_reports_schema.sql; do
  [ -f "$sql_dir/$f" ] || { echo "missing $sql_dir/$f" >&2; exit 66; }
done

pgenv=""; [ -n "${PGPASSWORD:-}" ] && pgenv="-e PGPASSWORD"
# shellcheck disable=SC2086
psql_in() { docker exec -i $pgenv "$container" psql -X -v ON_ERROR_STOP=1 -U "$admin" "$@"; }

echo "== Preflight on container '$container' as '$admin' (read-only)"
preflight=$(psql_in -d postgres -f - < "$sql_dir/preflight.sql") || { echo "could not run psql in the container" >&2; exit 65; }
echo "$preflight"
if echo "$preflight" | grep -q "PROBLEM"; then
  echo "== Stopped: fix every PROBLEM row first. Nothing was changed." >&2; exit 2
fi
if echo "$preflight" | grep -q "REVIEW" && [ "$yes" -ne 1 ]; then
  echo "== REVIEW rows present. Read them, then rerun with --yes if they are expected." >&2; exit 3
fi
if [ "$yes" -ne 1 ]; then
  echo "== Preflight is clean. Nothing was changed. Rerun the same command with --yes to install."; exit 3
fi

umask 077
mkdir -p "$password_dir"
for role in writer reader; do
  file="$password_dir/reports_db_${role}_password"
  [ -s "$file" ] || openssl rand -hex 24 > "$file"
  chmod 600 "$file"
done
writer=$(tr -d '\r\n' < "$password_dir/reports_db_writer_password")
reader=$(tr -d '\r\n' < "$password_dir/reports_db_reader_password")

echo "== Creating database, roles and tables"
{ printf "\\\\set writer_password '%s'\n\\\\set reader_password '%s'\n" "$writer" "$reader"; cat "$sql_dir/000_create_database_and_roles.sql"; } | psql_in -q -d postgres -f -
psql_in -q -d marketing_reports -f - < "$sql_dir/001_reports_schema.sql"

echo "== Checking the new roles"
tables=$(psql_in -At -d marketing_reports -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'reports'")
[ "$tables" -ge 4 ] && echo "PASS: $tables objects in schema reports" || { echo "FAIL: schema reports looks incomplete" >&2; exit 1; }
roles=$(psql_in -At -d postgres -c "SELECT count(*) FROM pg_roles WHERE rolname IN ('report_owner','report_writer','report_reader') AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole")
[ "$roles" -eq 3 ] && echo "PASS: three report roles exist without elevated privileges" || { echo "FAIL: unexpected role attributes" >&2; exit 1; }

echo "== Done. Passwords are in $password_dir (mode 600). Put them into the n8n Postgres credentials, then keep the"
echo "   files out of Git and out of chat. Add marketing_reports to your backup routine."
