// One entry per report, even when the chat summary was split into several messages.
const seen = new Set();
const runs = [];
for (const item of ref('Compose Message').all()) {
  const r = item.json;
  if (seen.has(r.run_id)) continue;
  seen.add(r.run_id);
  runs.push({ bu: r.bu, period: r.period, run_id: r.run_id, inserted: r.inserted });
}
return [{ json: { runs } }];
