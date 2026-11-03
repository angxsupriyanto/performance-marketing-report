// Which companies to compute performance for. The sheet export is the only input; there is no period.
const BUS = ['bu1', 'bu2'];
const input = $input.first().json;
const source = Object.assign({}, input, input.body || {});
const requested = String(source.bu || 'all').toLowerCase();
if (requested !== 'all' && !BUS.includes(requested)) throw new Error(`bu harus salah satu dari: all, ${BUS.join(', ')}`);
const bus = requested === 'all' ? BUS : [requested];
const executed = (name) => {
  try { return $(name).isExecuted === true; } catch (e) { return false; }
};
const jobId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(source.job_id || '')) ? String(source.job_id).toLowerCase() : '';
return [{ json: { trigger: executed('Webhook Performa') ? 'webhook' : 'manual', job_id: jobId, plans: bus.map((bu) => ({ bu, period: '' })) } }];
