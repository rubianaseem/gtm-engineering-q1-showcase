-- Why are leads waiting for a human? Fix the top reason and the queue shrinks next time.
SELECT
  code          AS reason,
  COUNT(*)      AS leads,
  GROUP_CONCAT(email, '; ') AS examples
FROM lead_reasons
WHERE kind = 'blocking'
GROUP BY code
ORDER BY leads DESC, reason;
