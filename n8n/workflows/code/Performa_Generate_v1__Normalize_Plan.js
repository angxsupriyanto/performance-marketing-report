// Which companies to compute performance for. The sheet export is the only input; there is no period.
const BUS = ['bu1', 'bu2'];
const input = $input.first().json;
const source = Object.assign({}, input, input.body || {});
const requested = String(source.bu || 'all').toLowerCase();
if (requested !== 'all' && !BUS.includes(requested)) throw new Error(`bu harus salah satu dari: all, ${BUS.join(', ')}`);
const bus = requested === 'all' ? BUS : [requested];
return [{ json: { trigger: 'manual', plans: bus.map((bu) => ({ bu, period: '' })) } }];
