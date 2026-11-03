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

// Accepts only a JSON object of plain-text strings whose keys the report actually has.
const MAX_TEXT_CHARS = 4000;
const response = $input.first().json;
let text;
if (Array.isArray(response.choices)) { // OpenAI-compatible
  const choice = response.choices[0] || {};
  if (choice.finish_reason === 'length') throw new Error('Jawaban model terpotong (max_tokens); naikkan MAX_TOKENS atau ringkas permintaan');
  const content = choice.message && choice.message.content;
  text = (Array.isArray(content) ? content.map((part) => (typeof part === 'string' ? part : part.text || '')).join('') : content || '').trim();
  if (!text) throw new Error('Jawaban model kosong; periksa nama model atau combo di router');
} else { // Anthropic Messages
  if (response.stop_reason === 'max_tokens') throw new Error('Jawaban model terpotong (max_tokens); naikkan MAX_TOKENS atau ringkas permintaan');
  text = (response.content || []).filter((part) => part.type === 'text').map((part) => part.text).join('').trim();
}
const start = text.indexOf('{');
const end = text.lastIndexOf('}');
if (start < 0 || end <= start) throw new Error('Jawaban model bukan objek JSON');

let analysis;
try { analysis = JSON.parse(text.slice(start, end + 1)); } catch (e) { throw new Error('Jawaban model bukan JSON yang valid'); }
if (analysis === null || typeof analysis !== 'object' || Array.isArray(analysis)) throw new Error('Jawaban model harus berupa objek JSON');

const allowed = new Set([...ref('Load Latest Run').first().json.analysis_keys, 'next_action']); // the stored page of an older report has no slot for it; the analysis keeps it anyway
const clean = {};
for (const key of allowed) clean[key] = '';
for (const [key, value] of Object.entries(analysis)) {
  if (!allowed.has(key)) throw new Error(`Kunci tidak dikenal dari model: ${key}`);
  if (typeof value !== 'string') throw new Error(`${key} harus berupa teks`);
  if (value.length > MAX_TEXT_CHARS) throw new Error(`${key} melebihi ${MAX_TEXT_CHARS} karakter`);
  clean[key] = value.trim();
}
// The model that actually answered. A router combo (e.g. pesankopi-report) reports the model it picked in `model`;
// only when the response carries none do we fall back to the name that was requested.
const answered = typeof response.model === 'string' ? response.model.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 120) : '';
return [{ json: { analysis: clean, model: answered } }];
