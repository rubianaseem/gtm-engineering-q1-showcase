# Walk through it line by line

This is the key code, in the order it runs. Open each file next to this page. Every step is a small function, so you can read one without the others.

## 0. The order of the run: `showcase/pipeline.py`, `process()`

```python
verdict, spam_score, spam_hits = triage(lead, policy, crowd)
```
Spam first. There is no point matching or scoring a fake lead.

```python
utm, utm_flags = normalise_utm(...)
lead["notes"] += utm_flags
```
UTM fixes are notes, not reasons. A lead with a messy campaign name still gets routed.

```python
if verdict in ("likely_spam", "test_internal"):
    lead.update(outcome="quarantine", ...)
    return lead
```
Quarantined leads stop here. They are written to `quarantine.csv`, never deleted.

```python
match = crm.match(lead)
...
lead["score"], lead["tier"], lead["score_parts"] = score_lead(lead, policy)
stage, stage_note, stage_block = decide_stage(...)
```
Match, then score, then the lifecycle check. Each one can add a blocking reason to `lead["reasons"]`.

```python
if not lead["reasons"]:
    owner, route, route_reasons, route_notes = router.route(lead, match, lead["tier"])
```
The line that matters most. Routing only runs if nothing is blocking, so a rep's daily cap is never used up by a lead that is going to review anyway.

```python
lead["outcome"] = "review" if lead["reasons"] else "import"
```
One rule decides the split: any reason means a human looks first.

## 1. Merging duplicate submissions: `showcase/ingest.py`, `merge_duplicates()`

```python
for row in sorted(rows, key=lambda r: r["submitted_at"]):
```
Oldest first, so later submissions overwrite earlier ones.

```python
key = row["email"] or f"__blank_{len(order)}"
```
The email is the key. Rows with no email get a unique key so they are never merged together by accident.

```python
if value not in ("", None, 0, False):
    keep[field] = value
```
A later blank does not wipe an earlier value. Leon's second form had no message, so his first message survives.

```python
if CONSENT_RANK[row["consent"]] < CONSENT_RANK[keep["consent"]]:
    keep["consent"] = row["consent"]
```
Consent is the exception to "latest wins". `CONSENT_RANK` puts opted out at 0, unknown at 1 and opted in at 2, and the lowest wins. If someone says no once, the record says no.

## 2. Spam signals: `showcase/triage.py`, `triage()`

```python
if row["domain"] in policy["internal_domains"] or re.search(r"\btest\b", name) ...:
    return "test_internal", 100, ["TEST_OR_INTERNAL"]
```
Your own colleagues testing the form are not leads. Caught first, with their own label.

```python
if row["domain"] in policy["disposable_domains"]:
    hits.append("DISPOSABLE_EMAIL")
```
Each check adds a named signal. No single signal decides alone; the weights in `policy.json` do.

```python
if len(by_message.get(" ".join(msg.split()), ())) > 1:
    hits.append("SAME_MESSAGE_MANY_EMAILS")
```
`build_crowd_signals()` ran once over the whole batch and grouped emails by message. The same pitch from two addresses is a campaign, not two prospects.

```python
score = min(100, sum(w[h] for h in hits))
if score >= s["quarantine_at"]: return "likely_spam", ...
if score >= s["review_at"]: return "review", ...
```
Three buckets. The middle one exists so that a real lead with one odd signal is checked, not lost.

## 3. CRM match: `showcase/crm.py`, `match()`

```python
contact = self.contact_by_email.get(lead["email"])
```
Exact email first. That becomes an UPDATE with the Record ID.

```python
domain = lead["domain"] if lead["domain"] not in self.policy["free_email_domains"] else lead["website"]
```
A gmail address tells you nothing about the company, so use the website field instead.

```python
if company and company.get("parent_company_id") in self.companies:
    result["parent"] = self.companies[company["parent_company_id"]]
```
One level of hierarchy, from account-hierarchy-agent. The brief tells the owner to check the parent.

