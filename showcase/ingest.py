"""Step 1. Ingest: map messy headers, clean every field, merge duplicate submissions.

Pattern from event-lead-import-agent (header mapping, name fixes, most restrictive consent)
and inbound-lead-router-n8n-to-python (country clean-up, merge instead of drop).
"""
import csv
import re
from pathlib import Path

HEADER_ALIASES = {
    "email": ["email", "email address", "e-mail", "work email"],
    "full_name": ["full name", "name", "contact name"],
    "first_name": ["first name", "firstname"],
    "last_name": ["last name", "lastname", "surname"],
    "title": ["job title", "title", "role"],
    "company": ["company", "company name", "organisation", "organization"],
    "website": ["website", "company website", "domain"],
    "country": ["country", "country/region"],
    "employees": ["employees", "company size", "number of employees"],
    "form": ["form", "form name"],
    "page_url": ["page url", "page", "conversion page"],
    "utm_source": ["utm_source", "utm source"],
    "utm_medium": ["utm_medium", "utm medium"],
    "utm_campaign": ["utm_campaign", "utm campaign"],
    "message": ["message", "comments", "how can we help?"],
    "phone": ["phone", "phone number", "mobile"],
    "consent": ["consent", "marketing consent", "opt in"],
    "submitted_at": ["submitted at", "submission date", "created"],
    "pages_viewed": ["pages viewed", "page views"],
    "demo_requested": ["demo requested", "demo"],
}

EMAIL_RE = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
CONSENT_RANK = {"opted_out": 0, "unknown": 1, "opted_in": 2}  # lower = more restrictive


def map_headers(fieldnames):
    """Return {raw header: canonical name}. Unknown headers keep a lowercased name."""
    lookup = {alias: canon for canon, aliases in HEADER_ALIASES.items() for alias in aliases}
    return {h: lookup.get(h.strip().lower(), h.strip().lower()) for h in fieldnames}


def fix_case(name):
    """ALL CAPS or all lower names become Title Case. Mixed case is left alone (McDonald, DeVries)."""
    name = " ".join(name.split())
    if name and (name.isupper() or name.islower()):
        return name.title()
    return name


def split_name(full, first, last, title):
    """Handle 'Daniel Kim - RevOps Lead' in the name field and fill title from it if blank."""
    full = (full or "").strip()
    if " - " in full:
        full, extra = full.split(" - ", 1)
        title = title or extra.strip()
    if not (first or last) and full:
        parts = full.split()
        first, last = parts[0], " ".join(parts[1:])
    return fix_case(first or ""), fix_case(last or ""), (title or "").strip()


def normalise_country(value, policy):
    v = (value or "").strip().lower()
    for iso, aliases in policy["country_aliases"].items():
        if v in aliases:
            return iso
    return ""


def normalise_phone(value, country):
    digits = re.sub(r"[^\d+]", "", value or "")
    if country == "GB" and digits.startswith("07"):
        digits = "+44" + digits[1:]
    return digits


def normalise_consent(value):
    v = (value or "").strip().lower()
    if v in {"yes", "y", "true", "1", "opt-in", "opted_in", "opted in"}:
        return "opted_in"
    if v in {"no", "n", "false", "0", "opt-out", "opted_out", "unsubscribed"}:
        return "opted_out"
    return "unknown"  # blank never counts as opt-in


def to_int(value):
    m = re.search(r"\d[\d,]*", value or "")
    return int(m.group().replace(",", "")) if m else None


def normalise_row(raw, policy):
    r = {k: (v or "").strip() for k, v in raw.items()}
    email = r.get("email", "").lower()
    first, last, title = split_name(r.get("full_name"), r.get("first_name"), r.get("last_name"), r.get("title"))
    country = normalise_country(r.get("country"), policy)
    website = re.sub(r"^(https?://)?(www\.)?", "", r.get("website", "").lower()).strip("/")
    return {
        "email": email,
        "email_valid": bool(EMAIL_RE.match(email)),
        "domain": email.split("@")[-1] if "@" in email else "",
        "first_name": first,
        "last_name": last,
        "title": title,
        "company": r.get("company", ""),
        "website": website,
        "country_raw": r.get("country", ""),
        "country": country,
        "employees": to_int(r.get("employees")),
        "form": r.get("form", ""),
        "page_url": r.get("page_url", ""),
        "utm_source_raw": r.get("utm_source", ""),
        "utm_medium_raw": r.get("utm_medium", ""),
        "utm_campaign_raw": r.get("utm_campaign", ""),
        "message": r.get("message", ""),
        "phone": normalise_phone(r.get("phone"), country),
        "consent": normalise_consent(r.get("consent")),
        "submitted_at": r.get("submitted_at", ""),
        "pages_viewed": to_int(r.get("pages_viewed")) or 0,
        "demo_requested": r.get("demo_requested", "").lower() in {"yes", "y", "true", "1"},
        "merged_submissions": 1,
        "reasons": [],
        "notes": [],
    }


def merge_duplicates(rows):
    """One row per email. Later submissions win on filled fields; consent takes the most restrictive value."""
    merged, order = {}, []
    for row in sorted(rows, key=lambda r: r["submitted_at"]):
        key = row["email"] or f"__blank_{len(order)}"
        if key not in merged:
            merged[key] = row
            order.append(key)
            continue
        keep = merged[key]
        for field, value in row.items():
            if field in {"reasons", "notes", "merged_submissions", "consent"}:
                continue
            if value not in ("", None, 0, False):
                keep[field] = value
        if CONSENT_RANK[row["consent"]] < CONSENT_RANK[keep["consent"]]:
            keep["consent"] = row["consent"]
        keep["demo_requested"] = keep["demo_requested"] or row["demo_requested"]
        keep["merged_submissions"] += 1
    out = [merged[k] for k in order]
    for row in out:
        if row["merged_submissions"] > 1:
            row["notes"].append("MERGED_DUPLICATE_SUBMISSIONS")
    return out


def read_leads(path, policy):
    with open(Path(path), newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header_map = map_headers(reader.fieldnames or [])
        raw_rows = [{header_map[k]: v for k, v in row.items() if k is not None} for row in reader]
    rows = [normalise_row(r, policy) for r in raw_rows]
    return len(raw_rows), merge_duplicates(rows)
