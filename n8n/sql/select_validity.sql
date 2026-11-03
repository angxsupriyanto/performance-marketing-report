SELECT coalesce(jsonb_object_agg(bu, config), '{}'::jsonb) AS validity
FROM (
  SELECT DISTINCT ON (bu) bu, config
  FROM reports.lead_validity_settings
  ORDER BY bu, saved_at DESC
) latest
