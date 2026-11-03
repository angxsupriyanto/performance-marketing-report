// Tells the viewer that a company's run ended well, so its "Perbarui data" page can unlock. One result per saved item.
// Runs started from n8n's editor carry no job id and report nothing. The text is short and holds no data rows.
const jobId = ref('Normalize Plan').first().json.job_id || '';
if (!jobId) return [];
const prepared = ref('Prepare Insert').all();
const label = __LABEL__;
return $input.all().map((item, i) => {
  const p = prepared[i].json;
  const text = item.json.inserted === false ? `${label(p)} sudah ada dengan isi yang sama; tidak ada yang berubah` : `${label(p)} selesai`;
  return { json: { params: [jobId, p.bu, true, text] } };
});
