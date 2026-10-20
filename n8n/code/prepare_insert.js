// Maps each generator response onto the parameters of sql/insert_run.sql.
return $input.all().map((item) => {
  const r = item.json;
  const table = r.audit.inputs.table;
  const params = [
    r.bu, r.period, r.period_kind, r.period_start, r.period_end, r.source_sha256, r.generator_version,
    table.rows_total, table.rows_in_bu, table.rows_without_bu,
    JSON.stringify(r.audit.metrics), JSON.stringify(r.audit), JSON.stringify(r.facts), JSON.stringify(r.analysis_keys),
    r.html,
  ];
  return { json: { params, lists: r.lists || { SQL: [], 'Deal Won': [] }, bu: r.bu, period: r.period, metrics: r.audit.metrics.now, rows_without_bu: table.rows_without_bu, rows_in_bu: table.rows_in_bu } };
});
