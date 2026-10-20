// Aggregate-only summary for Telegram and for the webhook response. No customer data.
const prepared = $('Prepare Insert').all();
const money = (n) => 'Rp ' + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
return $input.all().map((saved, i) => {
  const p = prepared[i].json;
  const row = saved.json;
  const m = p.metrics;
  const state = row.inserted ? 'tersimpan' : 'sudah ada (input identik, tidak ditulis ulang)';
  const lines = [
    `Laporan ${p.bu.toUpperCase()} ${p.period} ${state}`,
    `Submission ${m['Submission']} · MQL ${m['MQL']} · SQL ${m['SQL']} · SQL Value ${money(m['SQL Value'])} · Deal Won ${m['Deal Won']} (provisional)`,
    `Baris di BU: ${p.rows_in_bu} · tanpa BU (tidak dihitung): ${p.rows_without_bu}`,
    `Run: ${String(row.run_id).slice(0, 8)}`,
  ];
  return { json: { bu: p.bu, period: p.period, run_id: row.run_id, inserted: row.inserted, text: lines.join('\n') } };
});
