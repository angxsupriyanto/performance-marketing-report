INSERT INTO reports.process_results (job_id, bu, ok, message)
SELECT j.job_id, $2, $3::boolean, left($4, 500)
FROM reports.process_requests j
WHERE j.job_id = nullif($1, '')::uuid
ON CONFLICT (job_id, bu) DO NOTHING
RETURNING job_id
