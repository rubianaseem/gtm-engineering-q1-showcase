# Setup

## 1. Install

You need Python 3.10 or newer. Check with `python3 --version`.

```bash
git clone https://github.com/rubianaseem/gtm-engineering-q1-showcase.git
cd gtm-engineering-q1-showcase
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The pipeline and the audit only use the standard library. `requirements.txt` adds two optional packages: `anthropic` for the Claude summary and `python-dotenv` to read `.env`.

## 2. Sample run

```bash
python run_showcase.py
python -m unittest discover tests
```

`out/` now holds:

| File | What it is |
|---|---|
| `crm_import_contacts.csv` | Leads ready to import. `Action` is CREATE or UPDATE, `Record ID` is set for updates. A blank Lifecycle Stage means leave the current value alone. |
| `review_queue.csv` | Leads a human must decide on, with the reason and what to check. |
| `quarantine.csv` | Spam and test entries with the signals that caught them. Keep them out of workflows. |
| `briefs/*.md` | A first-call brief for each tier A lead now owned by an AE. |
| `reports/*.csv` | The five SQL results. The queries are in `sql/`. |
| `run.db` | The run as a SQLite database, so you can write your own queries. |
| `run_brief.md`, `run_log.json` | The summary for the managers and the raw counts. |

Explore the database: `sqlite3 out/run.db "SELECT route, COUNT(*) FROM leads GROUP BY route;"`

## 3. Optional: Claude for the summary

```bash
cp .env.example .env
# open .env and paste your key after ANTHROPIC_API_KEY=
python run_showcase.py
```

Claude only sees the counts in `run_log.json`, never the lead rows, and only writes the summary paragraph in `run_brief.md`. Every decision stays in the rules. Run with `--no-claude` to skip it even when a key is set. If the call fails, the run carries on with the rules summary.

## 4. Use your own data

Export four CSVs and pass them in:

```bash
python run_showcase.py --leads form_export.csv --contacts contacts.csv --companies companies.csv --reps reps.csv --out out_real
```

- **Leads:** a HubSpot form submissions export, a Typeform or Webflow export, or a webhook log. Header names can vary; `HEADER_ALIASES` in `showcase/ingest.py` maps the common ones. Add yours there.
- **Contacts:** in HubSpot, a contacts view with Record ID, Email, First Name, Last Name, Associated Company ID, Lifecycle Stage, Contact owner, a has-open-deal flag and email subscription status. In Salesforce, a Contacts and Leads report with the same fields. Rename the headers to match `sample_crm_contacts.csv`.
- **Companies:** company ID, name, domain, parent company ID, owner, lifecycle stage, employees.
- **Reps:** one row per rep with role (AE or SDR), territory, status (active, ooo, departed), daily cap and leads already assigned today. Most teams keep this in a sheet the sales manager owns.

Then edit `policy.json`: your own domains, territories, country spellings, owner aliases, UTM taxonomy and scoring weights. Run on a copy first and read the review queue before you import anything.

## 5. Audit your own portfolio

```bash
python portfolio_audit.py                # offline, from portfolio/snapshot.json
python portfolio_audit.py --fetch        # clone the public repos to a temp folder and re-audit
python portfolio_audit.py --clones ~/code # audit clones you already have
cp out/PORTFOLIO_MAP.md docs/PORTFOLIO_MAP.md
```

To audit your own repos, change `owner` and the `repos` list in `portfolio/portfolio.json`. The audit only reads; it never pushes or edits.

## 6. Extend it with an AI coding tool

Open the folder in Cursor, Claude Code, Codex CLI or Grok and ask for one change at a time. Prompts that work well:

- "Add a step between qualify and route that enriches company size from a CSV lookup when employees is blank. Add a test."
- "Add a Salesforce Lead import file next to the HubSpot one, with Salesforce field names."
- "Add a sixth SQL report: leads per form per territory. Put it in sql/06_*.sql and add a test."
- "Read docs/WALKTHROUGH.md and explain the round robin to me with a new example."

Ask it to run `python -m unittest discover tests` after each change.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: showcase` | Run commands from the repo folder, not from inside `showcase/`. |
| Every lead lands in review with `NO_TERRITORY` | Your country spellings are not in `country_aliases` in `policy.json`. |
| Every lead lands in review with `ALL_REPS_AT_CAP` | `assigned_today` or `daily_cap` in the reps file is wrong. |
| Real leads quarantined | Check the `signals` column, then lower a weight in `policy.json` or turn off `require_page_url` if your forms do not record a page URL. |
| `Claude step skipped` | The key is wrong, the package is missing or the network is down. The run still finishes on rules. |
| `portfolio_audit.py --fetch` fails | Check `git` is installed and you are online. Set `GITHUB_TOKEN` in `.env` if GitHub rate-limits you. |
