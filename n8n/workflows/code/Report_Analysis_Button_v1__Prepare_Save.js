const prepared = $('Prepare Analysis Request').first().json;
const request = $('Validate Request').first().json;
const applied = $input.first().json;
if (typeof applied.html !== 'string' || !applied.html) throw new Error('Layanan laporan tidak mengembalikan HTML');
const analysis = $('Parse Analysis').first().json.analysis;
return [{
  json: {
    params: [prepared.run_id, request.requested_by, prepared.model, prepared.prompt_version, JSON.stringify(analysis), applied.html],
    bu: request.bu,
    period: request.period,
  },
}];
