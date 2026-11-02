"""The whole run in one place. Each step is a small function from its own module, in the order it runs."""
import csv
import json
from collections import Counter
from pathlib import Path

from . import crm as crm_mod
from .handoff import write_brief
from .ingest import read_leads
from .lifecycle import decide_stage
from .llm import claude_summary
from .qualify import score_lead
from .report import build_db, run_reports
from .route import Router
from .triage import build_crowd_signals, triage
from .utm import normalise_utm

REVIEW_HELP = {
    "INVALID_EMAIL": "Email will bounce or is malformed. Check the form record before creating a contact.",
    "POSSIBLE_DUPLICATE": "Same domain and surname as an existing contact under a different email. Merge or confirm new person.",
    "CONSENT_CONFLICT": "CRM says unsubscribed but the form says opted in. Confirm consent wording before changing it.",
    "UNKNOWN_LIFECYCLE_VALUE": "The CRM stage is a custom value. Map it in policy.json or fix the record first.",
    "UNRESOLVED_OWNER": "Owner field matches no rep. Add the alias to policy.json or fix the owner.",
    "OWNER_DEPARTED": "Owner has left. Sales manager picks the new owner (see book-of-business-transfer-agent).",
    "NO_TERRITORY": "Country is outside every territory. Decide who covers it, then add it to policy.json.",
    "ALL_REPS_AT_CAP": "Every eligible rep is OOO or at today's cap. Assign by hand or raise a cap.",
    "SPAM_REVIEW": "Some spam signals, not enough to quarantine. Check before it enters workflows.",
}

IMPORT_COLUMNS = ["Action", "Record ID", "Email", "First Name", "Last Name", "Job Title", "Company Name", "Country",
                  "Phone Number", "Lifecycle Stage", "Lead Status", "Contact Owner", "Lead Tier", "Fit Intent Score",
                  "UTM Source", "UTM Medium", "UTM Campaign", "Marketing Consent", "Routing Notes"]


def process(lead, crm, router, policy, crowd):
    """Run one lead through every step. Mutates and returns the lead dict."""
    verdict, spam_score, spam_hits = triage(lead, policy, crowd)
    lead.update(verdict=verdict, spam_score=spam_score, spam_hits=spam_hits)
    utm, utm_flags = normalise_utm(lead["utm_source_raw"], lead["utm_medium_raw"], lead["utm_campaign_raw"], policy)
    lead.update(utm_source=utm["source"], utm_medium=utm["medium"], utm_campaign=utm["campaign"])
    lead["notes"] += utm_flags
    if verdict in ("likely_spam", "test_internal"):
        lead.update(outcome="quarantine", action="", route="quarantine", owner_email="", tier="", score="")
        lead["reasons"] += spam_hits
        return lead
    if verdict == "review":
        lead["reasons"].append("SPAM_REVIEW")
    if not lead["email_valid"]:
        lead["reasons"].append("INVALID_EMAIL")

    match = crm.match(lead)
    lead["match"] = match
    if match["possible_duplicate"]:
        lead["reasons"].append("POSSIBLE_DUPLICATE")
        lead["notes"].append(f"looks like {match['possible_duplicate']['email']}")
    contact = match["contact"]
    if contact and contact.get("email_consent") == "unsubscribed" and lead["consent"] == "opted_in":
        lead["reasons"].append("CONSENT_CONFLICT")
    if contact and contact.get("email_consent") == "unsubscribed":
        lead["consent"] = "opted_out"  # never silently re-subscribe

    lead["score"], lead["tier"], lead["score_parts"] = score_lead(lead, policy)
    proposed = policy["routing"]["lifecycle_by_tier"][lead["tier"]]
    stage, stage_note, stage_block = decide_stage(contact["lifecycle_stage"] if contact else "", proposed, policy)
    lead["lifecycle_write"] = stage
    if stage_note:
        lead["notes"].append(stage_note)
    if stage_block:
        lead["reasons"].append(stage_block)

    owner = None
    if not lead["reasons"]:  # only spend a rep's capacity on leads that can actually be imported
        owner, route, route_reasons, route_notes = router.route(lead, match, lead["tier"])
        lead["reasons"] += route_reasons
        lead["notes"] += route_notes
        lead["route"] = route
    else:
        lead["route"] = "review"
        lead["territory"] = ""
    lead["owner"] = owner
    lead["owner_email"] = owner["email"] if owner else ""
    lead["action"] = "UPDATE" if contact else "CREATE"
    lead["outcome"] = "review" if lead["reasons"] else "import"
    return lead


def import_row(lead):
    contact = lead["match"]["contact"]
    return {
        "Action": lead["action"], "Record ID": contact["contact_id"] if contact else "", "Email": lead["email"],
        "First Name": lead["first_name"], "Last Name": lead["last_name"], "Job Title": lead["title"],
        "Company Name": lead["company"], "Country": lead["country"], "Phone Number": lead["phone"],
        "Lifecycle Stage": lead["lifecycle_write"], "Lead Status": "NEW" if lead["owner_email"] and not contact else "",
        "Contact Owner": lead["owner_email"], "Lead Tier": lead["tier"], "Fit Intent Score": lead["score"],
        "UTM Source": lead["utm_source"], "UTM Medium": lead["utm_medium"], "UTM Campaign": lead["utm_campaign"],
        "Marketing Consent": lead["consent"], "Routing Notes": f"{lead['route']}; " + ", ".join(lead["notes"]),
    }


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def rules_summary(facts):
    o = facts["outcomes"]
    top = facts["top_review_reason"]
    s = (f"{facts['rows_in']} form rows came in and merged to {facts['unique_leads']} unique leads. "
         f"{o.get('import', 0)} are ready to import, {o.get('review', 0)} need a human and {o.get('quarantine', 0)} were quarantined as spam or test entries. ")
    if top:
        s += f"The most common review reason is {top[0]} ({top[1]} leads). "
    if facts["tier_a_without_owner"]:
        s += f"{facts['tier_a_without_owner']} tier A leads have no owner yet, so clear those first."
    return s.strip()


