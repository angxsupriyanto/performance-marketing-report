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

// Tells the viewer that a company's run ended well, so its "Perbarui data" page can unlock. One result per saved item.
// Runs started from n8n's editor carry no job id and report nothing. The text is short and holds no data rows.
const jobId = ref('Normalize Plan').first().json.job_id || '';
if (!jobId) return [];
const prepared = ref('Prepare Insert').all();
const label = (p) => 'Data Performa';
return $input.all().map((item, i) => {
  const p = prepared[i].json;
  const text = item.json.inserted === false ? `${label(p)} sudah ada dengan isi yang sama; tidak ada yang berubah` : `${label(p)} selesai`;
  return { json: { params: [jobId, p.bu, true, text] } };
});
