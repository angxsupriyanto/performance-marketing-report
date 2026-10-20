// Accepts only a JSON object of plain-text strings whose keys the report actually has.
const MAX_TEXT_CHARS = 4000;
const response = $input.first().json;
if (response.stop_reason === 'max_tokens') throw new Error('Jawaban model terpotong (max_tokens); naikkan MAX_TOKENS atau ringkas permintaan');
const text = (response.content || []).filter((part) => part.type === 'text').map((part) => part.text).join('').trim();
const start = text.indexOf('{');
const end = text.lastIndexOf('}');
if (start < 0 || end <= start) throw new Error('Jawaban model bukan objek JSON');

let analysis;
try { analysis = JSON.parse(text.slice(start, end + 1)); } catch (e) { throw new Error('Jawaban model bukan JSON yang valid'); }
if (analysis === null || typeof analysis !== 'object' || Array.isArray(analysis)) throw new Error('Jawaban model harus berupa objek JSON');

const allowed = new Set($('Load Latest Run').first().json.analysis_keys);
const clean = {};
for (const key of allowed) clean[key] = '';
for (const [key, value] of Object.entries(analysis)) {
  if (!allowed.has(key)) throw new Error(`Kunci tidak dikenal dari model: ${key}`);
  if (typeof value !== 'string') throw new Error(`${key} harus berupa teks`);
  if (value.length > MAX_TEXT_CHARS) throw new Error(`${key} melebihi ${MAX_TEXT_CHARS} karakter`);
  clean[key] = value.trim();
}
return [{ json: { analysis: clean } }];
