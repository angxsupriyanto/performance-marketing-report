// Tells the viewer that a company's run failed. Runs once per failed item; `detail` is the capped, data-free reason built by the error formatter.
// Runs started from n8n's editor carry no job id: the insert then matches no request and stores nothing.
const jobId = ref('Normalize Plan').first().json.job_id || '';
return { json: { params: [jobId, $json.bu, false, String($json.detail || 'penyebab tidak diketahui').slice(0, 500)] } };
