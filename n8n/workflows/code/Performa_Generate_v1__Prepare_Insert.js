// Maps each service response onto the parameters of sql/insert_performance.sql. Only aggregates travel from here on.
return $input.all().map((item) => {
  const r = item.json;
  return { json: { params: [r.bu, r.as_of, r.source_sha256, r.generator_version, JSON.stringify(r.data)], bu: r.bu, as_of: r.as_of, days: r.days, rows_in_bu: r.rows_in_bu } };
});
