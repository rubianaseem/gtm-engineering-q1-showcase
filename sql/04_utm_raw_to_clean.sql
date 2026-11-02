-- Every raw UTM combination that fed one clean value. More than one raw row per clean row
-- means the campaign would have been split in your reports.
SELECT
  utm_source || ' / ' || utm_medium || ' / ' || utm_campaign AS clean_value,
  utm_source_raw || ' / ' || utm_medium_raw || ' / ' || utm_campaign_raw AS raw_value,
  COUNT(*) AS leads
FROM leads
WHERE outcome != 'quarantine'
GROUP BY clean_value, raw_value
ORDER BY clean_value, leads DESC;
