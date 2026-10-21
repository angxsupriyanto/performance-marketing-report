-- Budget and spend per company and month. Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/006_budget.sql
--
-- Re-running is safe.
--
-- Design:
--   * budget_snapshots is append-only. Saving the Budget page adds ONE row holding the whole picture of that company and month:
--     the total budget, the budget per campaign, the spend per campaign per ISO week, and the monthly spend per campaign with
--     the date it was filled up to. Nothing is updated or deleted, so every saved version stays in the history.
--   * data (jsonb) has the shape
--       {"campaigns": {"<name>": {"budget": n|null, "month_spend": n|null, "weeks": {"2026-W42": n}}}}
--     Amounts are whole rupiah. A campaign with no numbers can still be listed so that a manually added campaign survives.
--   * Weekly spend and monthly spend are entered separately and are never derived from each other: an ISO week can straddle
--     two months, and the ad platform's monthly total rarely equals the sum of whole weeks.
--   * The current budget, the weekly spend and the campaign list of a month come from its newest snapshot. A report picks the
--     monthly spend from the snapshot with the latest spend_as_of that is not after the report's last day (ties: newest save).
--   * Reports never contain budget. The viewer joins it at display time, like targets.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.budget_snapshots (
    snapshot_id  uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    bu           text          NOT NULL CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    month        text          NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    total_budget numeric(20,2) CHECK (total_budget IS NULL OR total_budget >= 0),
    spend_as_of  date,
    data         jsonb         NOT NULL CHECK (jsonb_typeof(data) = 'object' AND coalesce(jsonb_typeof(data -> 'campaigns'), '') = 'object'),
    saved_by     text          NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 64),
    saved_at     timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS budget_snapshots_lookup_idx ON reports.budget_snapshots (bu, month, saved_at DESC);

REVOKE ALL ON reports.budget_snapshots FROM PUBLIC;
GRANT SELECT, INSERT ON reports.budget_snapshots TO report_viewer;
GRANT SELECT ON reports.budget_snapshots TO report_writer, report_reader;

RESET ROLE;
