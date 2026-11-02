"""Step 5. Qualify: fit (company size, seniority, role) plus intent (demo, pricing, pages, message).

Pattern from lead-qualification-agent and account-signal-scoring-agent. Every point is explained.
"""
import re


def has_word(text, words):
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def score_lead(lead, policy):
    s = policy["scoring"]
    parts = []
    emp = lead["employees"]
    if emp is not None:
        for low, high, pts in s["employee_bands"]:
            if low <= emp <= high:
                parts.append((f"{emp} employees", pts))
                break
    title = lead["title"].lower()
    if has_word(title, s["senior_title_words"]):
        parts.append(("senior title", s["senior_points"]))
    elif has_word(title, s["mid_title_words"]):
        parts.append(("manager or lead title", s["mid_points"]))
    elif title:
        parts.append(("other title", s["other_title_points"]))
    if any(w in title for w in s["ops_title_bonus_words"]):
        parts.append(("ops buyer", s["ops_title_bonus"]))
    if lead["domain"] in policy["free_email_domains"]:
        parts.append(("free email domain", -s["free_email_penalty"]))
    if lead["demo_requested"]:
        parts.append(("asked for a demo", s["demo_points"]))
    if "pricing" in lead["page_url"].lower() or lead["form"].lower() == "pricing":
        parts.append(("pricing page", s["pricing_page_points"]))
    if lead["pages_viewed"]:
        parts.append((f"{lead['pages_viewed']} pages viewed", min(lead["pages_viewed"], s["max_page_points"])))
    if len(lead["message"]) > 25:
        parts.append(("wrote a real message", s["message_points"]))
    score = max(0, min(100, sum(p for _, p in parts)))
    tier = "A" if score >= s["tier_a_at"] else "B" if score >= s["tier_b_at"] else "C"
    return score, tier, parts
