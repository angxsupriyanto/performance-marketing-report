-- Manual edits of analysis panels. Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/005_analysis_edits.sql
--
-- Re-running is safe.
--
-- Design:
--   * analysis_edits is append-only, like report_analyses. Saving an edit adds a row; nothing is updated or deleted, so every
--     edited version stays in the history.
--   * One row is one panel (panel_key, e.g. executive_summary or hardware_dashcam) of one run. body NULL means "restore the
--     AI version" for that panel.
--   * The text shown for a panel is its newest edit row, but only when that row is newer than the run's newest AI analysis.
--     Creating a new AI analysis therefore replaces all panels, and the older edits stay stored as history.
--   * edited_by is the username of the admin who saved the edit. The viewer role can SELECT and INSERT only.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.analysis_edits (
    edit_id    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id     uuid        NOT NULL REFERENCES reports.report_runs (run_id) ON DELETE RESTRICT,
    panel_key  text        NOT NULL CHECK (panel_key ~ '^[a-z0-9_]{1,64}$'),
    body       text        CHECK (body IS NULL OR char_length(body) BETWEEN 1 AND 4000),
    edited_by  text        NOT NULL CHECK (char_length(edited_by) BETWEEN 1 AND 64),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analysis_edits_lookup_idx ON reports.analysis_edits (run_id, panel_key, created_at DESC);

REVOKE ALL ON reports.analysis_edits FROM PUBLIC;
GRANT SELECT, INSERT ON reports.analysis_edits TO report_viewer;
GRANT SELECT ON reports.analysis_edits TO report_writer, report_reader;

RESET ROLE;
