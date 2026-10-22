SELECT run_id, bu, period, facts, analysis_keys, numeric_html
FROM reports.report_runs
WHERE bu = $1 AND period = $2
ORDER BY generated_at DESC
LIMIT 1
