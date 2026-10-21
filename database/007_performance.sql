-- Aggregated performance series for the Performa page. Run after 001/002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/007_performance.sql
--
-- Re-running is safe.
--
-- Design:
--   * performance_snapshots is append-only, written by the n8n workflow "Performa Generate" through report_writer. Each row is
--     the whole picture of one company computed from one exact sheet export (source_sha256): per-day counts and values of
--     Submission, MQL, SQL and Deal Won, plus cohort counts per day, ISO week and calendar month. No lead rows, company names or
--     contact data are stored.
--   * Sending the same export again on the same day is a no-op (unique key); on a later day it adds a row, because the cohort columns that have elapsed by then differ.
--   * The viewer reads the newest snapshot of a company and does the range, day/week/month grouping and percentages at display time.
--   * data (jsonb) has the shape
--       {"v": 1, "as_of": "YYYY-MM-DD", "days": {"YYYY-MM-DD": {"sub": n, "mql": n, "sql": n, "sqlv": "n", "won": n, "wonv": "n"}},
--        "cohorts": {"day"|"week"|"month": [[start, size, mql_base, valid_columns, [mql_by_k x5], [sql_by_k x5], [sql_of_mql_by_k x5]], ...]}}

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.performance_snapshots (
    snapshot_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu                text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    generated_at      timestamptz NOT NULL DEFAULT now(),
    as_of             date        NOT NULL,
    source_sha256     text        NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    generator_version text        NOT NULL,
    data              jsonb       NOT NULL CHECK (jsonb_typeof(data) = 'object' AND coalesce(jsonb_typeof(data -> 'days'), '') = 'object' AND coalesce(jsonb_typeof(data -> 'cohorts'), '') = 'object'),
    CONSTRAINT performance_snapshots_idempotency UNIQUE (bu, as_of, source_sha256, generator_version)
);

CREATE INDEX IF NOT EXISTS performance_snapshots_latest_idx ON reports.performance_snapshots (bu, generated_at DESC);

REVOKE ALL ON reports.performance_snapshots FROM PUBLIC;
GRANT SELECT, INSERT ON reports.performance_snapshots TO report_writer;
GRANT SELECT ON reports.performance_snapshots TO report_reader, report_viewer;

RESET ROLE;
