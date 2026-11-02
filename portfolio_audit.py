"""Portfolio audit: map every repo of the quarter to the skill it shows, then check each one is tidy.

Usage:
  python portfolio_audit.py              # offline, from portfolio/snapshot.json
  python portfolio_audit.py --clones DIR # audit local clones (one folder per repo) and refresh the snapshot
  python portfolio_audit.py --fetch      # clone each public repo to a temp folder, read descriptions, refresh the snapshot

It only reads. It never pushes, edits or deletes anything in the audited repos.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F]")
README_LIMIT = 900
CHECKS = [  # (key, label, required?)
    ("readme", "README.md", True),
    ("readme_under_limit", f"README at or under {README_LIMIT} words", True),
    ("bio_line", "bio line", True),
    ("where_each_step_runs", "'Where each step runs' section", True),
    ("setup_md", "SETUP.md", True),
    ("has_tests", "automated tests", True),
    ("sample_data", "sample data", True),
    ("requirements", "requirements.txt", True),
    ("env_example", ".env.example", False),
    ("license", "LICENSE", False),
    ("emoji_free", "no emojis in docs", True),
    ("details_md", "docs/DETAILS.md", False),
    ("walkthrough_md", "docs/WALKTHROUGH.md", False),
]


def count_tests(repo_dir):
    n = 0
    for path in Path(repo_dir).rglob("*.py"):
        if ".venv" in path.parts or "site-packages" in path.parts:
            continue
        if path.name.startswith("test_") or "tests" in path.parts:
            n += len(re.findall(r"^\s*def test_\w+", path.read_text(encoding="utf-8", errors="ignore"), re.M))
    return n


def audit_repo(repo_dir):
    d = Path(repo_dir)
    readme = d / "README.md"
    text = readme.read_text(encoding="utf-8", errors="ignore") if readme.exists() else ""
    words = len(text.split())
    md_files = [p for p in d.rglob("*.md") if ".venv" not in p.parts and ".git" not in p.parts]
    emoji_files = [str(p.relative_to(d)) for p in md_files if EMOJI_RE.search(p.read_text(encoding="utf-8", errors="ignore"))]
    tests = count_tests(d)
    return {
        "readme": readme.exists(),
        "readme_words": words,
        "readme_under_limit": readme.exists() and words <= README_LIMIT,
        "bio_line": "Built by Rubia Naseem" in text,
        "where_each_step_runs": bool(re.search(r"^#+\s*Where each step runs", text, re.M | re.I)),
        "setup_md": (d / "SETUP.md").exists(),
        "test_functions": tests,
        "has_tests": tests > 0,
        "sample_data": any(d.glob("sample*")) or (d / "data").is_dir(),
        "requirements": (d / "requirements.txt").exists(),
        "env_example": (d / ".env.example").exists(),
        "license": (d / "LICENSE").exists(),
        "emoji_free": not emoji_files,
        "emoji_files": emoji_files,
        "details_md": (d / "docs" / "DETAILS.md").exists(),
        "walkthrough_md": (d / "docs" / "WALKTHROUGH.md").exists(),
    }


def tidy_list(checks):
    """Plain-English to-do list: required checks first, then nice-to-haves."""
    todo = []
    for key, label, required in CHECKS:
        if not checks.get(key):
            if key == "readme_under_limit" and checks.get("readme"):
                label = f"shorten README ({checks['readme_words']} words, limit {README_LIMIT})"
            elif key == "emoji_free":
                label = "remove emojis from " + ", ".join(checks.get("emoji_files", []))
            else:
                label = "add " + label
            todo.append(("required" if required else "nice to have", label))
    return todo


def fetch_description(owner, repo):
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}", headers={"Accept": "application/vnd.github+json"})
    if os.getenv("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("description") or ""


def refresh(portfolio, clones_dir=None, fetch=False):
    snapshot = load_snapshot()
    owner = portfolio["owner"]
    tmp = tempfile.TemporaryDirectory() if fetch else None
    base = Path(tmp.name) if tmp else Path(clones_dir)
    for entry in portfolio["repos"]:
        name = entry["repo"]
        if fetch:
            subprocess.run(["git", "clone", "--depth", "1", "-q", f"https://github.com/{owner}/{name}.git", str(base / name)], check=True)
        repo_dir = base / name
        if not repo_dir.is_dir():
            print(f"  skipped {name}: no folder at {repo_dir}")
            continue
        snap = snapshot["repos"].setdefault(name, {})
        snap["checks"] = audit_repo(repo_dir)
        if fetch:
            snap["description"] = fetch_description(owner, name)
        print(f"  audited {name}")
    snapshot["audited_on"] = date.today().isoformat()
    (HERE / "portfolio" / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    if tmp:
        tmp.cleanup()
    return snapshot


def load_snapshot():
    path = HERE / "portfolio" / "snapshot.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"audited_on": "", "repos": {}}


def render_map(portfolio, snapshot):
    owner = portfolio["owner"]
    lines = [f"# {portfolio['quarter']} portfolio map", "",
             f"Generated by `portfolio_audit.py` from the repos as they were on {snapshot.get('audited_on') or 'unknown'}. "
             "Descriptions come from each repo's GitHub description. Test counts are `def test_` functions found in the code, "
             "so parametrised tests count once.", "", portfolio.get("note", ""), "",
             "## What each repo shows", "",
             "| Repo | Published | Skill | The pain | Patterns | Used in this pipeline |", "|---|---|---|---|---|---|"]
    for e in portfolio["repos"]:
        lines.append(f"| [{e['repo']}](https://github.com/{owner}/{e['repo']}) | {e['when']} | {e['skill']} | {e['pain']} | "
                     f"{', '.join(e['patterns'])} | {e['pipeline_step'] or '-'} |")
    lines += ["", "Pattern key: " + "; ".join(f"`{k}` {v}" for k, v in portfolio["pattern_names"].items()) + ".", "",
              "## Descriptions", ""]
    for e in portfolio["repos"]:
        desc = snapshot["repos"].get(e["repo"], {}).get("description") or "(no GitHub description set)"
        lines.append(f"- **{e['repo']}**: {desc}")
    lines += ["", "## Tidy check", "", "| Repo | README words | Tests found | Where each step runs | SETUP.md | Sample data | No emojis |",
              "|---|---|---|---|---|---|---|"]
    yn = lambda v: "yes" if v else "no"
    for e in portfolio["repos"]:
        c = snapshot["repos"].get(e["repo"], {}).get("checks")
        if not c:
            lines.append(f"| {e['repo']} | not audited | | | | | |")
            continue
        lines.append(f"| {e['repo']} | {c['readme_words']} | {c['test_functions']} | {yn(c['where_each_step_runs'])} | "
                     f"{yn(c['setup_md'])} | {yn(c['sample_data'])} | {yn(c['emoji_free'])} |")
    lines += ["", "## Tidy list", ""]
    for e in portfolio["repos"]:
        c = snapshot["repos"].get(e["repo"], {}).get("checks")
        todo = [t for t in tidy_list(c) if t[0] == "required"] if c else []
        if todo:
            lines.append(f"- **{e['repo']}**: " + "; ".join(label for _, label in todo))
    if lines[-1] == "":
        lines.append("- Nothing required. Every repo passes the required checks.")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--clones", help="folder holding one local clone per repo")
    g.add_argument("--fetch", action="store_true", help="clone the public repos into a temp folder first")
    p.add_argument("--out", default=str(HERE / "out"))
    a = p.parse_args()
    portfolio = json.loads((HERE / "portfolio" / "portfolio.json").read_text(encoding="utf-8"))
    snapshot = refresh(portfolio, a.clones, a.fetch) if (a.clones or a.fetch) else load_snapshot()
    if not snapshot["repos"]:
        sys.exit("No snapshot yet. Run with --fetch or --clones DIR first.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "PORTFOLIO_MAP.md").write_text(render_map(portfolio, snapshot), encoding="utf-8")
    with open(out / "portfolio_audit.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repo", "skill", "readme_words", "test_functions"] + [k for k, _, _ in CHECKS] + ["required_fixes"])
        for e in portfolio["repos"]:
            c = snapshot["repos"].get(e["repo"], {}).get("checks", {})
            fixes = [l for lvl, l in tidy_list(c) if lvl == "required"] if c else ["not audited"]
            w.writerow([e["repo"], e["skill"], c.get("readme_words", ""), c.get("test_functions", "")]
                       + [c.get(k, "") for k, _, _ in CHECKS] + ["; ".join(fixes)])
    audited = [e for e in portfolio["repos"] if snapshot["repos"].get(e["repo"], {}).get("checks")]
    clean = [e for e in audited if not [t for t in tidy_list(snapshot["repos"][e["repo"]]["checks"]) if t[0] == "required"]]
    with_tests = [e for e in audited if snapshot["repos"][e["repo"]]["checks"]["has_tests"]]
    print(f"Portfolio audit ({snapshot.get('audited_on')}): {len(audited)} repos audited.")
    print(f"  Pass every required check: {len(clean)}. Have automated tests: {len(with_tests)}.")
    for e in audited:
        todo = [l for lvl, l in tidy_list(snapshot["repos"][e["repo"]]["checks"]) if lvl == "required"]
        print(f"  {e['repo']:<36} {'tidy' if not todo else '; '.join(todo)}")
    print(f"Wrote {out.name}/PORTFOLIO_MAP.md and {out.name}/portfolio_audit.csv")


if __name__ == "__main__":
    main()
