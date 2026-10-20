#!/bin/sh
# Adds the targets table and the report_viewer role to an EXISTING marketing_reports database (after
# install-reports-db.sh). Safe to run again: the role keeps its password, tables are kept.
#
#   deploy/install-viewer-db.sh --container <postgres container> --admin-user <superuser> [--password-dir DIR]
#
# The viewer password is generated here into <DIR>/reports_db_viewer_password (mode 600) and reaches psql through
# stdin only, so it never appears on a command line, in `ps`, or on screen. If the admin role needs a password,
# export PGPASSWORD in your shell first; it is passed by name only.
set -eu

container=""; admin=""; password_dir="./reports_db_secrets"
while [ $# -gt 0 ]; do
  case "$1" in
    --container) container="$2"; shift 2 ;;
    --admin-user) admin="$2"; shift 2 ;;
    --password-dir) password_dir="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done
[ -n "$container" ] && [ -n "$admin" ] || { echo "usage: --container NAME --admin-user USER [--password-dir DIR]" >&2; exit 64; }

here=$(cd "$(dirname "$0")/.." && pwd)
sql_dir="$here/database"
[ -f "$sql_dir/002_targets_and_viewer.sql" ] || { echo "missing $sql_dir/002_targets_and_viewer.sql" >&2; exit 66; }

pgenv=""; [ -n "${PGPASSWORD:-}" ] && pgenv="-e PGPASSWORD"
# shellcheck disable=SC2086
psql_in() { docker exec -i $pgenv "$container" psql -X -v ON_ERROR_STOP=1 -U "$admin" "$@"; }

exists=$(psql_in -At -d postgres -c "SELECT count(*) FROM pg_database WHERE datname = 'marketing_reports'") || { echo "could not run psql in the container" >&2; exit 65; }
[ "$exists" = "1" ] || { echo "marketing_reports does not exist; run deploy/install-reports-db.sh first" >&2; exit 2; }

umask 077
mkdir -p "$password_dir"
file="$password_dir/reports_db_viewer_password"
[ -s "$file" ] || openssl rand -hex 24 > "$file"
chmod 600 "$file"
viewer=$(tr -d '\r\n' < "$file")

echo "== Creating the report_viewer role and the targets table"
{ printf "\\\\set viewer_password '%s'\n" "$viewer"; cat "$sql_dir/002_targets_and_viewer.sql"; } | psql_in -q -d marketing_reports -f -

echo "== Checking"
checks=$(psql_in -At -d marketing_reports -f - < "$sql_dir/verify_install.sql")
echo "$checks"
if echo "$checks" | grep -q "FAIL"; then echo "== A check failed; see above." >&2; exit 1; fi
echo "== Done. The viewer password is in $file (mode 600). If the role already existed, its password was not changed."