```python
same_domain = c["email"].split("@")[-1] == lead["domain"]
if same_domain and c["lastname"].lower() == lead["last_name"].lower():
    result["possible_duplicate"] = c
```
`rachel.cole@` and `r.cole@` at the same company are probably the same person. The pipeline does not guess; it sends her to review.

## 4. Lifecycle: `showcase/lifecycle.py`, `decide_stage()`

```python
if not known:
    return "", None, "UNKNOWN_LIFECYCLE_VALUE"
```
"Trial User" is not a stage in the list. Writing over it could break a workflow somebody built on it, so a human decides.

```python
if order.index(proposed) > order.index(current):
    return proposed, "LIFECYCLE_MOVED_FORWARD", None
return "", "LIFECYCLE_KEPT_NO_BACKWARD_MOVE", None
```
Only forward. Returning `""` means the import cell stays blank, and a blank cell in a HubSpot import leaves the field alone. That is how Maya stays a Customer even though a new form would normally make her an MQL.

## 5. Scoring: `showcase/qualify.py`, `score_lead()`

```python
if has_word(title, s["senior_title_words"]):
```
`has_word` uses `\b` word boundaries. Without them, "coo" would match "Coordinator" and give a junior title senior points. There is a test for exactly this.

```python
parts.append(("asked for a demo", s["demo_points"]))
```
Every score is a list of `(reason, points)`, so you can always say why a lead is tier A.

## 6. Routing: `showcase/route.py`

```python
for label, record in (("contact", match["contact"]), ("company", match["company"]), ("parent company", match["parent"])):
    if record and record.get("owner"):
```
Look for an existing owner in that order. The first non-blank owner field wins.

```python
if rep["status"] == "departed":
    return None, "manager_review", ["OWNER_DEPARTED"], ...
if rep["status"] == "ooo":
    fallback = self.round_robin(rep["role"], rep["territory"])
```
A departed owner is a manager decision (the book-of-business-transfer-agent pattern). An OOO owner is covered by the same role in the same territory, and the note says who was covering for whom.

```python
pool = [r for r in self.crm.reps
        if r["role"] == role and r["territory"] == territory and r["status"] == "active"
        and r["assigned_today"] + r["assigned_this_run"] < r["daily_cap"]]
rep = min(pool, key=lambda r: (r["assigned_today"] + r["assigned_this_run"], r["rep_id"]))
rep["assigned_this_run"] += 1
```
The round robin, load-balanced: of the reps who are active and under their cap, pick the one with the fewest leads today. Ties go to the lower rep ID so the result is the same every run. If the pool is empty, the lead goes to the RevOps queue with `ALL_REPS_AT_CAP`.

## 7. SQL: `sql/03_review_reasons.sql`

```sql
SELECT code AS reason, COUNT(*) AS leads, GROUP_CONCAT(email, '; ') AS examples
FROM lead_reasons
WHERE kind = 'blocking'
GROUP BY code
ORDER BY leads DESC, reason;
```
`report.py` writes one row per reason into `lead_reasons`, with `kind` set to blocking, note or spam_signal. Filtering on `blocking` keeps spam signals out of the review count. In the sample, `ALL_REPS_AT_CAP` tops the list, which tells you the fix is capacity, not data.

## 8. The audit: `portfolio_audit.py`, `audit_repo()`

```python
"where_each_step_runs": bool(re.search(r"^#+\s*Where each step runs", text, re.M | re.I)),
"test_functions": tests,
"emoji_free": not emoji_files,
```
Each check is one line that returns true or false. `tidy_list()` turns the failures into a to-do list, split into required and nice to have. It only reads files.

## Try it yourself

1. Set Sam's status to `active` in `sample_reps.csv` and run again. Nina should go to Sam.
2. Add `"FR"` to the DACH list under `territories` in `policy.json`. Carla should go to Tom and leave the review queue.
3. Raise Grace's `daily_cap` to 9. Three UKI leads should leave the review queue.
