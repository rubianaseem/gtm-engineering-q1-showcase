import json
import tempfile
import unittest
from pathlib import Path

import portfolio_audit as pa

ROOT = Path(__file__).resolve().parents[1]


class PortfolioAuditTests(unittest.TestCase):
    def make_repo(self, root, readme, files=()):
        d = Path(root)
        (d / "README.md").write_text(readme, encoding="utf-8")
        for f in files:
            (d / f).parent.mkdir(parents=True, exist_ok=True)
            (d / f).write_text("def test_x():\n    pass\n" if f.endswith(".py") else "x", encoding="utf-8")
        return d

    def test_tidy_repo_passes_required_checks(self):
        with tempfile.TemporaryDirectory() as t:
            readme = "# A\n\nBuilt by Rubia Naseem, GTM Engineer.\n\n## Where each step runs\n\n1. GitHub\n"
            d = self.make_repo(t, readme, ["SETUP.md", "requirements.txt", "sample_leads.csv", "tests/test_a.py"])
            checks = pa.audit_repo(d)
            self.assertEqual(checks["test_functions"], 1)
            self.assertEqual([x for x in pa.tidy_list(checks) if x[0] == "required"], [])

    def test_long_readme_with_emoji_is_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_repo(t, "word " * 950 + "\U0001F680")
            todo = [label for lvl, label in pa.tidy_list(pa.audit_repo(d)) if lvl == "required"]
            self.assertTrue(any(label.startswith("shorten README (951 words") for label in todo))
            self.assertTrue(any(label.startswith("remove emojis") for label in todo))
            self.assertIn("add automated tests", todo)

    def test_map_covers_every_repo_in_the_portfolio(self):
        portfolio = json.loads((ROOT / "portfolio" / "portfolio.json").read_text(encoding="utf-8"))
        text = pa.render_map(portfolio, pa.load_snapshot())
        for e in portfolio["repos"]:
            self.assertIn(f"https://github.com/rubianaseem/{e['repo']}", text)
        self.assertTrue(set(e["pipeline_step"] for e in portfolio["repos"]) - {""})


if __name__ == "__main__":
    unittest.main()
