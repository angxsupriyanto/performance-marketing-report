// One entry per company: whether a new snapshot was stored or the same export had already been stored today.
const prepared = $('Prepare Insert').all();
return [{ json: { snapshots: $input.all().map((item, i) => ({ bu: prepared[i].json.bu, as_of: prepared[i].json.as_of, days: prepared[i].json.days, snapshot_id: item.json.snapshot_id, inserted: item.json.inserted })) } }];
