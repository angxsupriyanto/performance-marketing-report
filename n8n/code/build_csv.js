// Turns the Tracker rows into one CSV per planned report. Only the columns the generator needs are kept, so PIC
// names, phone numbers, emails and CRM links never leave n8n. Dates arrive as Google Sheets serial numbers and are
// written as ISO dates, which removes any M/D versus D/M ambiguity.
const COLUMNS = __COLUMNS__;
// Filter columns for the Performa page (Medium, Category Campaign). Copied when the sheet has them; a sheet without them still works.
const OPTIONAL_COLUMNS = __OPTIONAL_COLUMNS__;
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
const items = $input.all();
for (const item of items) {  // first pass: which columns exist in at least one row
  for (const key of Object.keys(item.json)) seen.add(normalize(key));
}
const ALL = COLUMNS.concat(OPTIONAL_COLUMNS.filter((column) => seen.has(column)));
for (const item of items) {
  const byName = {};
  for (const [key, value] of Object.entries(item.json)) {
    const name = normalize(key);
    byName[name] = value;
    seen.add(name);
  }
  const values = ALL.map((column) => cell(column, byName[column]));
  if (values.slice(0, COLUMNS.length).some((v) => v !== '')) rows.push(values.map(quote).join(','));
}
if (!items.length) throw new Error('Node Read Tracker tidak mengembalikan satu baris pun. Periksa ID spreadsheet, nama tab (NEW Customers List), rentang A:DR, dan credential Google Sheets pada node itu.');
if (!rows.length) {
  const sample = [...seen].slice(0, 12).join(', ') || '(tidak ada)';
  throw new Error(`Node Read Tracker mengembalikan ${items.length} baris, tetapi tidak ada baris yang berisi kolom wajib. Header yang terbaca (maks. 12): ${sample}. Biasanya nama tab atau rentang salah, atau baris judul tidak ada di baris pertama rentang.`);
}

const missing = COLUMNS.filter((column) => !seen.has(column));
if (missing.length) {
  const hints = missing.map((column) => {
    const close = [...seen].filter((name) => squash(name) === squash(column));
    return close.length ? `${column} (header mirip: "${close[0]}")` : column;
  });
  throw new Error(`Kolom tidak ditemukan di satu baris pun (tidak ada di sheet atau kosong seluruhnya): ${hints.join('; ')}. Baris dibaca: ${rows.length}, header unik: ${seen.size}`);
}

const csv = [ALL.map(quote).join(','), ...rows].join('\n') + '\n';
const plans = $('Normalize Plan').first().json.plans;
return plans.map((plan) => ({ json: { bu: plan.bu, period: plan.period, csv, rows: rows.length } }));
