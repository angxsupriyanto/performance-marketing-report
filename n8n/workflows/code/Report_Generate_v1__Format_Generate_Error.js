// Runs once per failed item (n8n requires a single { json } object in this mode, not an array).
// Builds a short, aggregate-only message. It reads only named fields of the error and caps the length, so no
// request body (the CSV) can leak into it. The service's own error text is a validation message and never a row.
let plan;
try { plan = $('Build CSV').item.json; } catch (e) { plan = $('Build CSV').first().json; }

const err = $json.error !== undefined ? $json.error : $json;
const parts = [];
const add = (value) => {
  if (value === undefined || value === null || value === '') return;
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (!parts.includes(text)) parts.push(text);
};
if (typeof err === 'string') {
  add(err);
} else {
  add(err.httpCode);
  add(err.message);
  add(err.description);
  add(err.cause && err.cause.message);
  add(err.context && err.context.data);
}
const detail = (parts.join(' | ') || 'penyebab tidak diketahui').replace(/\s+/g, ' ').slice(0, 1200);
return { json: { text: `Laporan ${String(plan.bu).toUpperCase()} ${plan.period} GAGAL dibuat: ${detail}` } };
