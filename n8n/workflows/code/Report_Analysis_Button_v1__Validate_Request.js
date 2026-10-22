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
// What the team did in the period (typed in the viewer) and the budget figures. Text and numbers only, with size limits; anything else is dropped.
const text = (value, max) => (typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max) : '');
const actions = [];
if (input.body && Array.isArray(input.body.actions)) {
  for (const entry of input.body.actions) {
    if (actions.length >= 30) break;
    if (!entry || typeof entry !== 'object') continue;
    const action = text(entry.action, 300);
    if (action) actions.push({ action, campaign: text(entry.campaign, 100), note: text(entry.note, 300) });
  }
}
let budget = null;
if (input.body && input.body.budget && typeof input.body.budget === 'object' && !Array.isArray(input.body.budget)) {
  const budgetText = JSON.stringify(input.body.budget);
  if (budgetText.length > 20000) throw new Error('budget terlalu besar');
  budget = JSON.parse(budgetText);
}
return [{ json: { bu, period, requested_by: requestedBy, targets, actions, budget } }];
