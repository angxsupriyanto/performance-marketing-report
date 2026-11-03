-- Report and Performa runs that an admin starts from the viewer ("Perbarui data"), and the result n8n reports back for each company.
-- Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/013_process_runs.sql
--
-- Re-running is safe.
--
-- Design:
--   * Two append-only tables, so that each role only ever INSERTs into its own table and nothing is updated:
--       process_requests: written by the viewer when an admin presses the button (who, what, which company and period).
--       process_results:  written by n8n when a company's run ends, success or failure, with a short message (never data rows).
--   * A request is "running" until every company it asked for has a result, "failed" when any result is a failure, and the viewer calls it
--     timed out when no result came within 5 minutes. The status is derived from these rows, so it survives a restart of the viewer and keeps
--     the buttons locked while a run is going on.
--   * bu is a company key, or 'all' for every company. period is empty for Performa, which has none.
--   * Runs started from n8n's own editor carry no job id and are not recorded here.
--   * The viewer role can SELECT and INSERT process_requests and SELECT process_results; the writer role can SELECT and INSERT process_results
--     and SELECT process_requests; the reader role can SELECT both. Nobody can UPDATE or DELETE.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.process_requests (
    job_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind         text        NOT NULL CHECK (kind IN ('report', 'performa')),
    bu           text        NOT NULL CHECK (bu = 'all' OR bu ~ '^[a-z0-9_]{1,32}$'),
    period       text        NOT NULL DEFAULT '' CHECK (period = '' OR period ~ '^[0-9]{4}-([0-9]{2}|W[0-9]{2})$'),
    requested_by text        NOT NULL CHECK (char_length(requested_by) BETWEEN 1 AND 64),
    requested_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT process_requests_period_shape CHECK ((kind = 'report') = (period <> ''))
);

CREATE TABLE IF NOT EXISTS reports.process_results (
    result_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      uuid        NOT NULL REFERENCES reports.process_requests (job_id) ON DELETE RESTRICT,
    bu          text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    ok          boolean     NOT NULL,
    message     text        NOT NULL DEFAULT '' CHECK (char_length(message) <= 500),
    finished_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT process_results_once UNIQUE (job_id, bu)
);

CREATE INDEX IF NOT EXISTS process_requests_lookup_idx ON reports.process_requests (kind, requested_at DESC);
CREATE INDEX IF NOT EXISTS process_results_job_idx ON reports.process_results (job_id);

REVOKE ALL ON reports.process_requests, reports.process_results FROM PUBLIC;
GRANT SELECT, INSERT ON reports.process_requests TO report_viewer;
GRANT SELECT ON reports.process_results TO report_viewer;
GRANT SELECT, INSERT ON reports.process_results TO report_writer;
GRANT SELECT ON reports.process_requests TO report_writer;
GRANT SELECT ON reports.process_requests, reports.process_results TO report_reader;

RESET ROLE;
