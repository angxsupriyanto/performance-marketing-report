// The generator error is a short validation message (missing column, bad date, duplicate key). It never echoes a row.
const plan = $('Build CSV').item.json;
const raw = $json.error ? JSON.stringify($json.error) : JSON.stringify($json);
let message = raw;
try {
  const parsed = JSON.parse(raw);
  message = (parsed.error && (parsed.error.message || parsed.error)) || parsed.message || raw;
} catch (e) { /* keep raw */ }
return [{ json: { text: `Laporan ${plan.bu.toUpperCase()} ${plan.period} GAGAL dibuat: ${String(message).slice(0, 300)}` } }];
