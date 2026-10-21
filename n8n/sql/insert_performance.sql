WITH ins AS (
  INSERT INTO reports.performance_snapshots (bu, as_of, source_sha256, generator_version, data)
  VALUES ($1, $2::date, $3, $4, $5::jsonb)
  ON CONFLICT (bu, as_of, source_sha256, generator_version) DO NOTHING
  RETURNING snapshot_id
)
SELECT snapshot_id, true AS inserted FROM ins
UNION ALL
SELECT snapshot_id, false AS inserted
FROM reports.performance_snapshots
WHERE bu = $1 AND as_of = $2::date AND source_sha256 = $3 AND generator_version = $4 AND NOT EXISTS (SELECT 1 FROM ins)
