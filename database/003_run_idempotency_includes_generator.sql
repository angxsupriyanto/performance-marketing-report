-- A report is identified by its input AND the code that built it. Run as a superuser connected to marketing_reports:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/003_run_idempotency_includes_generator.sql
--
-- Before: (bu, period, source_sha256) was unique, so after a generator upgrade, re-running Report Generate on an
-- unchanged sheet inserted nothing and the old HTML stayed on screen. Now the generator version is part of the key:
-- identical input and identical code is still a no-op (n8n retries stay safe), new code adds a new run, and the
-- viewer shows the newest run. Old runs and their analyses are kept.
-- Safe to run twice.

SET ROLE report_owner;

ALTER TABLE reports.report_runs DROP CONSTRAINT IF EXISTS report_runs_idempotency;
ALTER TABLE reports.report_runs ADD CONSTRAINT report_runs_idempotency UNIQUE (bu, period, source_sha256, generator_version);

RESET ROLE;
