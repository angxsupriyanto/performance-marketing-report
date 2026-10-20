SELECT html, has_analysis
FROM reports.latest_reports
WHERE bu = $1 AND period = $2
