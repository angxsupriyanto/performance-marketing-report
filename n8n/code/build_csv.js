// Turns the Tracker rows into one CSV per planned report. Only the columns the generator needs are kept, so PIC
// names, phone numbers, emails and CRM links never leave n8n. Dates arrive as Google Sheets serial numbers and are
// written as ISO dates, which removes any M/D versus D/M ambiguity.
const COLUMNS = __COLUMNS__;
const DATE_COLUMNS = new Set(__DATE_COLUMNS__);
const MONEY_COLUMNS = new Set(__MONEY_COLUMNS__);
const SERIAL_EPOCH = Date.UTC(1899, 11, 30);
const normalize = (name) => String(name).replace(/\s+/g, ' ').trim();

function cell(column, value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'number') {
    if (DATE_COLUMNS.has(column)) {
      // Serial 30000 is 1982 and 80000 is 2118. Anything else (for example 20260119 typed as a number) is left as
      // text so the generator reports it instead of turning it into a nonsense date.
      if (value < 30000 || value > 80000) return String(value);
      return new Date(SERIAL_EPOCH + Math.floor(value) * 86400000).toISOString().slice(0, 10);
    }
    if (MONEY_COLUMNS.has(column)) return String(Math.round(value * 100) / 100);
    return String(value);
  }
  return String(value).trim();
}

const quote = (text) => (/[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text);

// The Sheets API leaves out empty cells, so a column is judged missing only when NO row has it.
const squash = (name) => name.toLowerCase().replace(/[^a-z0-9]/g, '');
const seen = new Set();
const rows = [];
for (const item of $input.all()) {
  const byName = {};
  for (const [key, value] of Object.entries(item.json)) {
    const name = normalize(key);
    byName[name] = value;
    seen.add(name);
  }
  const values = COLUMNS.map((column) => cell(column, byName[column]));
  if (values.some((v) => v !== '')) rows.push(values.map(quote).join(','));
}
if (!rows.length) throw new Error('Sheet tidak mengembalikan baris data');

const missing = COLUMNS.filter((column) => !seen.has(column));
if (missing.length) {
  const hints = missing.map((column) => {
    const close = [...seen].filter((name) => squash(name) === squash(column));
    return close.length ? `${column} (header mirip: "${close[0]}")` : column;
  });
  throw new Error(`Kolom tidak ditemukan di satu baris pun (tidak ada di sheet atau kosong seluruhnya): ${hints.join('; ')}. Baris dibaca: ${rows.length}, header unik: ${seen.size}`);
}

const csv = [COLUMNS.map(quote).join(','), ...rows].join('\n') + '\n';
const plans = $('Normalize Plan').first().json.plans;
return plans.map((plan) => ({ json: { bu: plan.bu, period: plan.period, csv, rows: rows.length } }));
