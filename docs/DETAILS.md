# Details

## Cost note

With no API key the pipeline and the audit cost nothing to run. With a key, the pipeline makes one Claude call per run and sends only the counts in `run_log.json` (no names, emails or messages), so it is one short call (a few hundred words in and out) whatever the batch size. Check current pricing on Anthropic's site. `portfolio_audit.py --fetch` makes one anonymous GitHub API call per repo.

## Stack-swap table

| Piece | In this repo | Swap for |
|---|---|---|
| Lead source | Form export CSV | HubSpot Forms API, Typeform, Webflow, a webhook queue |
| CRM | HubSpot-shaped CSVs | Salesforce Leads and Contacts, Dynamics, Pipedrive |
| Rep roster | `sample_reps.csv` | A territory tool, a sheet the sales manager owns, the CRM user list |
| Rules | `policy.json` | A dbt seed, a config table in the warehouse |
| Reports | SQLite + `sql/` | BigQuery, Snowflake or Postgres with the same SQL |
| LLM | Claude via Anthropic | Any model that returns text |
| Delivery | CSV import | HubSpot import API, Salesforce Data Loader, an n8n flow calling the batch upsert API |

## Customise for your stack

Everything opinionated lives in `policy.json`:

- `internal_domains`, `free_email_domains`, `disposable_domains`: your own domain, and the lists that drive spam and scoring.
- `spam.weights`, `quarantine_at`, `review_at`: how much each signal counts and where the buckets split.
- `country_aliases`, `territories`: every spelling you see, mapped to one country code, and which codes each territory covers.
- `owner_aliases`: names and initials found in owner fields, mapped to a rep email.
- `utm`: approved sources and mediums with their typed variants, internal sources, and the campaign naming rule.
- `lifecycle_order`, `lifecycle_aliases`: the stages in order. Anything not listed is treated as a custom value and goes to review.
- `scoring`: points for size, seniority, ops titles, demo, pricing page, pages viewed and a real message, and the tier cut-offs.
- `routing.tier_role`: tier A goes to an AE, tier B to an SDR, tier C to nurture.
- `handoff_checklist`: the six questions the brief checks for.

To add a new reason for review, append the code to `lead["reasons"]` in `showcase/pipeline.py` and add a line to `REVIEW_HELP`. To add a SQL report, drop a new `.sql` file in `sql/`; the runner picks it up.

## Design choices

- **Nothing spends a rep's capacity on a lead that is going to review.** Routing only runs once every blocking check has passed.
- **Existing owners win over round robin**, contact first, then company, then parent company. A departed owner sends the lead to a manager. An OOO owner falls back to the same role in the same territory.
- **Consent only gets stricter.** Duplicate submissions keep the most restrictive answer, blank never counts as opted in, and an unsubscribed contact who opts back in goes to review.
- **Lifecycle only moves forward.** The import leaves the cell blank when the CRM stage is already further on.
- **UTM fixes are notes, not blockers.** A bad UTM should not stop a lead being routed.

## How this runs today (and what production would add)

Today it is a script you run on an export. It reads four CSVs, decides, and writes files. It never writes to the CRM, never sends a message and never changes a rep's real caps.

Production would add:

- A trigger: a form webhook or an hourly pull from the HubSpot Forms API, with the same steps in an n8n flow or a small service (see inbound-lead-router-n8n-to-python).
- Live reads of contacts, companies and rep status from the CRM and the calendar, instead of exports.
- A guarded upsert for the import rows only, with a dry-run diff and a run log, and the review queue as a Slack message or a HubSpot task per owner.
- Alerts for tier A leads with no owner after 15 minutes.
- A weekly check of the SQL reports: are the same review reasons coming back, and which policy change would remove them.