def run(paths, policy_path, out_dir, sql_dir, use_claude=True):
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    (out / "briefs").mkdir(parents=True, exist_ok=True)
    for old in (out / "briefs").glob("*.md"):
        old.unlink()  # briefs are regenerated every run

    rows_in, leads = read_leads(paths["leads"], policy)
    crm = crm_mod.CRM(paths["contacts"], paths["companies"], paths["reps"], policy)
    router = Router(crm, policy)
    crowd = build_crowd_signals(leads)
    for lead in leads:
        lead["route"] = ""
        lead["territory"] = ""
        process(lead, crm, router, policy, crowd)

    imports = [import_row(l) for l in leads if l["outcome"] == "import"]
    write_csv(out / "crm_import_contacts.csv", imports, IMPORT_COLUMNS)
    review = [{"email": l["email"], "company": l["company"], "tier": l["tier"], "reasons": ", ".join(l["reasons"]),
               "what_to_check": " | ".join(REVIEW_HELP.get(r, r) for r in l["reasons"]), "notes": ", ".join(l["notes"])}
              for l in leads if l["outcome"] == "review"]
    write_csv(out / "review_queue.csv", review, ["email", "company", "tier", "reasons", "what_to_check", "notes"])
    quarantine = [{"email": l["email"], "name": f"{l['first_name']} {l['last_name']}".strip(), "verdict": l["verdict"],
                   "spam_score": l["spam_score"], "signals": ", ".join(l["reasons"])} for l in leads if l["outcome"] == "quarantine"]
    write_csv(out / "quarantine.csv", quarantine, ["email", "name", "verdict", "spam_score", "signals"])

    briefs = []
    for l in leads:
        if l["outcome"] == "import" and l["owner"] and l["owner"]["role"] == "AE" and l["tier"] == "A":
            text, covered, gaps = write_brief(l, l["owner"], l["match"], policy)
            name = l["email"].split("@")[0].replace(".", "_") + ".md"
            (out / "briefs" / name).write_text(text, encoding="utf-8")
            briefs.append((l["email"], l["owner"]["name"], covered, gaps))

    con = build_db(leads, crm.reps, out / "run.db")
    reports = run_reports(con, sql_dir)
    (out / "reports").mkdir(exist_ok=True)
    for name, (cols, rows) in reports.items():
        with open(out / "reports" / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    con.close()

    reason_counts = Counter(r for l in leads if l["outcome"] == "review" for r in l["reasons"])
    facts = {
        "rows_in": rows_in, "unique_leads": len(leads),
        "outcomes": dict(Counter(l["outcome"] for l in leads)),
        "routes": dict(Counter(l["route"] for l in leads if l["outcome"] == "import")),
        "tiers": dict(Counter(l["tier"] for l in leads if l["tier"])),
        "review_reasons": dict(reason_counts),
        "top_review_reason": reason_counts.most_common(1)[0] if reason_counts else None,
        "tier_a_without_owner": len(reports["05_tier_a_not_routed"][1]),
        "utm_fixes": sum(1 for l in leads for n in l["notes"] if n.startswith("UTM_") and n.endswith("FIXED")),
        "briefs": len(briefs),
    }
    summary = (claude_summary(facts) if use_claude else None) or rules_summary(facts)
    mode = "Claude" if summary != rules_summary(facts) else "rules"
    (out / "run_brief.md").write_text(render_brief(facts, summary, mode, reports, briefs), encoding="utf-8")
    (out / "run_log.json").write_text(json.dumps(facts, indent=2, default=str), encoding="utf-8")
    return {"facts": facts, "leads": leads, "reports": reports, "briefs": briefs, "mode": mode, "reps": crm.reps}


def render_brief(facts, summary, mode, reports, briefs):
    lines = ["# Inbound batch run brief", "", f"Summary written by: {mode}.", "", summary, "", "## Review queue by reason"]
    for code, n in sorted(facts["review_reasons"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {code}: {n}. {REVIEW_HELP.get(code, '')}")
    lines += ["", "## Tier A leads with no owner yet"]
    rows = reports["05_tier_a_not_routed"][1]
    lines += [f"- {r[0]} ({r[1]}): {r[4] or r[3]}" for r in rows] or ["- none"]
    lines += ["", "## First-call briefs written"]
    lines += [f"- {e} -> {o}: {c} checklist items covered, {g} questions to ask" for e, o, c, g in briefs] or ["- none"]
    lines += ["", "## Before you import", "1. Clear the review queue with the owners named in each reason.",
              "2. Import five rows of crm_import_contacts.csv first and check them in the CRM.",
              "3. Import the rest. Blank Lifecycle Stage cells mean leave the current stage alone.",
              "4. Leave quarantine.csv out of every workflow. Nothing was deleted.", ""]
    return "\n".join(lines)
