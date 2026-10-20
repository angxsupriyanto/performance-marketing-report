// Decides which BU/period pairs to build. Scheduled runs build the previous completed ISO week or calendar
// month in Asia/Jakarta. Webhook runs must name the period explicitly; nothing is guessed.
const BUS = ['bu1', 'bu2'];
const PERIOD = /^\d{4}-(W\d{2}|\d{2})$/;
const pad = (n) => String(n).padStart(2, '0');

function jakartaToday(value) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(value);
  const get = (type) => Number(parts.find((p) => p.type === type).value);
  return new Date(Date.UTC(get('year'), get('month') - 1, get('day')));
}

function isoWeekLabel(date) {
  const thursday = new Date(date);
  thursday.setUTCDate(date.getUTCDate() + 3 - ((date.getUTCDay() + 6) % 7));
  const year = thursday.getUTCFullYear();
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const week = 1 + Math.round(((thursday - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${year}-W${pad(week)}`;
}

function previousWeek(today) {
  const d = new Date(today);
  d.setUTCDate(d.getUTCDate() - 7);
  return isoWeekLabel(d);
}

function previousMonth(today) {
  const y = today.getUTCFullYear();
  const m = today.getUTCMonth();
  return m === 0 ? `${y - 1}-12` : `${y}-${pad(m)}`;
}

const executed = (name) => {
  try { return $(name).isExecuted === true; } catch (e) { return false; }
};

const input = $input.first().json;
const today = jakartaToday(input.timestamp ? new Date(input.timestamp) : new Date());
let trigger;
let bus = BUS;
let period;

if (executed('Webhook Generate')) {
  trigger = 'webhook';
  const body = input.body || {};
  const requested = String(body.bu || 'all').toLowerCase();
  if (requested !== 'all' && !BUS.includes(requested)) throw new Error(`bu harus salah satu dari: all, ${BUS.join(', ')}`);
  if (!PERIOD.test(String(body.period || ''))) throw new Error('period wajib diisi dengan format YYYY-Www atau YYYY-MM');
  bus = requested === 'all' ? BUS : [requested];
  period = String(body.period);
} else if (executed('Schedule Monthly')) {
  trigger = 'monthly';
  period = previousMonth(today);
} else {
  trigger = executed('Schedule Weekly') ? 'weekly' : 'manual';
  period = previousWeek(today);
}

return [{ json: { trigger, plans: bus.map((bu) => ({ bu, period })) } }];
