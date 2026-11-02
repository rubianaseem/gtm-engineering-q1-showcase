"""Run the Q1 showcase pipeline: messy inbound leads in, CRM-ready files, review queue, briefs and SQL reports out.

Usage:
  python run_showcase.py
  python run_showcase.py --leads my_form_export.csv --contacts contacts.csv --companies companies.csv --reps reps.csv
"""
import argparse
import os
from pathlib import Path

from showcase.pipeline import run

HERE = Path(__file__).parent

STEPS = [
    ("1 Ingest", "event-lead-import-agent, inbound-lead-router-n8n-to-python"),
    ("2 Spam triage", "hubspot-form-spam-triage-agent"),
    ("3 CRM match", "event-lead-import-agent, account-hierarchy-agent"),
    ("4 UTM clean-up", "utm-governance-agent"),
    ("5 Qualify", "lead-qualification-agent, account-signal-scoring-agent"),
    ("6 Lifecycle check", "lifecycle-stage-audit-agent"),
    ("7 Route", "inbound-lead-router-n8n-to-python, book-of-business-transfer-agent"),
    ("8 Handoff briefs", "sdr-ae-handoff-brief-agent"),
    ("9 SQL reports", "gtm-sql-revops-queries"),
]


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(HERE / ".env")
    except ImportError:
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--leads", default=HERE / "sample_inbound_leads.csv")
    p.add_argument("--contacts", default=HERE / "sample_crm_contacts.csv")
    p.add_argument("--companies", default=HERE / "sample_crm_companies.csv")
    p.add_argument("--reps", default=HERE / "sample_reps.csv")
    p.add_argument("--policy", default=HERE / "policy.json")
    p.add_argument("--out", default=HERE / "out")
    p.add_argument("--no-claude", action="store_true", help="skip the optional Claude summary even if a key is set")
    a = p.parse_args()

    has_key = bool(os.getenv("ANTHROPIC_API_KEY", "").strip()) and not a.no_claude
    print(f"Q1 showcase pipeline. Mode: {'rules + Claude summary' if has_key else 'rules only (no API key)'}")
    print("Steps and the repo each pattern comes from:")
    for step, repo in STEPS:
        print(f"  {step:<18} {repo}")
    res = run({"leads": a.leads, "contacts": a.contacts, "companies": a.companies, "reps": a.reps},
              a.policy, a.out, HERE / "sql", use_claude=has_key)
    f = res["facts"]
    print(f"\nRows in: {f['rows_in']}. Unique leads after merge: {f['unique_leads']}.")
    print(f"{'lead':<32} {'tier':<4} {'score':>5}  {'outcome':<10} {'route / owner'}")
    for l in res["leads"]:
        who = l["owner"]["name"] if l.get("owner") else ", ".join(l["reasons"])[:46]
        print(f"  {l['email'][:30]:<30} {str(l['tier']):<4} {str(l['score']):>5}  {l['outcome']:<10} {l['route']}: {who}")
    o = f["outcomes"]
    print(f"\nReady to import: {o.get('import', 0)}. Review queue: {o.get('review', 0)}. Quarantined: {o.get('quarantine', 0)}.")
    print(f"UTM values fixed: {f['utm_fixes']}. First-call briefs: {f['briefs']}. Tier A leads with no owner: {f['tier_a_without_owner']}.")
    print("\nSQL report 03_review_reasons:")
    for row in res["reports"]["03_review_reasons"][1]:
        print(f"  {row[0]:<26} {row[1]}")
    print(f"\nOutputs written to {Path(a.out).name}/: crm_import_contacts.csv, review_queue.csv, quarantine.csv,")
    print("  briefs/, reports/ (5 SQL results), run.db, run_brief.md, run_log.json")


if __name__ == "__main__":
    main()
