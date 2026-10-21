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
