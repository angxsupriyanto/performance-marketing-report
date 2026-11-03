-- How long a lead's MQL, SQL and Deal Won stay valid after its Inbound Date, per company: a general limit per stage and special limits per
-- Remark (for example Trial gets 12 months). Set in the viewer by an admin; read by n8n and handed to the report generator.
-- Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/012_lead_validity.sql
--
-- Re-running is safe.
--
-- Design:
--   * lead_validity_settings is append-only. Every save adds one row holding the complete setting for one company (bu); earlier rows stay as
--     history. The newest row per company is the one in force. A company without a row falls back to the limits written in its profile file.
--   * config is {"defaults": {"MQL": null|months, "SQL": ..., "Deal Won": ...}, "remarks": [{"remark": text, "MQL": "default"|null|months, ...}]}.
--     null means no limit, "default" means "follow the general limit". The generator checks the content again; the CHECK below only guards the shape.
--   * A report records the settings it used, and the settings are part of its input identity, so changing them and generating again makes
--     a new report instead of being skipped as a duplicate. Reports made earlier are not changed.
--   * The viewer role can SELECT and INSERT only. The writer role (n8n) and the reader role can SELECT.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.lead_validity_settings (
    settings_id uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    bu          text        NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    config      jsonb       NOT NULL CHECK (jsonb_typeof(config) = 'object' AND jsonb_typeof(config -> 'defaults') = 'object'
                                            AND jsonb_typeof(coalesce(config -> 'remarks', '[]'::jsonb)) = 'array'
                                            AND jsonb_array_length(coalesce(config -> 'remarks', '[]'::jsonb)) <= 30
                                            AND pg_column_size(config) <= 8000),
    saved_by    text        NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 64),
    saved_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lead_validity_settings_lookup_idx ON reports.lead_validity_settings (bu, saved_at DESC);

REVOKE ALL ON reports.lead_validity_settings FROM PUBLIC;
GRANT SELECT, INSERT ON reports.lead_validity_settings TO report_viewer;
GRANT SELECT ON reports.lead_validity_settings TO report_writer, report_reader;

RESET ROLE;
