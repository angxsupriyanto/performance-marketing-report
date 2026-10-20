// Runs the body of an n8n Code node with minimal stand-ins for $input, $json and $('Node').
// Usage: node n8n_harness.js < spec.json   where spec = {code, items, nodes, compileOnly}
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));
const items = (spec.items || []).map((json) => ({ json }));
const nodes = spec.nodes || {};
const lookup = (name) => {
  const node = nodes[name] || { items: [], executed: false };
  const list = (node.items || []).map((json) => ({ json }));
  return { all: () => list, first: () => list[0], last: () => list[list.length - 1], item: list[0], isExecuted: !!node.executed };
};
const fn = new Function('$input', '$json', '$', spec.code);
if (spec.compileOnly) { console.log(JSON.stringify({ ok: true })); process.exit(0); }
const $input = { all: () => items, first: () => items[0], last: () => items[items.length - 1], item: items[0] };
try {
  console.log(JSON.stringify({ ok: true, result: fn($input, items[0] ? items[0].json : undefined, lookup) }));
} catch (error) {
  console.log(JSON.stringify({ ok: false, error: String(error.message) }));
}
