"""Step 9. SQL reports: load the run into SQLite and answer the questions RevOps asks after every batch.

Pattern from gtm-sql-revops-queries. The SQL files live in sql/ so you can read and change them.
"""
import sqlite3
from pathlib import Path

LEAD_COLUMNS = ["email", "company", "country", "territory", "tier", "score", "verdict", "outcome", "action",
                "route", "owner_email", "utm_source_raw", "utm_medium_raw", "utm_campaign_raw",
                "utm_source", "utm_medium", "utm_campaign", "submitted_at"]


def build_db(leads, reps, db_path):
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()  # the run database is rebuilt from scratch every run
    con = sqlite3.connect(db_path)
    con.execute(f"CREATE TABLE leads ({', '.join(c + ' TEXT' for c in LEAD_COLUMNS)})")
    con.execute("CREATE TABLE lead_reasons (email TEXT, code TEXT, kind TEXT)")
    con.execute("CREATE TABLE reps (rep_id TEXT, name TEXT, email TEXT, role TEXT, territory TEXT, status TEXT,"
                " daily_cap INTEGER, assigned_today INTEGER, assigned_this_run INTEGER)")
    for lead in leads:
        con.execute(f"INSERT INTO leads VALUES ({', '.join('?' for _ in LEAD_COLUMNS)})",
                    [str(lead.get(c, "")) for c in LEAD_COLUMNS])
        kind = "spam_signal" if lead["outcome"] == "quarantine" else "blocking"
        for code in lead["reasons"]:
            con.execute("INSERT INTO lead_reasons VALUES (?, ?, ?)", (lead["email"], code, kind))
        for note in lead["notes"]:
            con.execute("INSERT INTO lead_reasons VALUES (?, ?, 'note')", (lead["email"], note.split(" (")[0]))
    for r in reps:
        con.execute("INSERT INTO reps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["rep_id"], r["name"], r["email"], r["role"], r["territory"], r["status"],
                     r["daily_cap"], r["assigned_today"], r["assigned_this_run"]))
    con.commit()
    return con


def run_reports(con, sql_dir):
    results = {}
    for path in sorted(Path(sql_dir).glob("*.sql")):
        cur = con.execute(path.read_text())
        results[path.stem] = ([d[0] for d in cur.description], cur.fetchall())
    return results
