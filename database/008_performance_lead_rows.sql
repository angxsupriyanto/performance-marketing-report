-- Performance snapshots now hold one anonymous row per lead (format v2), so the Performa page can filter by Channel, Source, Medium,
-- Campaign, Category Campaign and Campaign Hardware. Run after 007, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/008_performance_lead_rows.sql
--
-- Re-running is safe. Existing v1 snapshots (per-day aggregates and cohort counts) stay valid; the page asks for a new Performa Generate run.
--
-- v2 shape: {"v": 2, "as_of": "YYYY-MM-DD",
--            "dims": {"channel": [...], "source": [...], "medium": [...], "campaign": [...], "category": [...], "hardware": [...]},
--            "leads": [[inbound, mql, sql, won, sql_value, won_value, channel, source, medium, campaign, category, hardware], ...]}
--   Dates are day numbers (Python date.toordinal(), 0 = no date); values are whole rupiah (or an exact decimal as text); the last six
--   numbers are positions in the matching `dims` list. No company name, contact or record key is stored.

SET ROLE report_owner;

ALTER TABLE reports.performance_snapshots DROP CONSTRAINT IF EXISTS performance_snapshots_data_check;
ALTER TABLE reports.performance_snapshots DROP CONSTRAINT IF EXISTS performance_snapshots_data_shape;
ALTER TABLE reports.performance_snapshots ADD CONSTRAINT performance_snapshots_data_shape CHECK (
    jsonb_typeof(data) = 'object' AND (
        (coalesce(jsonb_typeof(data -> 'days'), '') = 'object' AND coalesce(jsonb_typeof(data -> 'cohorts'), '') = 'object')
        OR (data ->> 'v' = '2' AND coalesce(jsonb_typeof(data -> 'dims'), '') = 'object' AND coalesce(jsonb_typeof(data -> 'leads'), '') = 'array')
    )
);

RESET ROLE;
