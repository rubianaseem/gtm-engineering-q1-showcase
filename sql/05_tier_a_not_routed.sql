-- Speed-to-lead risk: tier A leads that do not yet have an owner. These are the ones to clear first.
SELECT
  l.email,
  l.company,
  l.territory,
  l.route,
  (SELECT GROUP_CONCAT(code, ', ') FROM lead_reasons r WHERE r.email = l.email AND r.kind = 'blocking') AS reasons,
  l.submitted_at
FROM leads l
WHERE l.tier = 'A' AND (l.owner_email = '' OR l.outcome != 'import')
ORDER BY l.submitted_at;
