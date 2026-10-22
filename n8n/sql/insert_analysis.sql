INSERT INTO reports.report_analyses (run_id, requested_by, model, prompt_version, analysis, final_html)
VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6)
RETURNING analysis_id, run_id, created_at
