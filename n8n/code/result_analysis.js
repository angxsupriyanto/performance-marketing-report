const request = ref('Validate Request').first().json;
const saved = $input.first().json;
return [{ json: { bu: request.bu, period: request.period, run_id: saved.run_id, analysis_id: saved.analysis_id, created_at: saved.created_at } }];
