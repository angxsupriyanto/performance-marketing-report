-- Achievement figures an admin typed by hand because the Sheet was not complete yet: SQL Value per product for the report's month,
-- and the semester and 1-year progress (SQL Value for BU1, SQL count for the Ecosystem company).
-- Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/011_report_achievements.sql
--
-- Re-running is safe.
--
-- Design:
--   * report_achievements is append-only, like report_actions. Every save adds one row holding the whole set for one report (bu + period),
--     so earlier versions stay as history. The newest row is what the viewer shows. The system figures are never overwritten: they stay in the
--     stored report and the form shows them next to the typed ones.
--   * The figures belong to one report period, not to a month, because the cumulative figures depend on the week the report ends.
--   * values is {"hardware": {"<product>": number}, "semester": number, "year": number}; every key is optional, a missing key means "use the
--     system figure". An empty object is a valid save (all reset). A reason is required whenever values is not empty and is kept as history;
--     it is never shown in the report.
--   * The viewer role can SELECT and INSERT only. The writer and reader roles can SELECT.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.report_achievements (
    achievement_id uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu             text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    period         text        NOT NULL CHECK (period ~ '^[0-9]{4}-([0-9]{2}|W[0-9]{2})$'),
    values         jsonb       NOT NULL CHECK (jsonb_typeof(values) = 'object' AND pg_column_size(values) <= 4000),
    reason         text        NOT NULL CHECK (char_length(reason) <= 300),
    saved_by       text        NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 64),
    saved_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_achievements_reason_required CHECK (values = '{}'::jsonb OR char_length(btrim(reason)) > 0)
);

CREATE INDEX IF NOT EXISTS report_achievements_lookup_idx ON reports.report_achievements (bu, period, saved_at DESC);

REVOKE ALL ON reports.report_achievements FROM PUBLIC;
GRANT SELECT, INSERT ON reports.report_achievements TO report_viewer;
GRANT SELECT ON reports.report_achievements TO report_writer, report_reader;

RESET ROLE;
