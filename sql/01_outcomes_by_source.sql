-- Where did this batch come from, and how much of each source was usable?
-- Uses the cleaned UTM source, so 'Google Ads' and 'google' count as one row.
SELECT
  utm_source                                              AS source,
  COUNT(*)                                                AS leads,
  SUM(CASE WHEN outcome = 'import' THEN 1 ELSE 0 END)     AS ready_to_import,
  SUM(CASE WHEN outcome = 'review' THEN 1 ELSE 0 END)     AS needs_review,
  SUM(CASE WHEN outcome = 'quarantine' THEN 1 ELSE 0 END) AS quarantined,
  SUM(CASE WHEN tier = 'A' THEN 1 ELSE 0 END)             AS tier_a
FROM leads
GROUP BY utm_source
ORDER BY leads DESC, source;
