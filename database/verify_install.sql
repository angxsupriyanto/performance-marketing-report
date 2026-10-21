-- Read-only check of an installed marketing_reports database. Changes nothing, needs no passwords.
--
--   psql -U <admin> -d marketing_reports -f database/verify_install.sql
--
-- Every row should say PASS.

SELECT check_name, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS status FROM (
  SELECT 1 AS n, 'database is owned by report_owner' AS check_name,
         EXISTS (SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba WHERE d.datname = 'marketing_reports' AND r.rolname = 'report_owner') AS ok
  UNION ALL SELECT 2, 'report_writer, report_reader and report_owner exist with no elevated attributes',
         (SELECT count(*) = 3 FROM pg_roles WHERE rolname IN ('report_owner', 'report_writer', 'report_reader')
            AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls)
  UNION ALL SELECT 3, 'report_writer and report_reader can log in, report_owner cannot',
         (SELECT bool_and(CASE WHEN rolname = 'report_owner' THEN NOT rolcanlogin ELSE rolcanlogin END) FROM pg_roles WHERE rolname IN ('report_owner', 'report_writer', 'report_reader'))
  UNION ALL SELECT 4, 'PUBLIC cannot connect to marketing_reports',
         (SELECT d.datacl IS NOT NULL AND NOT EXISTS (SELECT 1 FROM aclexplode(d.datacl) a WHERE a.grantee = 0) FROM pg_database d WHERE d.datname = 'marketing_reports')
  UNION ALL SELECT 5, 'only report_writer, report_reader and report_viewer (and the owner) can connect',
         (SELECT NOT EXISTS (SELECT 1 FROM aclexplode(d.datacl) a JOIN pg_roles r ON r.oid = a.grantee
                              WHERE a.privilege_type = 'CONNECT' AND r.rolname NOT IN ('report_writer', 'report_reader', 'report_viewer', 'report_owner'))
           FROM pg_database d WHERE d.datname = 'marketing_reports')
  UNION ALL SELECT 6, 'tables report_runs and report_analyses exist',
         (SELECT count(*) = 2 FROM information_schema.tables WHERE table_schema = 'reports' AND table_name IN ('report_runs', 'report_analyses') AND table_type = 'BASE TABLE')
  UNION ALL SELECT 7, 'views run_index and latest_reports exist',
         (SELECT count(*) = 2 FROM information_schema.views WHERE table_schema = 'reports' AND table_name IN ('run_index', 'latest_reports'))
  UNION ALL SELECT 8, 'report_runs has the idempotency unique constraint (bu, period, source_sha256)',
         EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'report_runs_idempotency' AND contype = 'u')
  UNION ALL SELECT 9, 'report_writer can SELECT and INSERT but not UPDATE, DELETE or TRUNCATE',
         has_table_privilege('report_writer', 'reports.report_runs', 'SELECT') AND has_table_privilege('report_writer', 'reports.report_runs', 'INSERT')
         AND has_table_privilege('report_writer', 'reports.report_analyses', 'INSERT')
         AND NOT (has_table_privilege('report_writer', 'reports.report_runs', 'UPDATE') OR has_table_privilege('report_writer', 'reports.report_runs', 'DELETE') OR has_table_privilege('report_writer', 'reports.report_runs', 'TRUNCATE')
                  OR has_table_privilege('report_writer', 'reports.report_analyses', 'UPDATE') OR has_table_privilege('report_writer', 'reports.report_analyses', 'DELETE') OR has_table_privilege('report_writer', 'reports.report_analyses', 'TRUNCATE'))
  UNION ALL SELECT 10, 'report_reader can SELECT but not INSERT, UPDATE or DELETE',
         has_table_privilege('report_reader', 'reports.report_runs', 'SELECT') AND has_table_privilege('report_reader', 'reports.latest_reports', 'SELECT')
         AND NOT (has_table_privilege('report_reader', 'reports.report_runs', 'INSERT') OR has_table_privilege('report_reader', 'reports.report_runs', 'UPDATE') OR has_table_privilege('report_reader', 'reports.report_runs', 'DELETE'))
  UNION ALL SELECT 11, 'neither role can create objects in schemas reports or public',
         NOT (has_schema_privilege('report_writer', 'reports', 'CREATE') OR has_schema_privilege('report_reader', 'reports', 'CREATE') OR coalesce(has_schema_privilege(to_regrole('report_viewer'), 'reports', 'CREATE'), false)
              OR has_schema_privilege('report_writer', 'public', 'CREATE') OR has_schema_privilege('report_reader', 'public', 'CREATE') OR coalesce(has_schema_privilege(to_regrole('report_viewer'), 'public', 'CREATE'), false))
  UNION ALL SELECT 12, 'connection limits are 10 for report_writer and 5 for report_reader',
         (SELECT bool_and(rolconnlimit = CASE rolname WHEN 'report_writer' THEN 10 ELSE 5 END) FROM pg_roles WHERE rolname IN ('report_writer', 'report_reader'))
  UNION ALL SELECT 13, 'report_viewer exists without elevated attributes, can log in, and is limited to 10 connections',
         (SELECT count(*) = 1 FROM pg_roles WHERE rolname = 'report_viewer' AND rolcanlogin AND rolconnlimit = 10
            AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls)
  UNION ALL SELECT 14, 'table target_entries and view targets_latest exist',
         (SELECT count(*) = 2 FROM information_schema.tables WHERE table_schema = 'reports' AND table_name IN ('target_entries', 'targets_latest'))
  UNION ALL SELECT 15, 'report_viewer can SELECT reports and INSERT targets, and nothing else',
         has_table_privilege(to_regrole('report_viewer'), 'reports.latest_reports', 'SELECT') AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.target_entries'), 'INSERT')
         AND NOT (has_table_privilege(to_regrole('report_viewer'), 'reports.report_runs', 'INSERT') OR has_table_privilege(to_regrole('report_viewer'), 'reports.report_analyses', 'INSERT')
                  OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.target_entries'), 'UPDATE') OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.target_entries'), 'DELETE') OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.target_entries'), 'TRUNCATE')
                  OR has_table_privilege(to_regrole('report_viewer'), 'reports.report_runs', 'UPDATE') OR has_table_privilege(to_regrole('report_viewer'), 'reports.report_runs', 'DELETE'))
  UNION ALL SELECT 16, 'report_writer and report_reader cannot change targets',
         NOT (has_table_privilege('report_writer', to_regclass('reports.target_entries'), 'INSERT') OR has_table_privilege('report_writer', to_regclass('reports.target_entries'), 'UPDATE')
              OR has_table_privilege('report_reader', to_regclass('reports.target_entries'), 'INSERT') OR has_table_privilege('report_reader', to_regclass('reports.target_entries'), 'UPDATE'))
  UNION ALL SELECT 17, 'tables viewer_users and company_names exist; report_viewer can read and write them but not delete',
         (SELECT count(*) = 2 FROM information_schema.tables WHERE table_schema = 'reports' AND table_name IN ('viewer_users', 'company_names'))
         AND coalesce(has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.viewer_users'), 'SELECT') AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.viewer_users'), 'INSERT')
                      AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.viewer_users'), 'UPDATE') AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.company_names'), 'UPDATE')
                      AND NOT (has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.viewer_users'), 'DELETE') OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.viewer_users'), 'TRUNCATE')
                               OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.company_names'), 'DELETE')), false)
  UNION ALL SELECT 18, 'report_writer and report_reader cannot read viewer_users (password hashes)',
         NOT (has_table_privilege('report_writer', to_regclass('reports.viewer_users'), 'SELECT') OR has_table_privilege('report_reader', to_regclass('reports.viewer_users'), 'SELECT'))
  UNION ALL SELECT 19, 'analysis_edits exists; report_viewer can SELECT and INSERT but not UPDATE, DELETE or TRUNCATE',
         to_regclass('reports.analysis_edits') IS NOT NULL
         AND coalesce(has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.analysis_edits'), 'SELECT') AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.analysis_edits'), 'INSERT')
                      AND NOT (has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.analysis_edits'), 'UPDATE') OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.analysis_edits'), 'DELETE')
                               OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.analysis_edits'), 'TRUNCATE')), false)
  UNION ALL SELECT 20, 'budget_snapshots exists; report_viewer can SELECT and INSERT but not UPDATE, DELETE or TRUNCATE',
         to_regclass('reports.budget_snapshots') IS NOT NULL
         AND coalesce(has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.budget_snapshots'), 'SELECT') AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.budget_snapshots'), 'INSERT')
                      AND NOT (has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.budget_snapshots'), 'UPDATE') OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.budget_snapshots'), 'DELETE')
                               OR has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.budget_snapshots'), 'TRUNCATE')), false)
  UNION ALL SELECT 21, 'performance_snapshots exists; report_writer can SELECT and INSERT, report_viewer and report_reader can only SELECT, nobody can UPDATE or DELETE',
         to_regclass('reports.performance_snapshots') IS NOT NULL
         AND coalesce(has_table_privilege('report_writer', to_regclass('reports.performance_snapshots'), 'SELECT') AND has_table_privilege('report_writer', to_regclass('reports.performance_snapshots'), 'INSERT')
                      AND has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.performance_snapshots'), 'SELECT') AND has_table_privilege('report_reader', to_regclass('reports.performance_snapshots'), 'SELECT')
                      AND NOT (has_table_privilege(to_regrole('report_viewer'), to_regclass('reports.performance_snapshots'), 'INSERT') OR has_table_privilege('report_reader', to_regclass('reports.performance_snapshots'), 'INSERT')
                               OR has_table_privilege('report_writer', to_regclass('reports.performance_snapshots'), 'UPDATE') OR has_table_privilege('report_writer', to_regclass('reports.performance_snapshots'), 'DELETE')
                               OR has_table_privilege('report_writer', to_regclass('reports.performance_snapshots'), 'TRUNCATE')), false)
) checks
ORDER BY n;
