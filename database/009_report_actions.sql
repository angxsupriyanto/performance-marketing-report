-- Actions the team took during a report period, typed in the viewer when an analysis is requested or edited from the report page.
-- Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/009_report_actions.sql
--
-- Re-running is safe.
--
-- Design:
--   * report_actions is append-only, like budget_snapshots. Every save adds one row holding the whole list for one period (bu + period),
--     so earlier versions stay as history. The newest row is the list the report shows and the analysis receives.
--   * The list belongs to the period, not to one generated run, so it survives a Report Generate that makes a new run for the same period.
--   * items is a JSON array of {"action": text, "campaign": text, "note": text}; the viewer checks the text and the sizes, the CHECK
--     below only guards the shape. An empty array is a valid save (all actions removed).
--   * The viewer role can SELECT and INSERT only. The writer and reader roles can SELECT.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.report_actions (
    actions_id uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu         text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    period     text        NOT NULL CHECK (period ~ '^[0-9]{4}-([0-9]{2}|W[0-9]{2})$'),
    items      jsonb       NOT NULL CHECK (jsonb_typeof(items) = 'array' AND jsonb_array_length(items) <= 30),
    saved_by   text        NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 64),
    saved_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS report_actions_lookup_idx ON reports.report_actions (bu, period, saved_at DESC);

REVOKE ALL ON reports.report_actions FROM PUBLIC;
GRANT SELECT, INSERT ON reports.report_actions TO report_viewer;
GRANT SELECT ON reports.report_actions TO report_writer, report_reader;

RESET ROLE;
