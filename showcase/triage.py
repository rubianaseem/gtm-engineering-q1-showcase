"""Step 2. Spam and test triage: score small signals, quarantine the fakes, never delete.

Pattern from hubspot-form-spam-triage-agent. Every verdict carries its reasons.
"""
import re
from collections import defaultdict

VOWELS = set("aeiouy")


def looks_mashed(text):
    """Keyboard-mash names: a 4+ letter word with no vowels, or a known row like 'asdf' / 'qwer'."""
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        if len(word) >= 4 and not (set(word) & VOWELS):
            return True
        if any(row in word for row in ("asdf", "qwer", "zxcv", "hjkl")):
            return True
    return False


def random_localpart(email):
    local = email.split("@")[0]
    return len(local) >= 6 and not re.search(r"[._-]", local) and len(re.findall(r"\d", local)) >= 3


def fake_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return False
    return len(set(digits)) == 1 or digits in "12345678901234567890" or len(digits) < 7


def build_crowd_signals(rows):
    """Coordinated spam: the same message or phone used by different emails."""
    by_message, by_phone = defaultdict(set), defaultdict(set)
    for r in rows:
        msg = " ".join(r["message"].lower().split())
        if len(msg) > 20:
            by_message[msg].add(r["email"])
        if r["phone"]:
            by_phone[r["phone"]].add(r["email"])
    return by_message, by_phone


def triage(row, policy, crowd):
    by_message, by_phone = crowd
    s = policy["spam"]
    w = s["weights"]
    name = f"{row['first_name']} {row['last_name']}".lower()
    if row["domain"] in policy["internal_domains"] or re.search(r"\btest\b", name) or row["email"].startswith("test@"):
        return "test_internal", 100, ["TEST_OR_INTERNAL"]

    hits = []
    if row["domain"] in policy["disposable_domains"]:
        hits.append("DISPOSABLE_EMAIL")
    if looks_mashed(name):
        hits.append("KEYBOARD_MASH_NAME")
    if random_localpart(row["email"]):
        hits.append("RANDOM_EMAIL_LOCALPART")
    if fake_phone(row["phone"]):
        hits.append("FAKE_PHONE")
    msg = row["message"].lower()
    if "http" in msg and any(p in msg for p in s["pitch_words"]):
        hits.append("PITCH_MESSAGE_WITH_LINK")
    if policy["require_page_url"] and not row["page_url"]:
        hits.append("NO_PAGE_URL")
    if len(by_message.get(" ".join(msg.split()), ())) > 1:
        hits.append("SAME_MESSAGE_MANY_EMAILS")
    if row["phone"] and len(by_phone.get(row["phone"], ())) > 1 and not fake_phone(row["phone"]):
        hits.append("SAME_PHONE_MANY_EMAILS")

    score = min(100, sum(w[h] for h in hits))
    if score >= s["quarantine_at"]:
        return "likely_spam", score, hits
    if score >= s["review_at"]:
        return "review", score, hits
    return "clean", score, hits
