// Builds the model request. Only aggregate facts are sent: no company names, contacts or lead rows.
const SYSTEM_PROMPT = __SYSTEM_PROMPT__;
const PROMPT_VERSION = __PROMPT_VERSION__;
// One switch. 'openai' = any OpenAI-compatible endpoint (here the 9router combo); 'anthropic' = Anthropic Messages API.
// Change the URL to the router's internal Docker address (http://<container>:<port>/v1/chat/completions) when n8n can reach it.
const PROVIDER = 'openai';
const PROVIDERS = {
  openai: { url: 'https://9router.pesankopi.com/v1/chat/completions', model: 'pesankopi-report', headers: {} },
  anthropic: { url: 'https://api.anthropic.com/v1/messages', model: 'claude-sonnet-5-5', headers: { 'anthropic-version': '2023-06-01' } },
};
const MAX_TOKENS = 6000;

const provider = PROVIDERS[PROVIDER];
if (!provider) throw new Error(`PROVIDER harus salah satu dari: ${Object.keys(PROVIDERS).join(', ')}`);
const request = ref('Validate Request').first().json;
const run = $input.first().json;
if (!run.run_id) throw new Error(`Belum ada laporan numerik untuk ${request.bu} ${request.period}; jalankan Report Generate terlebih dahulu`);

// Reports made before the Next Action panel existed have no slot for it in their stored page; the analysis still answers it and the viewer shows it.
const analysisKeys = [...new Set([...(run.analysis_keys || []), 'next_action'])];
// Share of the Same-week (or Same-month) figures in the period total, computed here so the model never divides: percent with one decimal, null when the total is 0.
const facts = JSON.parse(JSON.stringify(run.facts));
const share = (window) => {
  const part = (facts.same_period || {})[window];
  const whole = (facts.funnel || {})[window];
  if (!part || !whole) return null;
  const percent = (a, b) => (b ? Math.round((1000 * a) / b) / 10 : null);
  return { MQL: percent(part.MQL, whole.MQL), SQL: percent(part.SQL, whole.SQL), 'SQL Value': percent(part['SQL Value'], whole['SQL Value']) };
};
facts.same_period_share_percent = { now: share('now'), prev: share('prev') };
const userInput = { company_key: request.bu, analysis_keys: analysisKeys, facts, actions: Array.isArray(request.actions) ? request.actions : [] };
if (request.targets) userInput.targets = request.targets;
if (request.budget) userInput.budget = request.budget;
const userText = JSON.stringify(userInput);
const body = PROVIDER === 'openai'
  ? { model: provider.model, max_tokens: MAX_TOKENS, messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: userText }] }
  : { model: provider.model, max_tokens: MAX_TOKENS, system: SYSTEM_PROMPT, messages: [{ role: 'user', content: userText }] };
return [{
  json: {
    run_id: run.run_id,
    model: provider.model,
    prompt_version: PROMPT_VERSION,
    url: provider.url,
    headers: provider.headers,
    request: body,
  },
}];
