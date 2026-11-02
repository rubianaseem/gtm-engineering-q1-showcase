"""Step 8. Handoff: for every lead an AE now owns, write a first-call brief with what we know and what to ask.

Pattern from sdr-ae-handoff-brief-agent: score the handoff against a checklist and turn gaps into questions.
"""
import re

SIGNALS = {
    "why_now": r"\b(before|this month|renewal|next year|q[1-4]|planning|comparing)\b",
    "pain": r"\b(breaks|mess|broken|problem|struggl|slow|manual|fix)\w*",
    "stakeholders": r"\b(team|board|cfo|procurement|finanzteam)\b",
    "current_tools": r"\b(salesforce|hubspot|current vendor|we run|we use|other vendors)\b",
    "timeline": r"\b(january|december|this month|next year|q[1-4]|before)\b",
    "budget": r"\b(budget|pricing|price|seats|users)\b",
}


def checklist(lead, policy):
    text = lead["message"].lower()
    found, missing = [], []
    for key, question in policy["handoff_checklist"]:
        hit = re.search(SIGNALS[key], text)
        if key == "why_now" and lead["demo_requested"] and not hit:
            hit = True  # a demo request is a reason to talk now, even with no message
        (found if hit else missing).append((key, question))
    return found, missing


def write_brief(lead, owner, match, policy):
    found, missing = checklist(lead, policy)
    company = match["company"]
    lines = [
        f"# First-call brief: {lead['first_name']} {lead['last_name']}, {lead['company']}",
        "",
        f"Owner: {owner['name']} ({owner['email']}). Tier {lead['tier']}, score {lead['score']}. Route: {lead['route']}.",
        "",
        "## What we know",
        f"- {lead['title'] or 'Title not given'} at {lead['company']}, {lead['employees'] or 'unknown'} employees, {lead['country'] or 'country unknown'}.",
        f"- Came in through: {lead['form']} form, {lead['utm_source']} / {lead['utm_medium']} / {lead['utm_campaign']}.",
        f"- Pages viewed: {lead['pages_viewed']}. Demo requested: {'yes' if lead['demo_requested'] else 'no'}.",
        f"- Marketing consent: {lead['consent']}." + (" Do not add to marketing sequences." if lead["consent"] != "opted_in" else ""),
    ]
    if lead["merged_submissions"] > 1:
        lines.append(f"- Submitted {lead['merged_submissions']} forms in this batch; details above are from the latest.")
    if company:
        lines.append(f"- Already in the CRM as {company['name']} (stage: {company.get('lifecycle_stage') or 'blank'}).")
    if match["parent"]:
        lines.append(f"- Part of the {match['parent']['name']} family. Check the parent account before the call.")
    if lead["message"]:
        lines += ["", "## In their words", f"> {lead['message']}"]
    lines += ["", f"## Checklist: {len(found)} of {len(found) + len(missing)} covered by the form"]
    lines += [f"- covered: {key.replace('_', ' ')}" for key, _ in found]
    lines += ["", "## Ask on the first call"] + [f"- {q}" for _, q in missing]
    opener = (f"You mentioned \"{lead['message'][:90].rstrip()}\". Can you walk me through what that looks like today?"
              if lead["message"] else f"You asked for a demo after looking at {lead['pages_viewed']} pages. What prompted that this week?")
    lines += ["", "## Suggested opener", opener, ""]
    return "\n".join(lines), len(found), len(missing)
