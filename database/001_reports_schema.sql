-- Schema for stored weekly/monthly reports. Run connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/001_reports_schema.sql
--
-- Design:
--   * report_runs is append-only. A run is the deterministic numeric report for one BU and period, built from one
--     exact input (source_sha256). Re-sending identical input is a no-op, so n8n retries cannot create duplicates.
--   * report_analyses is append-only too. Each press of the analysis button adds a row linked to the run it read.
--   * report_writer can only SELECT and INSERT; nobody has UPDATE or DELETE. Correct a mistake by inserting a new run.
--   * No credentials, and no lead-level rows, are stored. HTML contains company names only in the Top Contributor
--     and SQL list sections; treat the database as internal data.

-- Version-independent: PostgreSQL 14 and older still let everyone create objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

SET ROLE report_owner;

CREATE SCHEMA IF NOT EXISTS reports AUTHORIZATION report_owner;

CREATE TABLE IF NOT EXISTS reports.report_runs (
    run_id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu                text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    period            text        NOT NULL CHECK (period ~ '^[0-9]{4}-(W[0-9]{2}|[0-9]{2})$'),
    period_kind       text        NOT NULL CHECK (period_kind IN ('week', 'month')),
    period_start      date        NOT NULL,
    period_end        date        NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT now(),
    source_sha256     text        NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    generator_version text        NOT NULL,
    rows_total        integer     NOT NULL CHECK (rows_total >= 0),
    rows_in_bu        integer     NOT NULL CHECK (rows_in_bu >= 0),
    rows_without_bu   integer     NOT NULL CHECK (rows_without_bu >= 0),
    metrics           jsonb       NOT NULL,
    audit             jsonb       NOT NULL,
    facts             jsonb       NOT NULL,
    analysis_keys     jsonb       NOT NULL,
    numeric_html      text        NOT NULL,
    CONSTRAINT report_runs_period_shape CHECK ((period_kind = 'week') = (period LIKE '%-W%')),
    CONSTRAINT report_runs_period_order CHECK (period_end >= period_start),
    CONSTRAINT report_runs_idempotency UNIQUE (bu, period, source_sha256)
);

CREATE TABLE IF NOT EXISTS reports.report_analyses (
    analysis_id    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         uuid        NOT NULL REFERENCES reports.report_runs (run_id) ON DELETE RESTRICT,
    created_at     timestamptz NOT NULL DEFAULT now(),
    requested_by   text,
    model          text        NOT NULL,
    prompt_version text        NOT NULL,
    analysis       jsonb       NOT NULL,
    final_html     text        NOT NULL
);

CREATE INDEX IF NOT EXISTS report_runs_bu_period_idx ON reports.report_runs (bu, period, generated_at DESC);
CREATE INDEX IF NOT EXISTS report_analyses_run_idx ON reports.report_analyses (run_id, created_at DESC);

-- Index without the large columns, for Metabase and quick checks.
CREATE OR REPLACE VIEW reports.run_index AS
SELECT run_id, bu, period, period_kind, period_start, period_end, generated_at, source_sha256, generator_version,
       rows_total, rows_in_bu, rows_without_bu, metrics
FROM reports.report_runs;

-- The report to show for each BU and period: newest run, with its newest analysis if one exists.
CREATE OR REPLACE VIEW reports.latest_reports AS
SELECT r.run_id, r.bu, r.period, r.period_kind, r.period_start, r.period_end, r.generated_at,
       r.rows_without_bu, r.metrics, r.numeric_html,
       a.analysis_id, a.created_at AS analysis_created_at, a.model, a.prompt_version,
       a.analysis, COALESCE(a.final_html, r.numeric_html) AS html, (a.analysis_id IS NOT NULL) AS has_analysis
FROM (SELECT DISTINCT ON (bu, period) * FROM reports.report_runs ORDER BY bu, period, generated_at DESC) r
LEFT JOIN LATERAL (
    SELECT * FROM reports.report_analyses x WHERE x.run_id = r.run_id ORDER BY x.created_at DESC LIMIT 1
) a ON true;

REVOKE ALL ON SCHEMA reports FROM PUBLIC;
GRANT USAGE ON SCHEMA reports TO report_writer, report_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA reports FROM PUBLIC;
GRANT SELECT, INSERT ON reports.report_runs, reports.report_analyses TO report_writer;
GRANT SELECT ON reports.report_runs, reports.report_analyses, reports.run_index, reports.latest_reports TO report_writer, report_reader;

RESET ROLE;
