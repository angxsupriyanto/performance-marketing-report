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

const prepared = ref('Prepare Analysis Request').first().json;
const request = ref('Validate Request').first().json;
const applied = $input.first().json;
if (typeof applied.html !== 'string' || !applied.html) throw new Error('Layanan laporan tidak mengembalikan HTML');
const parsed = ref('Parse Analysis').first().json;
const analysis = parsed.analysis;
const model = parsed.model || prepared.model;
return [{
  json: {
    params: [prepared.run_id, request.requested_by, model, prepared.prompt_version, JSON.stringify(analysis), applied.html],
    bu: request.bu,
    period: request.period,
  },
}];
