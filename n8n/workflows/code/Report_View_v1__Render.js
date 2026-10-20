const row = $input.first().json;
const request = $('Validate Request').first().json;
if (!row.html) {
  return [{ json: { status: 404, html: `<!doctype html><meta charset="utf-8"><title>Tidak ada laporan</title><p>Belum ada laporan untuk ${request.bu.toUpperCase()} ${request.period}.</p>` } }];
}
return [{ json: { status: 200, html: row.html } }];
