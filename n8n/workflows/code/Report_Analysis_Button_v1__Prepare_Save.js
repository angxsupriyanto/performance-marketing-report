const prepared = $('Prepare Analysis Request').first().json;
const request = $('Validate Request').first().json;
const applied = $input.first().json;
if (typeof applied.html !== 'string' || !applied.html) throw new Error('Layanan laporan tidak mengembalikan HTML');
const parsed = $('Parse Analysis').first().json;
const analysis = parsed.analysis;
const model = parsed.model || prepared.model;
return [{
  json: {
    params: [prepared.run_id, request.requested_by, model, prepared.prompt_version, JSON.stringify(analysis), applied.html],
    bu: request.bu,
    period: request.period,
  },
}];
