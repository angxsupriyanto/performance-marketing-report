// Builds the BU/period pairs to generate. The period is always given explicitly, either on the
// "Manual Parameters" node or in the webhook body. Nothing is guessed from the current date.
const BUS = ['bu1', 'bu2'];
const input = $input.first().json;
const source = Object.assign({}, input, input.body || {});

const requested = String(source.bu || 'all').toLowerCase();
if (requested !== 'all' && !BUS.includes(requested)) throw new Error(`bu harus salah satu dari: all, ${BUS.join(', ')}`);

const period = String(source.period || '').trim();
const match = /^(\d{4})-(?:W(\d{2})|(\d{2}))$/.exec(period);
if (!match) throw new Error('period wajib diisi dengan format YYYY-Www (mingguan) atau YYYY-MM (bulanan)');
if (match[2] !== undefined && (Number(match[2]) < 1 || Number(match[2]) > 53)) throw new Error('nomor minggu harus 01 sampai 53');
if (match[3] !== undefined && (Number(match[3]) < 1 || Number(match[3]) > 12)) throw new Error('nomor bulan harus 01 sampai 12');

const executed = (name) => {
  try { return $(name).isExecuted === true; } catch (e) { return false; }
};
const trigger = executed('Webhook Generate') ? 'webhook' : 'manual';
const bus = requested === 'all' ? BUS : [requested];
return [{ json: { trigger, plans: bus.map((bu) => ({ bu, period })) } }];
