import csv
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from showcase import ingest, lifecycle, qualify, triage, utm
from showcase.crm import CRM
from showcase.pipeline import run
from showcase.route import Router

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F]")


def lead(**kw):
    base = ingest.normalise_row({"email": "a.b@example.com", "full_name": "Ann Bell", "title": "Manager",
                                 "country": "UK", "page_url": "https://x/demo", "submitted_at": "2026-11-02 09:00"}, POLICY)
    base.update(kw)
    return base


class IngestTests(unittest.TestCase):
    def test_header_aliases_map_to_one_name(self):
        m = ingest.map_headers(["Email Address", "Full Name", "Job Title", "Weird Column"])
        self.assertEqual(m["Email Address"], "email")
        self.assertEqual(m["Job Title"], "title")
        self.assertEqual(m["Weird Column"], "weird column")

    def test_name_with_title_is_split_and_cased(self):
        first, last, title = ingest.split_name("daniel kim - RevOps Lead", "", "", "")
        self.assertEqual((first, last, title), ("Daniel", "Kim", "RevOps Lead"))
        self.assertEqual(ingest.fix_case("siobhan o'neill"), "Siobhan O'Neill")
        self.assertEqual(ingest.fix_case("McDonald"), "McDonald")

    def test_country_and_uk_mobile(self):
        self.assertEqual(ingest.normalise_country("Österreich", POLICY), "AT")
        self.assertEqual(ingest.normalise_phone("07700 900123", "GB"), "+447700900123")

    def test_merge_keeps_most_restrictive_consent(self):
        a = lead(email="x@y.com", consent="opted_in", submitted_at="2026-11-02 08:00")
        b = lead(email="x@y.com", consent="opted_out", submitted_at="2026-11-02 09:00", message="")
        merged = ingest.merge_duplicates([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["consent"], "opted_out")
        self.assertIn("MERGED_DUPLICATE_SUBMISSIONS", merged[0]["notes"])

    def test_blank_consent_is_never_opt_in(self):
        self.assertEqual(ingest.normalise_consent(""), "unknown")


class TriageTests(unittest.TestCase):
    def test_keyboard_mash_and_disposable_is_quarantined(self):
        row = lead(email="asdkjh@mailinator.com", domain="mailinator.com", first_name="Asdfgh", last_name="Qwerty", phone="1111111111")
        verdict, score, hits = triage.triage(row, POLICY, triage.build_crowd_signals([row]))
        self.assertEqual(verdict, "likely_spam")
        self.assertIn("DISPOSABLE_EMAIL", hits)

    def test_same_pitch_from_two_emails_is_coordinated(self):
        msg = "We can rank your site #1 with backlinks http://spam.example"
        a, b = lead(email="a@one.biz", message=msg, phone=""), lead(email="b@two.biz", message=msg, phone="")
        crowd = triage.build_crowd_signals([a, b])
        verdict, _, hits = triage.triage(a, POLICY, crowd)
        self.assertEqual(verdict, "likely_spam")
        self.assertIn("SAME_MESSAGE_MANY_EMAILS", hits)

    def test_own_domain_is_test_not_lead(self):
        row = lead(email="test@northbeam.io", domain="northbeam.io")
        self.assertEqual(triage.triage(row, POLICY, triage.build_crowd_signals([row]))[0], "test_internal")

    def test_real_lead_is_clean(self):
        row = lead(phone="+447700900123")
        self.assertEqual(triage.triage(row, POLICY, triage.build_crowd_signals([row]))[0], "clean")


class UtmTests(unittest.TestCase):
    def test_aliases_fixed(self):
        clean, flags = utm.normalise_utm("Google Ads", "PPC", "Q4-RevOps-Demo", POLICY)
        self.assertEqual(clean, {"source": "google", "medium": "cpc", "campaign": "q4_revops_demo"})
        self.assertIn("UTM_CAMPAIGN_FIXED", flags)

    def test_internal_and_ambiguous_flags(self):
        self.assertIn("UTM_INTERNAL_TAG", utm.normalise_utm("website", "banner", "hero", POLICY)[1])
        self.assertIn("UTM_MEDIUM_AMBIGUOUS", utm.normalise_utm("facebook", "social", "x", POLICY)[1])


class LifecycleAndScoreTests(unittest.TestCase):
    def test_never_moves_backward(self):
        stage, note, block = lifecycle.decide_stage("opportunity", "marketingqualifiedlead", POLICY)
        self.assertEqual((stage, note, block), ("", "LIFECYCLE_KEPT_NO_BACKWARD_MOVE", None))

    def test_moves_forward_and_reads_labels(self):
        self.assertEqual(lifecycle.decide_stage("Lead", "marketingqualifiedlead", POLICY)[0], "marketingqualifiedlead")
        self.assertEqual(lifecycle.normalise_stage("MQL", POLICY), ("marketingqualifiedlead", True))

    def test_custom_value_blocks(self):
        self.assertEqual(lifecycle.decide_stage("Trial User", "lead", POLICY)[2], "UNKNOWN_LIFECYCLE_VALUE")

    def test_scoring_tiers_and_word_boundaries(self):
        strong = lead(title="VP Marketing", employees=450, demo_requested=True, pages_viewed=7, domain="orbit.com")
        weak = lead(title="Founder", employees=3, domain="gmail.com", pages_viewed=2)
        self.assertEqual(qualify.score_lead(strong, POLICY)[1], "A")
        self.assertEqual(qualify.score_lead(weak, POLICY)[1], "C")
        coordinator = lead(title="Marketing Coordinator")
        parts = dict(qualify.score_lead(coordinator, POLICY)[2])
        self.assertNotIn("senior title", parts)  # 'coo' inside 'coordinator' must not count


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.crm = CRM(ROOT / "sample_crm_contacts.csv", ROOT / "sample_crm_companies.csv", ROOT / "sample_reps.csv", POLICY)
        self.router = Router(self.crm, POLICY)

    def test_round_robin_skips_ooo_and_full_reps(self):
        new = lead(email="z@newco.com", domain="newco.com", country="US")
        rep, route, reasons, _ = self.router.route(new, self.crm.match(new), "A")
        self.assertEqual((rep["name"], route), ("Priya Shah", "ae_alert"))  # Sam is OOO
        dach = lead(email="z@kontor.de", domain="kontor.de", country="DE")
        self.assertEqual(self.router.route(dach, self.crm.match(dach), "B")[2], ["ALL_REPS_AT_CAP"])  # Lena is full

    def test_departed_owner_goes_to_manager(self):
        owen = lead(email="o.brien@brightwave.co.uk", domain="brightwave.co.uk", country="GB")
        rep, route, reasons, _ = self.router.route(owen, self.crm.match(owen), "B")
        self.assertIsNone(rep)
        self.assertEqual(reasons, ["OWNER_DEPARTED"])

    def test_owner_alias_and_parent_company(self):
        rep, ok = self.crm.resolve_owner("Jordan L.")
        self.assertTrue(ok)
        self.assertEqual(rep["name"], "Jordan Lee")
        leon = lead(email="leon@brightwave.de", domain="brightwave.de", last_name="Fischer")
        m = self.crm.match(leon)
        self.assertEqual(m["parent"]["name"], "Brightwave Ltd")

    def test_same_domain_and_surname_is_possible_duplicate(self):
        rachel = lead(email="rachel.cole@medcore.health", domain="medcore.health", last_name="Cole")
        self.assertEqual(self.crm.match(rachel)["possible_duplicate"]["email"], "r.cole@medcore.health")


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        paths = {"leads": ROOT / "sample_inbound_leads.csv", "contacts": ROOT / "sample_crm_contacts.csv",
                 "companies": ROOT / "sample_crm_companies.csv", "reps": ROOT / "sample_reps.csv"}
        cls.res = run(paths, ROOT / "policy.json", cls.out, ROOT / "sql")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_counts_add_up(self):
        f = self.res["facts"]
        self.assertEqual(f["rows_in"], 27)
        self.assertEqual(f["unique_leads"], 26)
        self.assertEqual(sum(f["outcomes"].values()), 26)
        self.assertEqual(self.res["mode"], "rules")

    def test_import_file_holds_only_clean_rows(self):
        with open(self.out / "crm_import_contacts.csv", newline="") as fh:
            emails = {r["Email"] for r in csv.DictReader(fh)}
        blocked = {l["email"] for l in self.res["leads"] if l["outcome"] != "import"}
        self.assertTrue(emails)
        self.assertFalse(emails & blocked)

    def test_every_output_written_and_emoji_free(self):
        for name in ["crm_import_contacts.csv", "review_queue.csv", "quarantine.csv", "run_brief.md", "run_log.json", "run.db"]:
            self.assertTrue((self.out / name).exists(), name)
        self.assertEqual(len(list((self.out / "reports").glob("*.csv"))), 5)
        for p in list(self.out.glob("*.md")) + list((self.out / "briefs").glob("*.md")) + list(self.out.glob("*.csv")):
            self.assertIsNone(EMOJI_RE.search(p.read_text(encoding="utf-8")), p.name)

    def test_sql_reports_answer_questions(self):
        reasons = dict((r[0], r[1]) for r in self.res["reports"]["03_review_reasons"][1])
        self.assertEqual(reasons["ALL_REPS_AT_CAP"], 4)
        self.assertNotIn("FAKE_PHONE", reasons)  # spam signals are not review reasons
        raw_per_clean = {}
        for clean, raw, n in self.res["reports"]["04_utm_raw_to_clean"][1]:
            raw_per_clean.setdefault(clean, set()).add(raw)
        self.assertGreater(len(raw_per_clean["google / cpc / q4_revops_demo"]), 1)


if __name__ == "__main__":
    unittest.main()
