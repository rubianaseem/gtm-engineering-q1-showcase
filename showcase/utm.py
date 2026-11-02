"""Step 4. UTM governance: map typed variants to one taxonomy and flag what splits reports.

Pattern from utm-governance-agent. Fixes are notes, not blockers: the lead still routes.
"""
import re


def _lookup(value, mapping):
    v = " ".join((value or "").strip().lower().split())
    for clean, variants in mapping.items():
        if v in variants:
            return clean
    return None


def normalise_utm(source, medium, campaign, policy):
    u = policy["utm"]
    flags = []
    src_raw, med_raw, camp_raw = (source or "").strip(), (medium or "").strip(), (campaign or "").strip()
    if not (src_raw or med_raw or camp_raw):
        return {"source": "(none)", "medium": "(none)", "campaign": "(none)"}, ["UTM_MISSING"]

    if src_raw.lower() in u["internal_sources"]:
        flags.append("UTM_INTERNAL_TAG")  # internal links overwrite the visitor's real source
    src = _lookup(src_raw, u["sources"])
    if src is None:
        src = src_raw.lower() or "(missing)"
        flags.append("UTM_SOURCE_UNKNOWN")
    elif src != src_raw:
        flags.append("UTM_SOURCE_FIXED")

    if med_raw.lower() in u["ambiguous_mediums"]:
        med = med_raw.lower()
        flags.append("UTM_MEDIUM_AMBIGUOUS")  # 'social' could be paid or organic
    else:
        med = _lookup(med_raw, u["mediums"])
        if med is None:
            med = med_raw.lower() or "(missing)"
            flags.append("UTM_MEDIUM_UNKNOWN")
        elif med != med_raw:
            flags.append("UTM_MEDIUM_FIXED")

    camp = re.sub(r"[\s-]+", "_", camp_raw.lower())
    camp = re.sub(r"[^a-z0-9_]", "", camp).strip("_")
    if not re.match(u["campaign_pattern"], camp_raw):
        flags.append("UTM_CAMPAIGN_FIXED" if camp else "UTM_CAMPAIGN_MISSING")
    return {"source": src, "medium": med, "campaign": camp or "(missing)"}, flags
