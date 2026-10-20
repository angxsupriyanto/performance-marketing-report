WITH ins AS (
  INSERT INTO reports.report_runs
    (bu, period, period_kind, period_start, period_end, source_sha256, generator_version,
     rows_total, rows_in_bu, rows_without_bu, metrics, audit, facts, analysis_keys, numeric_html)
  VALUES
    ($1, $2, $3, $4::date, $5::date, $6, $7,
     $8::int, $9::int, $10::int, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15)
  ON CONFLICT (bu, period, source_sha256) DO NOTHING
  RETURNING run_id
)
SELECT run_id, true AS inserted FROM ins
UNION ALL
SELECT run_id, false AS inserted
FROM reports.report_runs
WHERE bu = $1 AND period = $2 AND source_sha256 = $6 AND NOT EXISTS (SELECT 1 FROM ins)
