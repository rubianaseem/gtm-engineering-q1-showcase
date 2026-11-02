"""Step 3. CRM match: find the existing contact, the company and its parent, and resolve messy owners.

Patterns from event-lead-import-agent (exact email = update, same domain and surname = review),
account-hierarchy-agent (domain first, then parent) and book-of-business-transfer-agent (owner aliases).
"""
import csv
import re
from pathlib import Path


def read_csv(path):
    with open(Path(path), newline="", encoding="utf-8-sig") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def clean_domain(value):
    return re.sub(r"^(https?://)?(www\.)?", "", (value or "").lower()).strip("/")


class CRM:
    def __init__(self, contacts_path, companies_path, reps_path, policy):
        self.policy = policy
        self.contacts = read_csv(contacts_path)
        self.companies = {c["company_id"]: c for c in read_csv(companies_path)}
        self.reps = read_csv(reps_path)
        for rep in self.reps:
            rep["daily_cap"] = int(rep["daily_cap"] or 0)
            rep["assigned_today"] = int(rep["assigned_today"] or 0)
            rep["assigned_this_run"] = 0
        self.rep_by_email = {r["email"].lower(): r for r in self.reps}
        self.contact_by_email = {c["email"].lower(): c for c in self.contacts}
        self.company_by_domain = {clean_domain(c["domain"]): c for c in self.companies.values()}

    def resolve_owner(self, value):
        """Owner fields hold emails, names or initials. Return (rep or None, resolved?)."""
        v = (value or "").strip().lower()
        if not v:
            return None, True  # blank owner is a fact, not an error
        email = v if "@" in v else self.policy["owner_aliases"].get(v, "")
        rep = self.rep_by_email.get(email)
        return rep, rep is not None

    def match(self, lead):
        """Return a dict describing what the CRM already knows about this lead."""
        result = {"contact": None, "company": None, "parent": None, "possible_duplicate": None}
        contact = self.contact_by_email.get(lead["email"])
        if contact:
            result["contact"] = contact
        domain = lead["domain"] if lead["domain"] not in self.policy["free_email_domains"] else lead["website"]
        company = self.company_by_domain.get(domain) or self.company_by_domain.get(lead["website"])
        if contact and contact.get("company_id") in self.companies:
            company = self.companies[contact["company_id"]]
        result["company"] = company
        if company and company.get("parent_company_id") in self.companies:
            result["parent"] = self.companies[company["parent_company_id"]]
        if not contact and lead["last_name"]:
            for c in self.contacts:
                same_domain = c["email"].split("@")[-1] == lead["domain"]
                if same_domain and c["lastname"].lower() == lead["last_name"].lower():
                    result["possible_duplicate"] = c
                    break
        return result
