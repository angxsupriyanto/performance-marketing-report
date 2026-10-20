-- Targets and the login role of the web viewer. Run after 001, connected to the maintenance database as a superuser,
-- passing the viewer password at run time so it never enters Git:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -v viewer_password="$REPORT_VIEWER_PASSWORD" \
--        -f database/002_targets_and_viewer.sql
--
-- Re-running is safe: the role keeps its password, existing tables and views are kept or refreshed.
--
-- Design:
--   * target_entries is append-only, like report_runs. Saving a target adds rows; nothing is updated or deleted, so
--     the history of who-set-what-when stays intact. The viewer has a single shared password, so rows carry no person.
--   * hardware_month rows: SQL Value target per hardware for one month, in effect from period_key (YYYY-MM) onward
--     until a later row for the same hardware replaces it.
--   * semester rows: target for one semester (YYYY-S1 or YYYY-S2). The yearly target is the sum of its two semesters.
--     BU1 targets are in rupiah (unit idr), BU2 targets are a count of Ecosystem SQL (unit count).
--   * Reports never contain targets. The viewer joins them at display time, so changing a target does not need a
--     new report run.
--   * Amount 0 means "no target". Clearing a target is therefore an INSERT of 0, not a DELETE.

SELECT format('CREATE ROLE report_viewer LOGIN PASSWORD %L CONNECTION LIMIT 10 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'viewer_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_viewer')
\gexec

GRANT CONNECT ON DATABASE marketing_reports TO report_viewer;

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.target_entries (
    entry_id    uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    bu          text          NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    scope       text          NOT NULL CHECK (scope IN ('hardware_month', 'semester')),
    product     text          CHECK (product IS NULL OR char_length(product) BETWEEN 1 AND 64),
    period_key  text          NOT NULL,
    unit        text          NOT NULL CHECK (unit IN ('idr', 'count')),
    amount      numeric(20,2) NOT NULL CHECK (amount >= 0),
    recorded_at timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT target_entries_shape CHECK (
        (scope = 'hardware_month' AND product IS NOT NULL AND unit = 'idr' AND period_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$')
        OR (scope = 'semester' AND product IS NULL AND period_key ~ '^[0-9]{4}-S[12]$')
    )
);

CREATE INDEX IF NOT EXISTS target_entries_lookup_idx
    ON reports.target_entries (bu, scope, product, period_key, recorded_at DESC);

-- Newest entry per target slot. Zero rows stay visible here so the history page can show a cleared target.
CREATE OR REPLACE VIEW reports.targets_latest AS
SELECT DISTINCT ON (bu, scope, coalesce(product, ''), period_key)
       entry_id, bu, scope, product, period_key, unit, amount, recorded_at
FROM reports.target_entries
ORDER BY bu, scope, coalesce(product, ''), period_key, recorded_at DESC, entry_id;

REVOKE ALL ON reports.target_entries, reports.targets_latest FROM PUBLIC;
GRANT USAGE ON SCHEMA reports TO report_viewer;
GRANT SELECT ON reports.report_runs, reports.report_analyses, reports.run_index, reports.latest_reports TO report_viewer;
GRANT SELECT ON reports.target_entries, reports.targets_latest TO report_viewer, report_writer, report_reader;
GRANT INSERT ON reports.target_entries TO report_viewer;

RESET ROLE;
