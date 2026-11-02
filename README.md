# GTM Engineering Q1 Showcase

One inbound lead pipeline that runs the patterns from eleven of my GTM repos end to end on the same messy data, plus an audit that maps all seventeen repos to the skill each one shows.

Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

## The pain point

A list of repos does not tell a hiring manager much. They want to know if the pieces work together, if they hold up on messy data, and if I can explain the decisions in plain English. Seventeen separate repos answer that badly. One pipeline that chains them, with tests, answers it well.

> "The market has shifted from 'can you use Clay' (most candidates can) to 'can you build something that actually runs unattended and doesn't break.'"
> [r/gtmengineering: "Best way to get a Job?"](https://www.reddit.com/r/gtmengineering/comments/1sfwo00/best_way_to_get_a_job/)

> "They’ve actually built things, not just talked about them" and "Thinks in workflows and systems, not shiny tools"
> [r/gtmengineering: "We're hiring a GTM engineer. Any advice on what to look out for?"](https://www.reddit.com/r/gtmengineering/comments/1qeqhdq/were_hiring_a_gtm_engineer_any_advice_on_what_to/)

## What it does

- Takes one messy inbound form export (27 rows: odd headers, ALL CAPS names, duplicate submissions, spam, a test entry, bad UTMs) plus a CRM contact, company and rep export.
- Runs nine steps in order, each from a repo I shipped: ingest, spam triage, CRM match, UTM clean-up, qualify, lifecycle check, route, handoff briefs, SQL reports. [docs/PORTFOLIO_MAP.md](docs/PORTFOLIO_MAP.md) shows which repo each step comes from.
- Handles the edge cases that break real routing: a departed owner, an OOO owner, reps at their daily cap, countries with no territory, an unsubscribed contact who opts back in, a custom lifecycle value and a possible duplicate.
- Splits every lead three ways: a CRM-ready import file, a review queue with the reason and what to check, and a quarantine file. Nothing is deleted.
- Loads the run into SQLite and answers five RevOps questions in plain SQL files you can read and change.
- `portfolio_audit.py` checks every repo for a short README, tests, sample data and setup docs, and writes a tidy list.

## Where each step runs

1. **GitHub** holds the code. You copy it to your laptop with `git clone`.
2. **Your CRM and form tool** are where you export the four input files. [SETUP.md](SETUP.md) lists the columns.
3. **Terminal** (Mac Terminal or the terminal inside Cursor) runs `python run_showcase.py`. It reads the CSVs and writes everything to `out/`.
4. **Claude is optional.** With no key, built-in rules write the run summary. With a key in `.env`, Claude writes it from the counts only. It still runs in the terminal.
5. **Back in the CRM**, you clear the review queue, import five rows of `out/crm_import_contacts.csv`, check them, then import the rest. The pipeline never writes to your CRM itself.

## Quick start

```bash
git clone https://github.com/rubianaseem/gtm-engineering-q1-showcase.git
cd gtm-engineering-q1-showcase
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_showcase.py
python portfolio_audit.py
python -m unittest discover tests
```

## Example output

```
Rows in: 27. Unique leads after merge: 26.
  leon.fischer@brightwave.de     A       82  import     account_owner: Tom Becker
  o.brien@brightwave.co.uk       B       66  review     manager_review: OWNER_DEPARTED
  nina.shah@medcore.health       A       76  import     ooo_fallback: Priya Shah
  carla.mendes@novapay.fr        A       83  review     revops_queue: NO_TERRITORY
  contact@rankfast.biz                       quarantine quarantine: PITCH_MESSAGE_WITH_LINK, ...
Ready to import: 10. Review queue: 11. Quarantined: 5.
UTM values fixed: 10. First-call briefs: 5. Tier A leads with no owner: 3.
```

Leon filled in two forms. The second one said no to marketing, so the merged record keeps the no. His company is a German subsidiary that Tom already owns, so Tom keeps him, and the brief tells Tom to check the parent account first. Owen's owner has left, so he goes to a manager, not the next rep in line. That matters because he has an open deal.

## More

- [SETUP.md](SETUP.md): install, sample run, API key, using your own exports, extending with Cursor, Claude Code, Codex CLI or Grok, and troubleshooting.
- [docs/DETAILS.md](docs/DETAILS.md): cost note, stack-swap table, customising `policy.json`, and how this runs today versus what production would add.
- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md): walk through the key code line by line.
- [docs/PORTFOLIO_MAP.md](docs/PORTFOLIO_MAP.md): every repo, the skill it shows, its patterns and the tidy check.
