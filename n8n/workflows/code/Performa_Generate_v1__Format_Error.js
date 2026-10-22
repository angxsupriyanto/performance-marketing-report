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

// Runs once per failed item. Short, aggregate-only text: it reads only named fields of the error and caps the length, so no
// request body (the CSV) can leak into it.
let plan;
try { plan = ref('Build CSV').item.json; } catch (e) { plan = ref('Build CSV').first().json; }
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
return { json: { text: `Performa ${String(plan.bu).toUpperCase()} GAGAL dihitung: ${detail}` } };
