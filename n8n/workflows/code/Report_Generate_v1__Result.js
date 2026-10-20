return [{ json: { runs: $input.all().map((i) => ({ bu: i.json.bu, period: i.json.period, run_id: i.json.run_id, inserted: i.json.inserted })) } }];
