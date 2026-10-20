// Chat summary after a report is saved. Totals are aggregates. The two lists name companies with their amounts;
// set INCLUDE_COMPANY_NAMES to false to send totals only. Long lists are split across messages (Telegram allows
// 4096 characters), never cut.
const INCLUDE_COMPANY_NAMES = true;
const MAX_CHARS = 3800;
const prepared = $('Prepare Insert').all();
const money = (n) => 'Rp ' + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const clean = (text) => String(text).replace(/\s+/g, ' ').trim().slice(0, 60);

function build(p, row) {
  const m = p.metrics;
  const state = row.inserted ? 'tersimpan' : 'sudah ada (input identik, tidak ditulis ulang)';
  const lines = [
    { text: `Laporan ${p.bu.toUpperCase()} ${p.period} ${state}` },
    { text: '' },
    { text: `Submission ${m['Submission']}` },
    { text: `MQL ${m['MQL']}` },
    { text: `SQL ${m['SQL']}` },
    { text: `SQL Value ${money(m['SQL Value'])}` },
    { text: `Deal Won ${m['Deal Won']}` },
    { text: `Deal Won Value ${money(m['Deal Won Value'])}` },
  ];
  if (INCLUDE_COMPANY_NAMES) {
    for (const [title, key] of [['List SQL + Value', 'SQL'], ['List Deal Won + Value', 'Deal Won']]) {
      const entries = (p.lists && p.lists[key]) || [];
      const heading = `${title} (${entries.length})`;
      const cont = `${title} (lanjutan, total ${entries.length})`;
      lines.push({ text: '' }, { text: heading, list: heading, cont, heading: true });
      if (!entries.length) lines.push({ text: '-', list: heading, cont });
      entries.forEach((e, i) => lines.push({ text: `${i + 1}. ${clean(e.company)} - ${money(e.value)}`, list: heading, cont }));
    }
  }
  lines.push({ text: '' }, { text: `Baris di BU: ${p.rows_in_bu} · tanpa BU (tidak dihitung): ${p.rows_without_bu} · Run: ${String(row.run_id).slice(0, 8)}` });
  return lines;
}

function pack(lines) {
  const chunks = [];
  let current = [];
  let size = 0;
  for (const line of lines) {
    if (line.text === '' && !current.length) continue;
    const extra = current.length === 0 && line.list && !line.heading ? [line.cont] : [];
    const add = extra.concat(line.text);
    const cost = add.join('\n').length + 1;
    if (current.length && size + cost > MAX_CHARS) {
      chunks.push(current.join('\n').trim());
      current = [];
      size = 0;
      const again = line.list && !line.heading ? [line.cont] : [];
      current.push(...again, line.text);
      size = current.join('\n').length + 1;
    } else {
      current.push(...add);
      size += cost;
    }
  }
  if (current.length) chunks.push(current.join('\n').trim());
  return chunks;
}

return $input.all().flatMap((saved, i) => {
  const p = prepared[i].json;
  const row = saved.json;
  const chunks = pack(build(p, row));
  return chunks.map((text, index) => ({ json: { bu: p.bu, period: p.period, run_id: row.run_id, inserted: row.inserted, part: index + 1, parts: chunks.length, text } }));
});
