-- Read-only check to run on the EXISTING server before database/000_*.sql. It changes nothing.
--
--   psql -d postgres -f database/preflight.sql
--
-- Every row should say OK. REVIEW means "look before continuing"; PROBLEM means the scripts should not be run as is.

SELECT check_name, status, detail FROM (
  SELECT 1 AS n, 'server is PostgreSQL 13 or newer' AS check_name,
         CASE WHEN current_setting('server_version_num')::int >= 130000 THEN 'OK' ELSE 'PROBLEM' END AS status,
         'server_version = ' || current_setting('server_version') AS detail
  UNION ALL
  SELECT 2, 'database marketing_reports does not exist yet',
         CASE WHEN EXISTS (SELECT 1 FROM pg_database WHERE datname = 'marketing_reports') THEN 'PROBLEM' ELSE 'OK' END,
         'if it exists, the scripts would reuse it instead of creating a new one'
  UNION ALL
  SELECT 3, 'no role named report_owner, report_writer or report_reader yet',
         CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('report_owner', 'report_writer', 'report_reader')) THEN 'REVIEW' ELSE 'OK' END,
         'if any exist, the scripts reuse them and do NOT change their passwords'
  UNION ALL
  SELECT 4, 'current role can create databases and roles',
         CASE WHEN r.rolsuper OR (r.rolcreatedb AND r.rolcreaterole) THEN 'OK' ELSE 'PROBLEM' END,
         'connected as ' || current_user
  FROM pg_roles r WHERE r.rolname = current_user
  UNION ALL
  SELECT 5, 'server accepts new connections for another database',
         CASE WHEN current_setting('max_connections')::int - (SELECT count(*) FROM pg_stat_activity) >= 20 THEN 'OK' ELSE 'REVIEW' END,
         'max_connections = ' || current_setting('max_connections') || ', in use = ' || (SELECT count(*) FROM pg_stat_activity)
) checks
ORDER BY n;
