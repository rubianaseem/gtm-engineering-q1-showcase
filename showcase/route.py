"""Step 7. Route: keep the right existing owner, otherwise round robin inside the territory.

Patterns from inbound-lead-router-n8n-to-python (round robin with OOO and daily cap fallback)
and book-of-business-transfer-agent (a departed owner's contact goes to a human, not to whoever is next).
"""


def territory_for(country, policy):
    for name, countries in policy["territories"].items():
        if country in countries:
            return name
    return ""


class Router:
    def __init__(self, crm, policy):
        self.crm = crm
        self.policy = policy

    def round_robin(self, role, territory):
        """Least-loaded active rep in the pool who is under today's cap. Ties go to the lower rep_id."""
        pool = [r for r in self.crm.reps
                if r["role"] == role and r["territory"] == territory and r["status"] == "active"
                and r["assigned_today"] + r["assigned_this_run"] < r["daily_cap"]]
        if not pool:
            return None
        rep = min(pool, key=lambda r: (r["assigned_today"] + r["assigned_this_run"], r["rep_id"]))
        rep["assigned_this_run"] += 1
        return rep

    def existing_owner(self, match):
        """Walk contact owner, then company owner, then parent company owner. First non-blank wins."""
        for label, record in (("contact", match["contact"]), ("company", match["company"]), ("parent company", match["parent"])):
            if record and record.get("owner"):
                rep, resolved = self.crm.resolve_owner(record["owner"])
                return label, record["owner"], rep, resolved
        return None, "", None, True

    def route(self, lead, match, tier):
        """Return (owner rep or None, route name, blocking reasons, notes)."""
        reasons, notes = [], []
        territory = territory_for(lead["country"], self.policy)
        lead["territory"] = territory
        label, raw_owner, rep, resolved = self.existing_owner(match)
        company = match["company"]
        is_customer = bool(company and company.get("lifecycle_stage", "").lower() == "customer")

        if label and not resolved:
            return None, "revops_queue", ["UNRESOLVED_OWNER"], [f"{label} owner '{raw_owner}' matches no rep"]
        if rep:
            if rep["status"] == "active":
                notes.append(f"OWNER_KEPT_FROM_{label.upper().replace(' ', '_')}")
                route = "account_owner_expansion" if is_customer else "account_owner"
                return rep, route, reasons, notes
            if rep["status"] == "departed":
                return None, "manager_review", ["OWNER_DEPARTED"], [f"{label} owner {rep['name']} has left"]
            if rep["status"] == "ooo":
                notes.append(f"OWNER_OOO_FALLBACK ({rep['name']})")
                fallback = self.round_robin(rep["role"], rep["territory"])
                if fallback:
                    return fallback, "ooo_fallback", reasons, notes
                return None, "revops_queue", ["ALL_REPS_AT_CAP"], notes

        role = self.policy["routing"]["tier_role"].get(tier)
        if not role:
            return None, "nurture", reasons, notes
        if not territory:
            return None, "revops_queue", ["NO_TERRITORY"], [f"country '{lead['country_raw']}' is outside every territory"]
        rep = self.round_robin(role, territory)
        if not rep:
            return None, "revops_queue", ["ALL_REPS_AT_CAP"], [f"every {territory} {role} is OOO or at today's cap"]
        return rep, "ae_alert" if role == "AE" else "sdr_sequence", reasons, notes
