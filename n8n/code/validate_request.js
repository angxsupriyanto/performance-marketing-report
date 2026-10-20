// Webhook input check for the analysis and view workflows. Period is always explicit.
const BUS = ['bu1', 'bu2'];
const PERIOD = /^\d{4}-(W\d{2}|\d{2})$/;
const input = $input.first().json;
const source = Object.assign({}, input.query || {}, input.body || {});
const bu = String(source.bu || '').toLowerCase();
const period = String(source.period || '');
if (!BUS.includes(bu)) throw new Error(`bu harus salah satu dari: ${BUS.join(', ')}`);
if (!PERIOD.test(period)) throw new Error('period wajib diisi dengan format YYYY-Www atau YYYY-MM');
const requestedBy = String(source.requested_by || 'webhook').replace(/[^\w .@-]/g, '').slice(0, 64) || 'webhook';
return [{ json: { bu, period, requested_by: requestedBy } }];
