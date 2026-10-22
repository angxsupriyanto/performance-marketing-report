// Input check for the analysis and view workflows. Fields come from the manual-parameters node, the webhook
// body or the query string. Period is always explicit.
const BUS = ['bu1', 'bu2'];
const PERIOD = /^\d{4}-(W\d{2}|\d{2})$/;
const input = $input.first().json;
const source = Object.assign({}, input, input.query || {}, input.body || {});
const bu = String(source.bu || '').toLowerCase();
const period = String(source.period || '').trim();
if (!BUS.includes(bu)) throw new Error(`bu harus salah satu dari: ${BUS.join(', ')}`);
if (!PERIOD.test(period)) throw new Error('period wajib diisi dengan format YYYY-Www atau YYYY-MM');
const requestedBy = String(source.requested_by || 'manual').replace(/[^\w .@-]/g, '').slice(0, 64) || 'manual';
// Target numbers computed by the viewer (progress against targets). Plain numbers and labels only; anything else is dropped.
let targets = null;
if (input.body && input.body.targets && typeof input.body.targets === 'object' && !Array.isArray(input.body.targets)) {
  const text = JSON.stringify(input.body.targets);
  if (text.length > 20000) throw new Error('targets terlalu besar');
  targets = JSON.parse(text);
}
return [{ json: { bu, period, requested_by: requestedBy, targets } }];
