// Builds the Anthropic Messages request. Only aggregate facts are sent: no company names, contacts or lead rows.
const SYSTEM_PROMPT = __SYSTEM_PROMPT__;
const PROMPT_VERSION = __PROMPT_VERSION__;
const ANTHROPIC_MODEL = '<ANTHROPIC_MODEL>'; // replace after import with a model ID from Anthropic's documentation
const MAX_TOKENS = 6000;

if (ANTHROPIC_MODEL.startsWith('<')) throw new Error('Isi ANTHROPIC_MODEL pada node ini dengan ID model dari dokumentasi Anthropic');
const request = $('Validate Request').first().json;
const run = $input.first().json;
if (!run.run_id) throw new Error(`Belum ada laporan numerik untuk ${request.bu} ${request.period}; jalankan Report Generate terlebih dahulu`);

const userText = JSON.stringify({ analysis_keys: run.analysis_keys, facts: run.facts });
return [{
  json: {
    run_id: run.run_id,
    model: ANTHROPIC_MODEL,
    prompt_version: PROMPT_VERSION,
    request: { model: ANTHROPIC_MODEL, max_tokens: MAX_TOKENS, system: SYSTEM_PROMPT, messages: [{ role: 'user', content: userText }] },
  },
}];
