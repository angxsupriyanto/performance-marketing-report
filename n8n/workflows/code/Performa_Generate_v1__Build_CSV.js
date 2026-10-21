// Reads another node of this workflow. When that node is missing or was renamed, say which name the code is looking for: n8n's own
// message ("Referenced node doesn't exist") does not name it. Importing a workflow into one that already has nodes of the same name
// makes n8n add a number to the new names (for example "Build CSV1"); rename them back.
const ref = (name) => {
  const guard = (action) => {
    try {
      return action($(name));
    } catch (e) {
      throw new Error(`Node "${name}" tidak ditemukan atau belum dijalankan di workflow ini (${e.message}). Nama node harus persis "${name}". Bila workflow ini diimpor ke workflow yang sudah punya node bernama sama, n8n menambah angka di belakang nama (mis. "${name}1"): ganti kembali nama node itu.`);
    }
  };
  return {
    all: () => guard((n) => n.all()),
    first: () => guard((n) => n.first()),
    last: () => guard((n) => n.last()),
    get item() { return guard((n) => n.item); },
  };
};

// Turns the Tracker rows into one CSV per planned report. Only the columns the generator needs are kept, so PIC
// names, phone numbers, emails and CRM links never leave n8n. Dates arrive as Google Sheets serial numbers and are
// written as ISO dates, which removes any M/D versus D/M ambiguity.
const COLUMNS = ["Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Remark", "Inbound Date", "MQL Date", "Proposal Price Quote Date", "ARR + OTF (Tanpa PPN)", "Deal Won Date", "Total Contract Deal Won", "BU", "Record Key", "SQL Date", "Total Contract SQL"];
// Filter columns for the Performa page (Medium, Category Campaign). Copied when the sheet has them; a sheet without them still works.
const OPTIONAL_COLUMNS = ["Medium", "Category Campaign"];
const DATE_COLUMNS = new Set(["Inbound Date", "MQL Date", "Proposal Price Quote Date", "Deal Won Date", "SQL Date"]);
const MONEY_COLUMNS = new Set(["ARR + OTF (Tanpa PPN)", "Total Contract Deal Won", "Total Contract SQL"]);
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
if (items.length && items[0].json && items[0].json.plans !== undefined) {
  throw new Error('Build CSV menerima keluaran node Normalize Plan, bukan baris sheet. Node Read Tracker sedang dinonaktifkan (disabled, tampil abu-abu atau dicoret) atau sambungannya terputus. Aktifkan node itu dan pastikan urutannya Normalize Plan, Read Tracker, Build CSV.');
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
const plans = ref('Normalize Plan').first().json.plans;
return plans.map((plan) => ({ json: { bu: plan.bu, period: plan.period, csv, rows: rows.length } }));
