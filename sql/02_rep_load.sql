-- Who got new leads this run, and how much room is left under each rep's daily cap?
SELECT
  name,
  role,
  territory,
  status,
  assigned_today                         AS before_run,
  assigned_this_run                      AS this_run,
  daily_cap,
  MAX(daily_cap - assigned_today - assigned_this_run, 0) AS room_left
FROM reps
ORDER BY territory, role, name;
