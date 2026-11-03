-- Extra information the admin types when asking for an analysis ("promo until the 16th", "tracking was down"). It goes to the model as context
-- and stays here as history; it is not shown in the report.
-- Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/010_analysis_notes.sql
--
-- Re-running is safe.
--
-- Design:
--   * analysis_notes is append-only, like report_actions. Every analysis request that carries the form adds one row for one period
--     (bu + period); the newest row prefills the next form and is the one the model receives. An empty note is a valid save (cleared).
--   * It is a separate table from report_actions on purpose: actions can be changed from the Action section without asking for an analysis,
--     and that must not reset the note.
--   * The viewer role can SELECT and INSERT only. The writer and reader roles can SELECT.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.analysis_notes (
    note_id  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu       text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    period   text        NOT NULL CHECK (period ~ '^[0-9]{4}-([0-9]{2}|W[0-9]{2})$'),
    note     text        NOT NULL CHECK (char_length(note) <= 1000),
    saved_by text        NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 64),
    saved_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analysis_notes_lookup_idx ON reports.analysis_notes (bu, period, saved_at DESC);

REVOKE ALL ON reports.analysis_notes FROM PUBLIC;
GRANT SELECT, INSERT ON reports.analysis_notes TO report_viewer;
GRANT SELECT ON reports.analysis_notes TO report_writer, report_reader;

RESET ROLE;
