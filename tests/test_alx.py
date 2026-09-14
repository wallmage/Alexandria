"""Tests for the `alx` entry point (spec 09-14-01 §5, §6)."""

import io
import json
import re
import shlex
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts import alx
from tests.source_fidelity_transport import mock_production_transport

PAGE = """<html><head><title>Ledger Study</title>
<meta property="article:published_time" content="2026-01-05">
</head><body>
<h1>Ledger Study</h1>
<p>The archive released 1,204 documents in March 2026, and the registry confirmed the count.</p>
<p>Retention rose to 88 percent after the second review round, the registry reported.</p>
<p>The reading room keeps 「原始日記」 under restricted access for named researchers.</p>
</body></html>"""

SECOND_PAGE = """<html><head><title>Registry Note</title></head><body>
<p>The registry logged 1,204 documents in March 2026 and published its own tally.</p>
</body></html>"""

CLAIM_ONE = {
    "claim_id": "C1",
    "claim": "The archive released 1,204 documents in March 2026.",
    "kind": "fact",
    "importance": "key",
    "decision_relevance": "The count decides whether the release is complete.",
    "what_would_change": "A registry tally with a different count.",
    "source_evidence": [
        {
            "source_id": "S1",
            "extract_or_location": (
                "The archive released 1,204 documents in March 2026, "
                "and the registry confirmed the count."
            ),
        }
    ],
}

CLAIM_TWO = {
    "claim_id": "C2",
    "claim": "The registry logged 1,204 documents in March 2026.",
    "kind": "fact",
    "importance": "supporting",
    "source_evidence": [
        {
            "source_id": "S2",
            "extract_or_location": (
                "The registry logged 1,204 documents in March 2026 and published "
                "its own tally."
            ),
        }
    ],
}

COVERAGE_PATCH = {
    "coverage": [
        {
            "area": "release",
            "question": "Does the archive release match the registry tally?",
            "priority": "high",
            "decision_relevance": "The tally decides whether the release is complete.",
            "completion_criteria": "Two independent records report the same count.",
            "status": "supported",
            "claim_ids": ["C1", "C2"],
            "gap_impact": None,
        }
    ],
    "synthesis": {
        "central_judgment_claim_ids": ["C1"],
        "counterevidence_claim_ids": [],
        "adversarial_tests": [
            {
                "hypothesis": "The registry tally differs from the archive release.",
                "test": "Compare both published counts for the same month.",
                "claim_ids": ["C1", "C2"],
                "outcome": "rejected",
                "result": "Both records report the same count.",
                "effect_on_conclusion": "The release claim stands.",
            }
        ],
        "implications": [
            {
                "statement": "The release can be cited as complete for March 2026.",
                "claim_ids": ["C1"],
                "for_whom": "Archive researchers",
                "timing": "Immediately",
            }
        ],
        "decisions_or_takeaways": [
            {
                "statement": "Cite the registry tally alongside the release count.",
                "rationale_claim_ids": ["C1", "C2"],
                "tradeoff": "Two citations per sentence cost space.",
                "success_signal": "Readers can reconcile both counts.",
                "failure_signal": "Only one record is cited for the count.",
            }
        ],
        "scenarios": [],
        "limitations": ["Only two records were available within the time budget."],
        "research_stop_reason": "Both records agree and the budget is spent.",
    },
}


REMEDY_SAMPLE = {
    "source_id": "S1",
    "claim_id": "C1",
    "paragraph": 3,
    "kind": "content",
    "keyword": "1918",
    "field": "living_status",
    "file": "claims/batch.json",
    "url": "https://example.org/study",
}

CLOSED_IMPERATIVES = (
    re.compile(r"^set field \S+ in \S+$"),
    re.compile(r"^set field \S+ in \S+, then alx claim add \S+$"),
    re.compile(r"^alx fetch --id S\d+ --refresh, then alx claim add \S+$"),
    re.compile(r"^extend the quote in \S+$"),
    re.compile(r"^extend the report body in report\.md$"),
    re.compile(r"^delete paragraph \d+ of report\.md$"),
    re.compile(r"^\(edit prose; waivable by alx issue --deliver\)$"),
    re.compile(r"^add the source link to paragraph \d+ of report\.md$"),
    re.compile(
        r"^add the source link to the paragraph that states claim C\d+ "
        r"in report\.md$"
    ),
)


def responses(page=PAGE):
    return {
        "example.org": (200, {"content-type": "text/html"}, page.encode("utf-8")),
        "registry.example.net": (
            200,
            {"content-type": "text/html"},
            SECOND_PAGE.encode("utf-8"),
        ),
    }


class AlxTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.dir = self.root / "workspace"

    def run_alx(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = alx.main([str(item) for item in argv])
        return code, out.getvalue()

    def run_in(self, *argv):
        return self.run_alx("--dir", self.dir, *argv)

    def write_json(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def init(self, *extra):
        subject = self.root / "subject.txt"
        subject.write_text(
            "Ledger Study\nDoes the archive release match the registry?\n",
            encoding="utf-8",
        )
        return self.run_alx(
            "init",
            self.dir,
            "--lang",
            "en",
            "--subject",
            subject,
            "--archetype",
            "artifact",
            *extra,
        )

    def fetch(self, *urls, page=PAGE):
        with mock_production_transport(responses(page)):
            return self.run_in("fetch", *urls)

    def bootstrap(self):
        """init + two fetched sources + two probed claims + a drafted report."""
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        for source_id in ("S1", "S2"):
            self.run_in(
                "source", "set", source_id, "--provenance", "primary_independent"
            )
        patch = self.write_json("coverage.json", COVERAGE_PATCH)
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.draft_report()

    def draft_report(self):
        ledger = json.loads((self.dir / "ledger.json").read_text(encoding="utf-8"))
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        date_line = alx.report_contract.localized_date("en", None)
        text = (
            "# Ledger Study\n\n"
            "> Whether the archive release matches the registry tally.\n"
            f"> {date_line}\n\n"
            "## Findings\n\n"
            "The archive released 1,204 documents in March 2026, a release "
            f"[recorded in the study]({first}) that the registry confirmed.\n\n"
            "The registry logged 1,204 documents in March 2026, "
            f"as the [registry note]({second}) records for the same period.\n\n"
            "The reading room keeps 「原始日記」 under restricted access, "
            "so the counts above are the only public record.\n\n"
            "## Sources\n\n"
            f"- [Ledger Study]({first})\n"
            f"- [Registry Note]({second})\n"
        )
        (self.dir / "report.md").write_text(text, encoding="utf-8")
        return text

    def ledger(self):
        return json.loads((self.dir / "ledger.json").read_text(encoding="utf-8"))

    def state(self):
        return json.loads(
            (self.dir / ".alx" / "state.json").read_text(encoding="utf-8")
        )

    def set_remaining(self, minutes):
        state = self.state()
        now = datetime.now(timezone.utc)
        state["deadline"] = (now + timedelta(minutes=minutes)).isoformat()
        (self.dir / ".alx" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )


class InitTests(AlxTestCase):
    def test_init_creates_layout_state_and_footer(self):
        code, out = self.init("--budget-minutes", "60")
        self.assertEqual(0, code, out)
        for relative in (
            "report.md",
            "ledger.json",
            "sources",
            "claims",
            "reviews",
            "receipts",
            ".alx/state.json",
            "worklog.md",
        ):
            self.assertTrue((self.dir / relative).exists(), relative)
        state = self.state()
        self.assertEqual("en", state["lang"])
        self.assertEqual("artifact", state["archetype"])
        self.assertIn("start_time", state)
        self.assertIn("deadline", state)
        self.assertIn("counters", state)
        self.assertIn("reviews", state)
        self.assertIn("last_check", state)
        self.assertRegex(out.strip().splitlines()[-1], r"^elapsed \d+ min, remaining \d+ min$")
        self.assertIn("alx fetch", out)
        worklog = (self.dir / "worklog.md").read_text(encoding="utf-8")
        self.assertIn("init", worklog)

    def test_report_skeleton_date_line_matches_ledger_report_date(self):
        self.init()
        ledger = self.ledger()
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        expected = alx.report_contract.localized_date(
            "en", alx.date.fromisoformat(ledger["report_date"])
        )
        self.assertIn(expected, text)
        self.assertTrue(text.startswith("# "))
        self.assertIn("\n> ", text)

    def test_init_refuses_existing_ledger_without_force(self):
        self.init()
        (self.dir / "ledger.json").write_text('{"marker": 1}', encoding="utf-8")
        code, out = self.init()
        self.assertEqual(1, code)
        self.assertIn("--force", out)
        self.assertEqual({"marker": 1}, self.ledger())
        code, out = self.init("--force")
        self.assertEqual(0, code, out)
        self.assertEqual(4, self.ledger()["schema_version"])

    def test_person_archetype_requires_subject_status(self):
        subject = self.root / "subject.txt"
        subject.write_text("Someone Notable\n", encoding="utf-8")
        code, out = self.run_alx(
            "init",
            self.dir,
            "--lang",
            "en",
            "--subject",
            subject,
            "--archetype",
            "person",
        )
        self.assertEqual(1, code)
        self.assertIn("--subject-status", out)
        code, out = self.run_alx(
            "init",
            self.dir,
            "--lang",
            "en",
            "--subject",
            subject,
            "--archetype",
            "person",
            "--subject-status",
            "unknown",
        )
        self.assertEqual(0, code, out)
        person = self.ledger()["people"][0]
        self.assertEqual("unknown", person["living_status"])
        self.assertEqual("primary_subject", person["relationship"])


class FetchTests(AlxTestCase):
    def test_fetch_adds_unverified_source_and_cache(self):
        self.init()
        code, out = self.fetch("https://example.org/study")
        self.assertEqual(0, code, out)
        self.assertRegex(out, r'S1 OK \d+ chars \S+ "Ledger Study" https://example\.org/study')
        source = self.ledger()["sources"][0]
        self.assertEqual("https://example.org/study", source["url"])
        self.assertEqual("unverified", source["provenance"])
        self.assertEqual("news_report", source["evidence_type"])
        self.assertEqual(["independent_analysis"], source["roles"])
        self.assertEqual("none", source["accountability_basis"])
        self.assertEqual("example.org", source["source_family"])
        text = (self.dir / "sources" / "S1.txt").read_text(encoding="utf-8")
        self.assertIn("1,204 documents", text)
        meta = json.loads(
            (self.dir / "sources" / "S1.meta.json").read_text(encoding="utf-8")
        )
        for key in (
            "url",
            "final_url",
            "aliases",
            "http_status",
            "charset",
            "title",
            "published",
            "fetched_at",
            "text_sha256",
        ):
            self.assertIn(key, meta)

    def test_http_url_is_promoted_to_https_and_kept_as_alias(self):
        self.init()
        code, out = self.fetch("http://example.org/study")
        self.assertEqual(0, code, out)
        source = self.ledger()["sources"][0]
        self.assertEqual("https://example.org/study", source["url"])
        self.assertIn("http://example.org/study", source["aliases"])

    def test_non_http_scheme_is_rejected(self):
        self.init()
        code, out = self.run_in("fetch", "ftp://example.org/study")
        self.assertEqual(1, code)
        self.assertIn("not added", out)
        self.assertEqual([], self.ledger()["sources"])

    def test_duplicate_url_prints_existing_id(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.fetch("https://example.org/study")
        self.assertEqual(0, code, out)
        self.assertIn("S1", out)
        self.assertEqual(1, len(self.ledger()["sources"]))

    def test_refresh_reports_text_change_and_claims_to_reprobe(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json("claims.json", [CLAIM_ONE])
        self.run_in("claim", "add", batch)
        changed = PAGE.replace("1,204 documents", "1,205 documents")
        with mock_production_transport(responses(changed)):
            code, out = self.run_in("fetch", "--id", "S1", "--refresh")
        self.assertEqual(0, code, out)
        self.assertIn("S1 text changed; claims C1 need re-probe", out)

    def test_source_set_edits_classification_only(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in(
            "source", "set", "S1", "--provenance", "primary_independent"
        )
        self.assertEqual(0, code, out)
        source = self.ledger()["sources"][0]
        self.assertEqual("primary_independent", source["provenance"])
        self.assertEqual("https://example.org/study", source["url"])


    def test_fetch_passes_cache_dir_refresh_and_deadline_to_t1(self):
        self.init()
        seen = []
        real = alx.source_fidelity.fetch_document

        def spy(url, **kwargs):
            seen.append(kwargs)
            return real(url, **kwargs)

        with mock.patch.object(
            alx.source_fidelity, "fetch_document", side_effect=spy
        ), mock_production_transport(responses()):
            code, out = self.run_in("fetch", "https://example.org/study")
            self.assertEqual(0, code, out)
            code, out = self.run_in("fetch", "--id", "S1", "--refresh")
            self.assertEqual(0, code, out)
        workspace = alx.Workspace(self.dir)
        deadline = datetime.fromisoformat(self.state()["deadline"]).timestamp()
        self.assertEqual([False, True], [call["refresh"] for call in seen])
        for call in seen:
            self.assertEqual(workspace.sources, call["cache_dir"])
            self.assertEqual(alx.FETCH_TIMEOUT_SECONDS, call["timeout"])
            self.assertAlmostEqual(deadline, call["deadline"], places=3)

    def test_fetch_batch_stops_near_the_deadline(self):
        self.init()
        self.set_remaining(10)
        code, out = self.fetch("https://example.org/study")
        self.assertEqual(0, code, out)
        self.assertIn("fetch batch stopped", out)
        self.assertEqual([], self.ledger()["sources"])


class LanguageTests(AlxTestCase):
    def test_verification_note_templates_per_language(self):
        for lang in ("en", "zh-CN", "zh-HK"):
            note = alx._verification_note(lang, ["S3 unreachable"])
            self.assertTrue(note.startswith(alx.VERIFICATION_NOTE_PREFIX[lang]), note)
            self.assertIn("S3 unreachable", note)

    def test_chinese_init_writes_a_localized_skeleton(self):
        subject = self.root / "subject.txt"
        subject.write_text("蒋介石日记\n日记如何改变史料判断？\n", encoding="utf-8")
        code, out = self.run_alx(
            "init",
            self.dir,
            "--lang",
            "zh-CN",
            "--subject",
            subject,
            "--archetype",
            "artifact",
        )
        self.assertEqual(0, code, out)
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("## 资料来源", text)
        ledger = self.ledger()
        self.assertIn(
            alx.report_contract.localized_date(
                "zh-CN", alx.date.fromisoformat(ledger["report_date"])
            ),
            text,
        )
        self.assertEqual("zh-CN", ledger["brief"]["report_language"])


class FindShowTests(AlxTestCase):
    def test_find_prints_numbered_sentence_windows(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("find", "S1", "1,204")
        self.assertEqual(0, code, out)
        self.assertIn("1. ", out)
        self.assertIn("1,204 documents", out)
        self.assertNotIn("…", out)
        for line in out.splitlines():
            self.assertLessEqual(len(line), 310, line)

    def test_show_prints_cache_window(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("show", "S1", "--start", "0", "--end", "60")
        self.assertEqual(0, code, out)
        # T1 stores the case-folded visible text, so the window is folded too.
        self.assertIn("ledger study", out)


class ClaimTests(AlxTestCase):
    def test_claim_add_round_trip_without_invented_fields(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        claims = {claim["claim_id"]: claim for claim in self.ledger()["claims"]}
        self.assertEqual({"C1", "C2"}, set(claims))
        claim = claims["C1"]
        self.assertEqual(["S1"], claim["source_ids"])
        self.assertTrue(claim["include_in_report"])
        self.assertEqual([], claim["report_excerpts"])
        self.assertIn(claim["triangulation"]["status"], {"met", "limited"})
        meta = json.loads(
            (self.dir / "sources" / "S1.meta.json").read_text(encoding="utf-8")
        )
        self.assertEqual(meta["fetched_at"][:10], claim["verified_at"])

    def test_missing_claim_id_and_short_segment_are_reported_together(self):
        self.init()
        self.fetch("https://example.org/study")
        bad = dict(CLAIM_ONE)
        bad.pop("claim_id")
        short = {
            "claim_id": "C9",
            "claim": "The archive released documents.",
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S1", "extract_or_location": "The archive"}
            ],
        }
        batch = self.write_json("claims.json", [bad, short])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code)
        self.assertIn("add claim_id", out)
        self.assertIn("extend the quote", out)
        self.assertEqual([], self.ledger()["claims"])

    def test_fabricated_extract_fails_the_offline_probe(self):
        self.init()
        self.fetch("https://example.org/study")
        invented = dict(CLAIM_ONE)
        invented["source_evidence"] = [
            {
                "source_id": "S1",
                "extract_or_location": (
                    "The archive released 1,204 documents in March 2026 "
                    "after a court ordered their immediate publication."
                ),
            }
        ]
        batch = self.write_json("claims.json", [invented])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code)
        self.assertIn("C1 FAIL", out)
        self.assertEqual([], self.ledger()["claims"])

    def test_person_claims_refused_while_status_unknown(self):
        subject = self.root / "subject.txt"
        subject.write_text("Someone Notable\n", encoding="utf-8")
        self.run_alx(
            "init",
            self.dir,
            "--lang",
            "en",
            "--subject",
            subject,
            "--archetype",
            "person",
            "--subject-status",
            "unknown",
        )
        self.fetch("https://example.org/study")
        claim = dict(CLAIM_ONE)
        claim["person_ids"] = ["P1"]
        claim["person_claim_role"] = "neutral"
        batch = self.write_json("claims.json", [claim])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code)
        self.assertIn("living_status", out)
        self.assertIn("alx ledger merge", out)
        self.assertEqual([], self.ledger()["claims"])

    def test_claim_drop_plan_then_apply_cascade(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        supporter = {
            "claim_id": "C3",
            "claim": "The registry tally corroborates the archive release.",
            "kind": "analysis",
            "importance": "supporting",
            "reasoning": "Both records report the same count for the same month.",
            "source_evidence": [
                {
                    "source_id": "S1",
                    "extract_or_location": (
                        "The archive released 1,204 documents in March 2026, "
                        "and the registry confirmed the count."
                    ),
                }
            ],
            "supports": ["C1"],
        }
        batch = self.write_json("supporter.json", [supporter])
        self.run_in("claim", "add", batch)
        code, plan = self.run_in("claim", "drop", "C1")
        self.assertEqual(0, code, plan)
        self.assertIn("C1", plan)
        self.assertIn("C3", plan)
        report_before = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("1,204 documents", report_before)
        code, out = self.run_in("claim", "drop", "C1", "--apply")
        self.assertEqual(0, code, out)
        ledger = self.ledger()
        excluded = {claim["claim_id"] for claim in ledger["excluded_claims"]}
        self.assertIn("C1", excluded)
        self.assertNotIn("C1", {claim["claim_id"] for claim in ledger["claims"]})
        for claim in ledger["excluded_claims"]:
            self.assertIn("reason", claim)
            self.assertIn("dropped_at", claim)
        report_after = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "The archive released 1,204 documents in March 2026, a release",
            report_after,
        )
        code, out = self.run_in("check")
        self.assertNotIn("leftover-prose", out)

    def test_surviving_supports_to_excluded_claim_is_hard(self):
        self.bootstrap()
        ledger = self.ledger()
        ledger["claims"][1]["supports"] = ["C1"]
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        self.run_in("claim", "drop", "C1", "--apply")
        surviving = {
            claim["claim_id"]: claim for claim in self.ledger()["claims"]
        }
        self.assertIn("C2", surviving)
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("C1", out)
        self.assertIn("excluded", out)

    def test_claim_add_upserts_by_claim_id(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json("claims.json", [CLAIM_ONE])
        self.assertEqual(0, self.run_in("claim", "add", batch)[0])
        corrected = dict(CLAIM_ONE)
        corrected["claim"] = "Retention rose to 88 percent after the second round."
        corrected["source_evidence"] = [
            {
                "source_id": "S1",
                "extract_or_location": (
                    "Retention rose to 88 percent after the second review round, "
                    "the registry reported."
                ),
            }
        ]
        batch = self.write_json("corrected.json", [corrected])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C1 replaced", out)
        claims = self.ledger()["claims"]
        self.assertEqual(1, len(claims))
        self.assertEqual(corrected["claim"], claims[0]["claim"])

    def test_one_claim_reports_every_family_without_short_circuit(self):
        self.init()
        self.fetch("https://example.org/study")
        broken = {
            "claim_id": "C5",
            "claim": "The court ordered the immediate publication of the archive.",
            "kind": "analysis",
            "importance": "supporting",
            "source_evidence": [
                {
                    "source_id": "S1",
                    "extract_or_location": (
                        "The archive released 1,204 documents in March 2026 "
                        "after a court ordered their immediate publication."
                    ),
                }
            ],
        }
        batch = self.write_json("broken.json", [broken])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code)
        self.assertIn("ledger/claim-input", out)
        self.assertIn("reasoning", out)
        self.assertIn("fidelity/mismatch", out)
        self.assertEqual([], self.ledger()["claims"])

    def test_drop_cascade_drops_both_claims_mapped_to_one_paragraph(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        co_mapped = {
            "claim_id": "C4",
            "claim": "Retention rose to 88 percent after the second review round.",
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {
                    "source_id": "S1",
                    "extract_or_location": (
                        "Retention rose to 88 percent after the second review round, "
                        "the registry reported."
                    ),
                }
            ],
        }
        batch = self.write_json("co.json", [co_mapped])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        code, plan = self.run_in("claim", "drop", "C1")
        self.assertEqual(0, code, plan)
        self.assertIn("Also dropped (same paragraph): C4", plan)
        code, out = self.run_in("claim", "drop", "C1", "--apply")
        self.assertEqual(0, code, out)
        excluded = {claim["claim_id"] for claim in self.ledger()["excluded_claims"]}
        self.assertEqual({"C1", "C4"}, excluded)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("a release [recorded in the study]", report)

    def test_claim_bind_sets_the_paragraph_mapping(self):
        self.bootstrap()
        code, out = self.run_in("claim", "bind", "C1", "--paragraph", "1")
        self.assertEqual(0, code, out)
        self.assertEqual(1, self.state()["bindings"]["C1"])


class LedgerMergeTests(AlxTestCase):
    def test_merge_refuses_claims_and_sources(self):
        self.bootstrap()
        patch = self.write_json("patch.json", {"claims": [{"claim_id": "C7"}]})
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(1, code)
        self.assertIn("sources only via fetch/source set", out)
        self.assertIn("claims only via claim add", out)
        patch = self.write_json("patch.json", {"sources": [{"source_id": "S9"}]})
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(1, code)

    def test_merge_deep_merges_people_and_coverage(self):
        self.bootstrap()
        patch = self.write_json(
            "patch.json",
            {
                "people": [
                    {
                        "person_id": "P1",
                        "name": "Someone Notable",
                        "aliases": [],
                        "living_status": "deceased",
                        "public_role": "public",
                        "relationship": "adjacent",
                    }
                ]
            },
        )
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.assertEqual("P1", self.ledger()["people"][0]["person_id"])


class CheckTests(AlxTestCase):
    def test_cache_detached_is_hard_with_refresh_remedy(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("cache-detached", out)
        self.assertIn("alx fetch --id S1 --refresh", out)

    def test_cache_missing_is_hard(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.meta.json").unlink()
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("cache", out)

    def test_link_outside_the_ledger_is_hard(self):
        self.bootstrap()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(
            "## Sources", "See [another page](https://elsewhere.example/x).\n\n## Sources"
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("elsewhere.example", out)

    def test_control_characters_and_quotation_loss_after_snapshot(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        damaged = report.replace("「原始日記」", "\x01")
        (self.dir / "report.md").write_text(damaged, encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("quotation-lost", out)
        self.assertIn("control-chars", out)
        self.assertIn("alx snapshot --restore", out)
        code, out = self.run_in("snapshot", "--restore")
        self.assertEqual(0, code, out)
        self.assertIn(
            "「原始日記」", (self.dir / "report.md").read_text(encoding="utf-8")
        )

    def test_fix_writes_excerpts_and_regenerates_sources(self):
        self.bootstrap()
        _code, out = self.run_in("check", "--fix")
        claim = next(
            claim for claim in self.ledger()["claims"] if claim["claim_id"] == "C1"
        )
        self.assertTrue(claim["report_excerpts"])
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        source = self.ledger()["sources"][0]
        self.assertIn(f"[{source['title']}]({source['url']})", report)
        self.assertIn("C1=1", out)
        self.assertIn("C2=2", out)

    def test_unbound_excerpts_are_hard_and_fix_writes_them(self):
        """Ruling R3: the schema clause is gone; §6.7(c) reports the gap."""
        self.bootstrap()
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("binding/excerpt-missing", out)
        self.assertNotIn("[ledger/schema]", out)
        _code, out = self.run_in("check", "--fix")
        self.assertNotIn("binding/excerpt-missing", out)
        claim = next(
            claim for claim in self.ledger()["claims"] if claim["claim_id"] == "C1"
        )
        self.assertTrue(claim["report_excerpts"])

    def test_check_prints_grouped_output_and_status_line(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertRegex(out, r"=== HARD \d+ \(blocks issue\) ===")
        self.assertRegex(out, r"=== STATUS: check #1, elapsed \d+ min, remaining \d+ min")
        self.assertRegex(out.strip().splitlines()[-1], r"^elapsed \d+ min, remaining \d+ min$")
        self.assertIn("last_check", json.dumps(self.state()))

    def test_fix_normalizes_the_date_line_whitespace(self):
        self.bootstrap()
        expected = alx.report_contract.localized_date("en", None)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        damaged = report.replace(f"> {expected}", f">   {expected.replace(' ', '  ')}")
        (self.dir / "report.md").write_text(damaged, encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertIn("integrity/date-line", out)
        _code, out = self.run_in("check", "--fix")
        self.assertNotIn("integrity/date-line", out)
        self.assertIn(
            f"> {expected}", (self.dir / "report.md").read_text(encoding="utf-8")
        )

    def test_missing_rewild_evaluator_is_a_class_a_finding(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        with mock.patch.object(alx.rewild_gate, "run_check", None, create=True):
            _code, out = self.run_in("check")
        self.assertIn("rewild evaluator unavailable", out)

    def test_degradation_instruction_printed_near_the_deadline(self):
        self.bootstrap()
        self.set_remaining(10)
        _code, out = self.run_in("status")
        self.assertIn("alx issue --deliver", out)


class ReviewTests(AlxTestCase):
    def finish_reviews(self):
        for kind in ("rewild", "content"):
            code, out = self.run_in("review", "start", kind)
            self.assertEqual(0, code, out)
            self.fill_note(kind)
            code, out = self.run_in("review", "finish", kind)
            self.assertEqual(0, code, out)

    def fill_note(self, kind):
        path = self.dir / "reviews" / f"{kind}.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["status"] = "completed"
        if kind == "rewild":
            note["fidelity_checks"] = {
                name: True for name in alx.rewild_gate.REQUIRED_FIDELITY_CHECKS
            }
            note["findings"] = []
        else:
            note["scores"] = {
                name: {
                    "score": 5,
                    "rationale": "The report answers the question with cited evidence.",
                }
                for name in alx.CONTENT_SCORE_KEYS
            }
            note["checks"] = {name: True for name in alx.CONTENT_CHECK_KEYS}
            note["section_reviews"] = [
                {
                    "section_heading": "Findings",
                    "purpose": "State what the archive released and when it did so.",
                    "new_value": "It ties the release count to the registry tally.",
                    "evidence_or_reasoning": "Both records report the same count.",
                    "limitation_or_tradeoff": "Only two records were available here.",
                    "contribution_to_governing_question": (
                        "It answers whether the release matches the registry."
                    ),
                    "disposition": "keep",
                }
            ]
            note["findings"] = []
            note["visual_assets"] = []
            note["evidence_limitations"] = []
            note["completion_note"] = "Reviewed against the ledger."
            mapping = alx.paragraph_mapping(
                alx.Workspace(self.dir),
                self.state(),
                self.ledger(),
                (self.dir / "report.md").read_text(encoding="utf-8"),
            )[0]
            note["claim_support"] = [
                {
                    "claim_id": claim_id,
                    "paragraph": paragraph,
                    "disposition": "supported",
                    "note": "The paragraph cites the claim's own source.",
                }
                for claim_id, paragraph in sorted(mapping.items())
            ]
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")

    def test_start_copies_report_and_binds_hashes(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        copy = self.dir / ".alx" / "reviews" / "content" / "1" / "report.md"
        self.assertTrue(copy.exists())
        self.assertTrue(
            (self.dir / ".alx" / "reviews" / "content" / "1" / "ledger.json").exists()
        )
        note = json.loads(
            (self.dir / "reviews" / "content.json").read_text(encoding="utf-8")
        )
        self.assertEqual(alx.file_sha256(self.dir / "report.md"), note["report_sha256"])
        self.assertEqual([], note["findings"])

    def test_finish_refuses_an_incomplete_note(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(1, code)
        self.assertIn("scores", out)

    def test_content_note_needs_a_disposition_per_mapped_claim(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        self.fill_note("content")
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["claim_support"] = [
            dict(entry, disposition="") for entry in note["claim_support"]
        ]
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(1, code)
        self.assertIn("claim_support[C1].disposition", out)

    def test_mechanical_delta_keeps_the_review_fresh(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.finish_reviews()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        ledger = self.ledger()
        url = ledger["sources"][0]["url"]
        report = report.replace(f"[recorded in the study]({url})", "recorded in the study")
        report = report.replace("## Sources\n", "## Sources\n\n")
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertNotIn("re-review required", out)

    def test_sentence_change_requires_a_review_iteration(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.finish_reviews()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(
            "as the [registry note]", "and independently, as the [registry note]"
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(1, code)
        self.assertIn("re-review required", out)
        self.assertIn("alx review start content --iter", out)
        code, out = self.run_in("review", "start", "content", "--iter")
        self.assertEqual(0, code, out)
        self.assertTrue(
            (self.dir / ".alx" / "reviews" / "content" / "2" / "report.md").exists()
        )
        self.fill_note("content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        code, out = self.run_in("check")
        self.assertNotIn("re-review required: content", out)

    def test_ledger_claim_change_requires_content_iteration(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.finish_reviews()
        ledger = self.ledger()
        ledger["claims"][0]["claim"] = "The archive released 1,204 documents in March."
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, out = self.run_in("check")
        self.assertIn("re-review required", out)

    def test_restore_reverts_report_and_ledger(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.finish_reviews()
        reviewed = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            reviewed + "\nAn unreviewed paragraph.\n", encoding="utf-8"
        )
        code, out = self.run_in("review", "restore", "content")
        self.assertEqual(0, code, out)
        self.assertEqual(
            reviewed, (self.dir / "report.md").read_text(encoding="utf-8")
        )


class IssueTests(AlxTestCase):
    def prepared(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        reviews.dir = self.dir
        reviews.root = self.root
        reviews.run_alx = self.run_alx
        reviews.run_in = self.run_in
        reviews.finish_reviews()

    def stub_gates(self, stack, *, online=None, rewild=True):
        calls = {"online": 0, "rewild": 0, "content": 0, "network": 0}

        def bound(payload):
            """Receipts carry the hashes validate_report --fast re-checks."""
            payload = dict(payload)
            payload["report_sha256"] = alx.file_sha256(self.dir / "report.md")
            payload["ledger_sha256"] = alx.file_sha256(self.dir / "ledger.json")
            return json.dumps(payload)

        real_check = alx.source_fidelity.check_source_fidelity

        def fake_live_check(ledger, **kwargs):
            """`issue` step 2 runs the live pass itself and reuses its result."""
            if not kwargs.get("online"):
                return real_check(ledger, **kwargs)
            calls["online"] += 1
            return online or {
                "status": "passed",
                "checks": [],
                "refreshed_source_ids": [],
                "disclosure_required": [],
            }

        def fake_online(ledger_path, receipt_path, **kwargs):
            Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
            Path(receipt_path).write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "policy": "weighted-source-evidence-v2",
                        "ledger_sha256": alx.file_sha256(self.dir / "ledger.json"),
                    }
                ),
                encoding="utf-8",
            )
            return online or {
                "status": "passed",
                "checks": [],
                "refreshed_source_ids": [],
                "disclosure_required": [],
            }

        def fake_rewild(*args, **kwargs):
            calls["rewild"] += 1
            Path(kwargs["receipt_path"]).write_text(
                bound({"status": "passed"}), encoding="utf-8"
            )
            return []

        def fake_content(report_path, ledger_path, review_note_path, receipt_path, **kwargs):
            calls["content"] += 1
            Path(receipt_path).write_text(bound({"status": "passed"}), encoding="utf-8")
            return []

        def fake_fetch(*args, **kwargs):
            calls["network"] += 1
            raise AssertionError("render must not reach the network")

        stack.enter_context(
            mock.patch.object(
                alx.source_fidelity,
                "check_source_fidelity",
                side_effect=fake_live_check,
            )
        )
        stack.enter_context(
            mock.patch.object(
                alx.source_fidelity,
                "issue_source_fidelity_receipt",
                side_effect=fake_online,
            )
        )
        if rewild:
            stack.enter_context(
                mock.patch.object(alx.rewild_gate, "run_gate", side_effect=fake_rewild)
            )
        stack.enter_context(
            mock.patch.object(
                alx.content_gate, "run_content_gate", side_effect=fake_content
            )
        )
        stack.enter_context(
            mock.patch.object(
                alx.source_fidelity, "default_fetcher", side_effect=fake_fetch
            )
        )
        return calls

    def test_issue_writes_receipts_and_verification_note(self):
        from contextlib import ExitStack

        self.prepared()
        with ExitStack() as stack:
            calls = self.stub_gates(
                stack,
                online={
                    "status": "passed",
                    "checks": [],
                    "refreshed_source_ids": [],
                    "disclosure_required": ["C1"],
                },
            )
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertEqual(1, calls["online"])
        receipt = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            alx.file_sha256(self.dir / "report.md"), receipt["report_sha256"]
        )
        self.assertIn("ledger_sha256", receipt)
        self.assertIn("receipts", receipt)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(alx.VERIFICATION_NOTE_PREFIX["en"], report)
        self.assertLess(
            report.index(alx.VERIFICATION_NOTE_PREFIX["en"]), report.index("## Sources")
        )

    def test_length_floor_is_class_a_and_only_deliver_issues(self):
        """Spec §6.10: `rewild/length` is Class A, and `rewild_gate` owns the class."""
        from contextlib import ExitStack

        self.prepared()
        _code, out = self.run_in("check")
        self.assertIn("[rewild/length]", out)
        # Class A: `rewild_gate` set it, so `issue` gets past step 1.
        self.assertEqual(0, self.state()["last_check"]["class_f"])
        with ExitStack() as stack:
            self.stub_gates(stack, rewild=False)
            code, out = self.run_in("issue")
            self.assertEqual(1, code, out)
            self.assertFalse((self.dir / "receipts" / "issue.json").exists())
            code, out = self.run_in("issue", "--deliver")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any("minimum is" in note for note in notes["notes"]), notes)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_issue_stamps_the_note_hashes_before_running_the_gates(self):
        """Spec §6.8/§6.9 step 4: stamp, then gate; `check` never judges hashes."""
        from contextlib import ExitStack

        self.prepared()
        # A mechanical delta (spec §6.8) moves the report off the reviewed hash
        # without making either review stale.
        code, out = self.run_in("claim", "drop", "C2", "--apply")
        self.assertEqual(0, code, out)
        for kind in ("rewild", "content"):
            note = json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(
                alx.file_sha256(self.dir / "report.md"), note.get("report_sha256")
            )
        # `check` section (e) passes review_note_path=None, so the hashes the
        # note still carries are never a finding there.
        _code, out = self.run_in("check")
        self.assertNotIn("report_sha256", out)
        self.assertNotIn("[review/rewild]", out)
        with ExitStack() as stack:
            self.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        for kind in ("rewild", "content"):
            note = json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                alx.file_sha256(self.dir / "report.md"), note["report_sha256"]
            )

    def test_issue_refuses_class_f_without_deliver(self):
        from contextlib import ExitStack

        self.prepared()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        with ExitStack() as stack:
            calls = self.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code)
        self.assertIn("cache-detached", out)
        self.assertEqual(0, calls["online"])
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())

    def test_deliver_never_bypasses_class_f(self):
        from contextlib import ExitStack

        self.prepared()
        self.set_remaining(10)
        ledger = self.ledger()
        for claim in ledger["claims"]:
            if claim["claim_id"] == "C2":
                claim["source_evidence"][0]["extract_or_location"] = (
                    "The registry logged 4,000 documents in March 2026 "
                    "under a sealed court order."
                )
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace("「原始日記」", "records"), encoding="utf-8"
        )
        with ExitStack() as stack:
            self.stub_gates(stack)
            code, out = self.run_in("issue", "--deliver")
        final = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("「原始日記」", final)
        self.assertNotIn("as the [registry note]", final)
        surviving = {claim["claim_id"] for claim in self.ledger()["claims"]}
        self.assertNotIn("C2", surviving)
        self.assertIn("C2", {c["claim_id"] for c in self.ledger()["excluded_claims"]})
        # Spec §6.8: the drop and its paragraph deletion are mechanical, so a
        # review finished before the drop stays fresh and delivery completes.
        self.assertEqual(0, code, out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists(), out)

    def test_deliver_records_class_a_failures_in_delivery_notes(self):
        from contextlib import ExitStack

        self.prepared()

        def failing_online(*args, **kwargs):
            raise ValueError("network unavailable")

        with ExitStack() as stack:
            self.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity,
                    "issue_source_fidelity_receipt",
                    side_effect=failing_online,
                )
            )
            code, out = self.run_in("issue", "--deliver")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(notes["notes"])
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_issue_without_deliver_aborts_on_class_a_failure(self):
        from contextlib import ExitStack

        self.prepared()

        def failing_online(*args, **kwargs):
            raise ValueError("network unavailable")

        with ExitStack() as stack:
            self.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity,
                    "issue_source_fidelity_receipt",
                    side_effect=failing_online,
                )
            )
            code, _out = self.run_in("issue")
        self.assertEqual(1, code)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())


class RenderTests(AlxTestCase):
    def test_render_refuses_without_a_matching_issue_receipt(self):
        self.bootstrap()
        code, out = self.run_in("render")
        self.assertEqual(1, code)
        self.assertIn("alx issue", out)
        (self.dir / "receipts").mkdir(exist_ok=True)
        (self.dir / "receipts" / "issue.json").write_text(
            json.dumps({"report_sha256": "0" * 64, "ledger_sha256": "0" * 64}),
            encoding="utf-8",
        )
        code, out = self.run_in("render")
        self.assertEqual(1, code)
        self.assertIn("alx issue", out)

    def test_issue_then_render_runs_no_gate_and_no_network(self):
        from contextlib import ExitStack

        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        issue_tests.root = self.root
        issue_tests.dir = self.dir
        issue_tests.run_alx = self.run_alx
        issue_tests.run_in = self.run_in
        issue_tests.write_json = self.write_json
        issue_tests.init = self.init
        issue_tests.fetch = self.fetch
        issue_tests.bootstrap = self.bootstrap
        issue_tests.draft_report = self.draft_report
        issue_tests.ledger = self.ledger
        issue_tests.state = self.state
        issue_tests.prepared()
        with ExitStack() as stack:
            calls = issue_tests.stub_gates(stack)
            code, out = self.run_in("issue")
            self.assertEqual(0, code, out)
            rendered = []

            def fake_render_pdf(input_path, output_path, **kwargs):
                rendered.append((Path(output_path).name, kwargs.get("template")))
                Path(output_path).write_bytes(b"%PDF-1.7\n")
                return Path(output_path)

            def fake_render_pages(pdf_path, output_dir, **kwargs):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                page = Path(output_dir) / "page-001.png"
                page.write_bytes(b"\x89PNG")
                return [page]

            from scripts import md_to_pdf, render_pdf_pages

            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=fake_render_pages
                )
            )
            before = dict(calls)
            code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        self.assertEqual(2, len(rendered))
        self.assertEqual(before["rewild"], calls["rewild"])
        self.assertEqual(before["content"], calls["content"])
        self.assertEqual(before["online"], calls["online"])
        self.assertEqual(0, calls["network"])
        self.assertIn(".pdf", out)


class StatusTests(AlxTestCase):
    def test_status_prints_the_phase_checklist(self):
        self.bootstrap()
        code, out = self.run_in("status")
        self.assertEqual(0, code, out)
        self.assertIn("sources 2", out)
        self.assertIn("claims 2", out)
        self.assertIn("snapshot", out)
        self.assertIn("Next:", out)
        self.assertRegex(out.strip().splitlines()[-1], r"^elapsed \d+ min, remaining \d+ min$")


#: SKILL.md placeholders -> a value `alx`'s parser accepts (spec D14).
SKILL_PLACEHOLDERS = {
    '"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/alx.py"': "",
    '"$WORK/claims/C1.json"': "claims/C1.json",
    '"$REPORT_LANG"': "en",
    '"$SUBJECT_FILE"': "subject.md",
    '"$PATCH"': "patch.json",
    '"$WORK"': "DIR",
    "URL": "https://example.org/study",
    "KEYWORD": "1918",
}


class SkillRunbookTests(unittest.TestCase):
    def test_every_alx_command_line_in_skill_md_parses(self):
        """Spec D14: every printed command is one `alx`'s own parser accepts."""
        parser = alx.build_parser()
        text = (
            Path(alx.__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")
        lines = [
            line.strip().strip("`")
            for line in text.splitlines()
            if "scripts/alx.py" in line
        ]
        self.assertGreaterEqual(len(lines), 10, "SKILL.md lost its command lines")
        for line in lines:
            command = line
            for placeholder, value in SKILL_PLACEHOLDERS.items():
                command = command.replace(placeholder, value)
            with self.subTest(command=line):
                self.assertNotIn("$", command)
                parser.parse_args(shlex.split(command))

    def test_step_7_sends_the_reviewer_to_the_printed_skeleton(self):
        """Item 5: the note format is printed, never read out of the repo."""
        text = (
            Path(alx.__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertIn(
            "skeleton lists every field; fill only those; never read "
            "scripts/ or references/*.schema.json",
            text,
        )


class CheckOutputTests(AlxTestCase):
    """Spec §6.7/§6.10: the printed line must be true for a weak model."""

    def item(self, **kwargs):
        base = dict(
            family="ledger/quantity",
            severity="hard",
            klass="F",
            ids=["C1", "S1"],
            message="C1: quantity '1916' is not in the extract",
            fix="alx find S1 1916",
            remove="alx claim drop C1 --apply",
        )
        base.update(kwargs)
        return alx.Finding(**base)

    def rendered(self, item):
        return alx.render_grouped(alx.adopt([item]))

    def finding_lines(self, text):
        return [line for line in text.splitlines() if line.startswith("  ")]

    def grouped_block(self, text):
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("=== HARD"))
        end = next(i for i, line in enumerate(lines) if line.startswith("=== STATUS:"))
        return "\n".join(lines[start:end])

    # item 1 --------------------------------------------------------------
    def test_producer_remedies_are_printed_once_and_kept(self):
        rendered = self.rendered(self.item())
        self.assertEqual(1, rendered.count("alx find S1 1916"), rendered)
        self.assertEqual(1, rendered.count("alx claim drop C1 --apply"), rendered)
        self.assertNotIn("alx find S1 C1", rendered)

    def test_a_generic_remedy_is_added_only_when_the_producer_has_none(self):
        rendered = self.rendered(
            self.item(
                family="ledger/reference",
                ids=["C23", "C10", "C23"],
                message="Analysis has circular support: C23 -> C10 -> C23",
                fix="",
                remove="",
            )
        )
        self.assertIn("Fix: set field supports in claims/*.json", rendered)
        self.assertIn("Remove: `alx claim drop C23 --apply`", rendered)
        self.assertNotIn("alx check --fix", rendered)

    def test_an_embedded_remedy_sentence_is_not_printed_twice(self):
        rendered = self.rendered(
            self.item(
                message=(
                    "C1: quantity '1916' is not in the extract. "
                    "Remove: `alx claim drop C1 --apply`."
                )
            )
        )
        self.assertEqual(1, rendered.count("alx claim drop C1 --apply"), rendered)

    def test_the_same_remedy_is_never_both_fix_and_remove(self):
        rendered = self.rendered(
            self.item(
                family="fidelity/quotation-lost",
                ids=[],
                message="Quoted span missing from the report: 「原始日記」",
                fix="alx snapshot --restore",
                remove="alx snapshot --restore",
            )
        )
        self.assertEqual(1, rendered.count("alx snapshot --restore"), rendered)

    def test_https_and_host_conflict_get_the_remedy_that_works(self):
        https = self.rendered(
            self.item(
                family="ledger/https",
                ids=["S5"],
                message="S5: source.url must be https (actual: http://jds.example.cn/a)",
                fix="alx fetch --id S5 --refresh",
                remove="",
            )
        )
        self.assertIn("Fix: alx fetch https://jds.example.cn/a", https)
        self.assertNotIn("--provenance", https)
        conflict = self.rendered(
            self.item(
                family="ledger/host-conflict",
                ids=["S12", "S14"],
                message=(
                    "Sources on host www.example.com declare different "
                    "independence classes without a family_justification"
                ),
                fix="alx source set S12",
                remove="",
            )
        )
        self.assertIn("--family-justification", conflict)
        self.assertNotIn("--provenance", conflict)

    def test_find_is_never_printed_with_a_claim_id_as_the_keyword(self):
        rendered = self.rendered(self.item(fix="", remove=""))
        self.assertNotIn("alx find S1 C1", rendered)
        self.assertIn("alx find S1 1916", rendered)
        bare = self.rendered(
            self.item(ids=["C1", "S1"], message="C1: quantity is uncovered", fix="", remove="")
        )
        self.assertNotIn("alx find", bare)
        self.assertIn("extend the quote in claims/*.json", bare)

    # addendum ------------------------------------------------------------
    def test_a_class_a_finding_never_carries_a_remove_remedy(self):
        for family in ("rewild/length", "rewild/ai-vocabulary", "rewild/style"):
            with self.subTest(family=family):
                rendered = self.rendered(
                    self.item(
                        family=family,
                        klass="A",
                        ids=[],
                        message="the report is below the length floor",
                        fix="",
                        remove="",
                    )
                )
                self.assertNotIn("Remove:", rendered)
                self.assertNotIn("alx snapshot --restore", rendered)
                self.assertIn(
                    "Fix: (edit prose; waivable by alx issue --deliver)", rendered
                )

    # item 2 --------------------------------------------------------------
    def break_the_date_line_and_the_supports(self):
        expected = alx.report_contract.localized_date("en", None)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(f"> {expected}\n", "").replace(
            "## Findings", f"{expected}\n\n## Findings"
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        ledger = self.ledger()
        by_id = {claim["claim_id"]: claim for claim in ledger["claims"]}
        by_id["C1"]["supports"] = ["C2"]
        by_id["C2"]["supports"] = ["C1"]
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )

    def test_check_fix_is_only_advertised_where_it_repairs_and_converges(self):
        self.bootstrap()
        self.break_the_date_line_and_the_supports()
        _code, first = self.run_in("check", "--fix")
        self.assertIn("integrity/date-line", first)
        self.assertIn("ledger/reference", first)
        self.assertNotIn("Fix: alx check --fix", first)
        _code, second = self.run_in("check", "--fix")
        self.assertEqual(self.grouped_block(first), self.grouped_block(second))

    def test_an_unrepairable_date_line_is_class_a_with_a_prose_remedy(self):
        self.bootstrap()
        self.break_the_date_line_and_the_supports()
        _code, out = self.run_in("check", "--fix")
        line = next(
            line for line in self.finding_lines(out) if "Date line" in line
        )
        self.assertIn("(edit prose; waivable by alx issue --deliver)", line)
        self.assertIn("[integrity/date-line] 1 (A, waivable by --deliver)", out)

    # item 3 --------------------------------------------------------------
    def test_family_headers_and_the_status_line_carry_the_class(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertRegex(out, r"\[fidelity/cache-detached\] \d+ \(F\)")
        self.assertRegex(out, r"=== STATUS: \d+ hard \(\d+ Class F, \d+ Class A\), \d+ warn ===")

    # item 4 --------------------------------------------------------------
    def test_the_claim_paragraph_table_lists_every_included_claim(self):
        self.bootstrap()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        first = self.ledger()["sources"][0]["url"]
        second = self.ledger()["sources"][1]["url"]
        report = report.replace(f"[registry note]({second})", "registry note", 1)
        # Minor 1: one claim with several candidate paragraphs, one with none.
        report = report.replace(
            "so the counts above are the only public record.",
            f"so the counts [above]({first}) are the only public record.",
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertIn("C1=unbound (candidates: 1, 3)", out)
        self.assertIn("C2=unbound (no candidate)", out)

    # item 5 --------------------------------------------------------------
    def test_source_set_records_a_family_justification_from_a_file(self):
        self.bootstrap()
        path = self.root / "family.txt"
        path.write_text(
            "The two pages are separately edited desks of the same host.\n",
            encoding="utf-8",
        )
        code, out = self.run_in(
            "source", "set", "S1", "--family-justification", path
        )
        self.assertEqual(0, code, out)
        source = self.ledger()["sources"][0]
        self.assertEqual(
            "The two pages are separately edited desks of the same host.",
            source["family_justification"],
        )

    # item 6 --------------------------------------------------------------
    def test_no_finding_line_is_longer_than_300_characters(self):
        rendered = self.rendered(
            self.item(message="C1: quantity '1916' is uncovered. " + "窗" * 400)
        )
        for line in self.finding_lines(rendered):
            self.assertLessEqual(len(line), alx.MAX_FINDING_CHARS, line)
        self.assertIn("…", rendered)
        self.assertIn("Fix: alx find S1 1916", rendered)
        self.assertIn("Remove: `alx claim drop C1 --apply`", rendered)


class LiveFidelityTests(AlxTestCase):
    """Spec §6.9.2/§6.10: T1's live result must reach classification."""

    def prepared(self):
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root",
            "dir",
            "run_alx",
            "run_in",
            "write_json",
            "init",
            "fetch",
            "bootstrap",
            "draft_report",
            "ledger",
            "state",
        ):
            setattr(issue_tests, name, getattr(self, name))
        issue_tests.prepared()
        return issue_tests

    def live_result(self, fetcher):
        """A real `source_fidelity` result, produced by T1 itself."""
        return alx.source_fidelity.check_source_fidelity(
            self.ledger(), fetcher=fetcher, sample_size=8, online=True
        )

    def test_check_reports_the_offline_probe_findings_of_t1(self):
        """Section (d): T1 stores `asdict` payloads; they must not be dropped."""
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text(
            "An unrelated page that carries none of the recorded extracts.",
            encoding="utf-8",
        )
        result = alx.source_fidelity.check_source_fidelity(
            self.ledger(), sample_size=0, online=False, cache_dir=self.dir / "sources"
        )
        self.assertTrue(
            all(isinstance(item, dict) for item in result["findings"]), result
        )
        collected = alx._fidelity_findings(alx.Workspace(self.dir), self.ledger())
        self.assertTrue(collected, "section (d) dropped T1's payload findings")
        self.assertIn("fidelity/mismatch", {item.family for item in collected})
        self.assertEqual({"F"}, {alx.adopted_class(item) for item in collected})
        _code, out = self.run_in("check")
        self.assertIn("[fidelity/mismatch]", out)

    def test_an_online_mismatch_refuses_issue_as_class_f(self):
        from contextlib import ExitStack

        issue_tests = self.prepared()
        result = self.live_result(
            lambda url: "<html><body><p>An unrelated page.</p></body></html>"
        )
        self.assertTrue(
            any(check["status"] == "mismatch" for check in result["checks"]), result
        )
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity, "check_source_fidelity", return_value=result
                )
            )
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn("[fidelity/mismatch]", out)
        self.assertIn("issue refused", out)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())

    def test_a_live_unreachable_beyond_quorum_is_class_a(self):
        from contextlib import ExitStack

        issue_tests = self.prepared()

        def dead(url):
            raise OSError("name resolution failed")

        result = self.live_result(dead)
        self.assertEqual(
            {"unreachable"}, {check["status"] for check in result["checks"]}, result
        )
        adopted = alx.adopt(alx._online_findings(result), online=True)
        self.assertTrue(adopted)
        self.assertEqual({"A"}, {item.klass for item in adopted})
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity, "check_source_fidelity", return_value=result
                )
            )
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())

    def test_deliver_waives_a_live_unreachable_as_a_delivery_note(self):
        from contextlib import ExitStack

        issue_tests = self.prepared()

        def dead(url):
            raise OSError("name resolution failed")

        result = self.live_result(dead)
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity, "check_source_fidelity", return_value=result
                )
            )
            code, out = self.run_in("issue", "--deliver")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any("unreachable" in note for note in notes["notes"]), notes)


class IntegrationHoleTests(AlxTestCase):
    """Task 7c: the remedies and the note skeleton a live dry run needed."""

    def started_content_review(self):
        self.bootstrap()
        code, out = self.run_in("check", "--fix")
        self.assertIn("claim->paragraph", out)
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)

    def line_with(self, out, needle):
        return next(line for line in out.splitlines() if needle in line)

    # item 2 --------------------------------------------------------------
    def test_deliver_restores_a_producer_quotation_loss(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace("「原始日記」", "records"), encoding="utf-8"
        )
        item = alx.Finding(
            family="fidelity/quotation-lost",
            severity="hard",
            klass="F",
            ids=[],
            message="Quoted span missing from the report: 「原始日記」",
            fix="",
            remove="alx snapshot --restore",
        )
        alx._auto_remedies(
            alx.Workspace(self.dir), self.state(), self.ledger(), [item], []
        )
        self.assertIn(
            "「原始日記」", (self.dir / "report.md").read_text(encoding="utf-8")
        )

    def test_a_stale_review_note_is_left_unstamped(self):
        """Spec §6.8: no stub — the real gates run and the hash stays old."""
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(issue_tests, name, getattr(self, name))
        issue_tests.prepared()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(
                "as the [registry note]", "and independently, as the [registry note]"
            ),
            encoding="utf-8",
        )
        stamps = {
            kind: json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )["report_sha256"]
            for kind in ("rewild", "content")
        }
        alx._receipt_phase(
            alx.Workspace(self.dir), self.state(), self.ledger(), [], []
        )
        for kind, before in stamps.items():
            note = json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(before, note["report_sha256"])
        self.assertNotEqual(
            alx.file_sha256(self.dir / "report.md"), stamps["content"]
        )

    # item 3 --------------------------------------------------------------
    def test_a_reworded_paragraph_gets_a_binding_remedy_not_a_re_review(self):
        self.started_content_review()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(
                "The archive released 1,204 documents in March 2026, a release",
                "In March 2026 the archive put out 1,204 documents, a release",
            ),
            encoding="utf-8",
        )
        _code, out = self.run_in("check")
        line = self.line_with(out, "cannot be located")
        self.assertIn("Fix: alx check --fix", line)
        self.assertNotIn("alx review start content --iter", line)
        _code, out = self.run_in("check", "--fix")
        self.assertNotIn("cannot be located", out)

    def test_a_missing_citation_asks_for_the_link_not_a_re_review(self):
        self.started_content_review()
        url = self.ledger()["sources"][0]["url"]
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(f"[recorded in the study]({url})", "recorded in the study"),
            encoding="utf-8",
        )
        _code, out = self.run_in("check")
        line = self.line_with(out, "no nearby citation")
        self.assertIn("Fix: add the source link to paragraph 1 of report.md", line)
        self.assertNotIn("alx review start content --iter", line)

    # item 4 --------------------------------------------------------------
    def test_review_start_prints_every_field_and_prefills_claim_support(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        for token in (
            "Fill reviews/content.json",
            "scores.<key>.score: integer 1-5",
            "checks.<key>",
            "section_reviews[]",
            "completion_note",
            "claim_support[].disposition: supported | qualified | removed",
        ):
            self.assertIn(token, out)
        note = json.loads(
            (self.dir / "reviews" / "content.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            ["C1", "C2"], [entry["claim_id"] for entry in note["claim_support"]]
        )
        self.assertEqual({""}, {entry["disposition"] for entry in note["claim_support"]})

    def test_the_filled_skeleton_validates_against_the_schemas(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        for kind in ("rewild", "content"):
            code, out = self.run_in("review", "start", kind)
            self.assertEqual(0, code, out)
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        reviews.dir = self.dir
        reviews.root = self.root
        reviews.run_alx = self.run_alx
        reviews.run_in = self.run_in
        reviews.state = self.state
        reviews.ledger = self.ledger
        for kind, schema_name in (
            ("rewild", "rewild-review.schema.json"),
            ("content", "content-review.schema.json"),
        ):
            with self.subTest(kind=kind):
                reviews.fill_note(kind)
                note = json.loads(
                    (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
                )
                schema = json.loads(
                    (Path(alx.__file__).resolve().parents[1] / "references" / schema_name)
                    .read_text(encoding="utf-8")
                )
                self.assertEqual(
                    [], list(alx.validate_ledger.validate_schema(note, schema))
                )
                code, out = self.run_in("review", "finish", kind)
                self.assertEqual(0, code, out)

    def test_finish_names_the_file_and_every_missing_path(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(1, code)
        self.assertIn("reviews/content.json", out)
        for path in (
            "status",
            "scores.question_answered.score",
            "scores.question_answered.rationale",
            "checks.central_judgment_answers_question",
            "section_reviews",
            "completion_note",
            "claim_support[C1].disposition",
        ):
            with self.subTest(path=path):
                self.assertIn(path, out)

    # addendum ------------------------------------------------------------
    def test_a_claim_field_remedy_names_the_claim_add_round_trip(self):
        rendered = alx.render_grouped(
            alx.adopt(
                [
                    alx.Finding(
                        family="ledger/reference",
                        severity="hard",
                        klass="F",
                        ids=["C23"],
                        message="Analysis has circular support: C23 -> C10 -> C23",
                        fix="",
                        remove="",
                    )
                ]
            )
        )
        self.assertIn(
            "set field supports in claims/*.json, then alx claim add claims/*.json",
            rendered,
        )

    def test_an_uncited_claim_gets_the_link_imperative(self):
        self.bootstrap()
        url = self.ledger()["sources"][1]["url"]
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(f"[registry note]({url})", "registry note", 1),
            encoding="utf-8",
        )
        _code, out = self.run_in("check")
        line = self.line_with(out, "C2 is included in the report with no")
        self.assertIn("Fix: add the source link to paragraph", line)
        bound = self.line_with(out, "C1 is included in the report with no")
        self.assertIn("Fix: alx check --fix", bound)


CLAIM_THREE = {
    "claim_id": "C3",
    "claim": "Retention rose to 88 percent after the second review round.",
    "kind": "fact",
    "importance": "supporting",
    "source_evidence": [
        {
            "source_id": "S1",
            "extract_or_location": (
                "Retention rose to 88 percent after the second review round, "
                "the registry reported."
            ),
        }
    ],
}

CHANGED_PAGE = PAGE.replace(
    "<p>The archive released",
    "<p>Correction: an earlier tally was withdrawn.</p>\n<p>The archive released",
)


class HonestRemedyTests(AlxTestCase):
    """Ruling R10: `--fix` is advertised only where spec §6.7 repairs."""

    def printed(self, **kwargs):
        base = dict(
            family="ledger/quantity",
            severity="hard",
            klass="F",
            ids=["C8", "S16"],
            message=(
                "C8: quantity '1918' is uncovered; candidates: 12; "
                "https://example.org/study"
            ),
            fix="alx check --fix",
            remove="alx claim drop C8 --apply",
        )
        base.update(kwargs)
        return alx.adopt([alx.Finding(**base)])[0]

    def test_no_family_advertises_a_repair_check_fix_does_not_perform(self):
        for family in alx.FAMILIES:
            for severity in ("hard", "warn"):
                for producer in ("alx check --fix", "alx check"):
                    item = self.printed(
                        family=family, severity=severity, fix=producer
                    )
                    with self.subTest(
                        family=family, severity=severity, fix=producer
                    ):
                        self.assertNotEqual("alx check", item.fix)
                        if family not in alx.MECHANICAL_FIX_FAMILIES:
                            self.assertNotEqual("alx check --fix", item.fix)
                        if item.klass == "A":
                            self.assertEqual("", item.remove, item)
                        if item.fix:
                            self.assertTrue(alx.valid_remedy(item.fix), item.fix)

    def test_coverage_linkage_gets_the_merge_it_needs(self):
        """Important 1: `--fix` never repairs coverage/synthesis linkage."""
        rendered = alx.render_grouped(
            [
                self.printed(
                    family="ledger/coverage",
                    severity="warn",
                    klass="A",
                    ids=["C8"],
                    message="Coverage release is supported but names no supported claim.",
                    remove="",
                )
            ]
        )
        self.assertIn("Fix: alx ledger merge coverage.json", rendered)
        self.assertNotIn("alx check", rendered)

    def test_a_class_a_rewild_finding_asks_for_prose_not_a_check(self):
        """Important 2: `alx check` edits no prose, so it is never the remedy."""
        rendered = alx.render_grouped(
            [
                self.printed(
                    family="rewild/length",
                    klass="A",
                    ids=[],
                    message="Report is 120 words; minimum is 7,500.",
                    fix="alx check",
                    remove="alx snapshot --restore",
                )
            ]
        )
        self.assertIn("Fix: (edit prose; waivable by alx issue --deliver)", rendered)
        self.assertNotIn("Remove:", rendered)
        self.assertNotIn("alx check", rendered)

    def test_a_line_with_no_budget_left_still_cuts_its_message(self):
        """Minor 2: the ids and the remedy may overrun; the message may not."""
        body = alx._fit(
            "m" * 500,
            [f"C{number}" for number in range(1, 60)],
            "alx claim drop C1 --apply",
            "alx claim drop C1 --apply",
        )
        self.assertEqual("…", body)


class FixRoundTests(AlxTestCase):
    """Task 7d part J: the whole-branch judgment findings on the `alx` side."""

    def issue_helper(self):
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
        ):
            setattr(issue_tests, name, getattr(self, name))
        return issue_tests

    def three_bound_paragraphs(self):
        """C1->1, C2->2, C3->3, each claim on its own paragraph."""
        self.bootstrap()
        self.run_in("check", "--fix")
        batch = self.write_json("third.json", [CLAIM_THREE])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        for claim_id, number in (("C1", 1), ("C2", 2), ("C3", 3)):
            code, out = self.run_in("claim", "bind", claim_id, "--paragraph", number)
            self.assertEqual(0, code, out)

    def line_with(self, out, needle):
        return next(line for line in out.splitlines() if needle in line)

    # J2 ------------------------------------------------------------------
    def test_sequential_bound_drops_delete_the_bound_paragraphs(self):
        self.three_bound_paragraphs()
        for claim_id in ("C1", "C2"):
            code, out = self.run_in("claim", "drop", claim_id, "--apply")
            self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("The archive released 1,204 documents", report)
        self.assertNotIn("The registry logged 1,204 documents", report)
        self.assertIn("The reading room keeps 「原始日記」", report)
        bindings = self.state()["bindings"]
        self.assertEqual({"C3": 1}, bindings)
        paragraph = alx.body_paragraphs(report)[bindings["C3"] - 1]
        self.assertIn("原始日記", paragraph[3])

    def test_leftover_prose_of_a_dropped_claim_is_reported(self):
        self.three_bound_paragraphs()
        self.run_in("claim", "drop", "C1", "--apply")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        restored = report.replace(
            "The registry logged",
            "The archive released 1,204 documents in March 2026, a release "
            "recorded in the study that the registry confirmed.\n\n"
            "The registry logged",
        )
        (self.dir / "report.md").write_text(restored, encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertIn("binding/leftover-prose", out)

    # J3 ------------------------------------------------------------------
    def test_the_printed_bind_names_the_paragraph_check_means(self):
        self.bootstrap()
        first = self.ledger()["sources"][0]["url"]
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(
                "so the counts above are the only public record.",
                f"so the counts [above]({first}) are the only public record.",
            ),
            encoding="utf-8",
        )
        _code, out = self.run_in("check")
        ambiguous = self.line_with(out, "ambiguous")
        printed = re.search(r"Fix: (alx claim bind C1 --paragraph (\d+))", ambiguous)
        self.assertIsNotNone(printed, ambiguous)
        code, out = self.run_in(*shlex.split(printed.group(1))[1:])
        self.assertEqual(0, code, out)
        number = int(printed.group(2))
        self.assertEqual(number, self.state()["bindings"]["C1"])
        _code, out = self.run_in("check")
        self.assertIn(f"C1={number}", out)
        block = alx.body_paragraphs(
            (self.dir / "report.md").read_text(encoding="utf-8")
        )[number - 1][3]
        self.assertIn(first, block)

    # J4 ------------------------------------------------------------------
    def stale_context(self):
        """Refresh S1 onto an edited page: the extract survives, its context does not."""
        self.bootstrap()
        self.run_in("check", "--fix")
        with mock_production_transport(responses(CHANGED_PAGE)):
            code, out = self.run_in("fetch", "--id", "S1", "--refresh")
        self.assertEqual(0, code, out)

    def test_context_changed_is_reported_with_the_two_step_remedy(self):
        self.stale_context()
        _code, out = self.run_in("check")
        self.assertIn("[fidelity/context-changed]", out)
        line = self.line_with(out, "context changed")
        self.assertIn(
            "Fix: alx fetch --id S1 --refresh, then alx claim add claims/*.json", line
        )
        self.assertIn("Remove: `alx claim drop C1 --apply`", line)

    def test_the_two_step_remedy_clears_the_context_finding(self):
        self.stale_context()
        with mock_production_transport(responses(CHANGED_PAGE)):
            self.run_in("fetch", "--id", "S1", "--refresh")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        _code, out = self.run_in("check")
        self.assertNotIn("context-changed", out)

    # J6 ------------------------------------------------------------------
    def test_a_dropped_paragraph_is_never_restored_by_a_quotation_loss(self):
        self.three_bound_paragraphs()
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        code, out = self.run_in("claim", "drop", "C3", "--apply")
        self.assertEqual(0, code, out)
        _code, out = self.run_in("check")
        self.assertNotIn("quotation-lost", out)
        code, out = self.run_in("snapshot", "--restore")
        self.assertEqual(0, code, out)
        self.assertNotIn(
            "原始日記", (self.dir / "report.md").read_text(encoding="utf-8")
        )

    # J9 ------------------------------------------------------------------
    def test_the_ledger_half_of_content_gate_is_not_printed_twice(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        ledger = self.ledger()
        ledger["sources"][0]["url"] = ledger["sources"][0]["url"].replace(
            "https://", "http://"
        )
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, out = self.run_in("check")
        https = [line for line in out.splitlines() if "must be https" in line]
        self.assertEqual(1, len(https), out)
        self.assertNotIn("alx review start content --iter", https[0])


class DeliveryRoundTests(AlxTestCase):
    """Task 7d part J: what `issue --deliver` may and may not ship."""

    def helper(self):
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
        ):
            setattr(issue_tests, name, getattr(self, name))
        return issue_tests

    def prepared_with_supporter(self):
        """A reviewed workspace where C3 supports C2, the claim that will drop."""
        self.bootstrap()
        supporter = dict(CLAIM_THREE, supports=["C2"])
        batch = self.write_json("supporter.json", [supporter])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("dir", "root", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        reviews.finish_reviews()

    def mismatch_result(self, claim_id="C2", source_id="S2"):
        return {
            "status": "failed",
            "online": True,
            "transport": alx.source_fidelity.PRODUCTION_TRANSPORT,
            "checks": [
                {
                    "claim_id": claim_id,
                    "source_id": source_id,
                    "url": "https://registry.example.net/note",
                    "status": "mismatch",
                    "detail": (
                        f"{claim_id}: the extract is no longer on the live page."
                    ),
                }
            ],
            "refreshed_source_ids": [],
            "disclosure_required": [],
        }

    def passed_result(self):
        return {
            "status": "passed",
            "online": True,
            "transport": alx.source_fidelity.PRODUCTION_TRANSPORT,
            "checks": [],
            "refreshed_source_ids": [],
            "disclosure_required": [],
        }

    def live_sequence(self, stack, results):
        """The live pass answers `results` in order; offline calls stay real."""
        real = alx.source_fidelity.check_source_fidelity
        seen = {"n": 0}

        def live(ledger, **kwargs):
            if not kwargs.get("online"):
                return real(ledger, **kwargs)
            seen["n"] += 1
            return results[min(seen["n"], len(results)) - 1]

        stack.enter_context(
            mock.patch.object(
                alx.source_fidelity, "check_source_fidelity", side_effect=live
            )
        )
        return seen

    # J1 ------------------------------------------------------------------
    def test_a_live_mismatch_never_reaches_a_receipt(self):
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(stack, [self.mismatch_result()])
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn("[fidelity/mismatch]", out)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())
        self.assertFalse((self.dir / "receipts" / "source-fidelity.json").exists())

    def test_deliver_drops_the_mismatching_claim_before_issuing(self):
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(
                stack, [self.mismatch_result(), self.passed_result()]
            )
            code, out = self.run_in("issue", "--deliver")
        self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("as the [registry note]", report)
        self.assertNotIn("C2", {claim["claim_id"] for claim in self.ledger()["claims"]})
        self.assertIn(
            "C2", {claim["claim_id"] for claim in self.ledger()["excluded_claims"]}
        )
        receipt = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        # `render` refuses unless this hash is the delivered report, so the
        # dropped paragraph can never reach a PDF.
        self.assertEqual(alx.file_sha256(self.dir / "report.md"), receipt["report_sha256"])

    def test_a_stale_source_fidelity_receipt_is_never_hashed_in(self):
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        (self.dir / "receipts").mkdir(parents=True, exist_ok=True)
        (self.dir / "receipts" / "source-fidelity.json").write_text(
            json.dumps({"status": "passed", "ledger_sha256": "0" * 64}),
            encoding="utf-8",
        )
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(stack, [self.mismatch_result()])
            code, _out = self.run_in("issue")
        self.assertEqual(1, code)
        self.assertFalse((self.dir / "receipts" / "source-fidelity.json").exists())

    # J5 ------------------------------------------------------------------
    def test_deliver_rechecks_after_an_online_drop_and_refuses_survivors(self):
        from contextlib import ExitStack

        self.prepared_with_supporter()
        issue_tests = self.helper()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(
                stack, [self.mismatch_result(), self.passed_result()]
            )
            code, out = self.run_in("issue", "--deliver")
        self.assertEqual(1, code, out)
        self.assertIn("excluded", out)
        self.assertIn("issue refused", out)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())

    # J7 ------------------------------------------------------------------
    def test_issue_refreshes_the_last_check_counters(self):
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        _code, _out = self.run_in("check")
        before = self.state()["last_check"]
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(stack, [self.mismatch_result()])
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertNotEqual(before["at"], self.state()["last_check"]["at"])

    def test_render_drops_the_companion_inside_the_reserve(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        issue_tests = self.helper()
        issue_tests.prepared()
        rendered = []

        def fake_render_pdf(input_path, output_path, **kwargs):
            rendered.append(kwargs.get("template"))
            Path(output_path).write_bytes(b"%PDF-1.7\n")
            return Path(output_path)

        def fake_render_pages(pdf_path, output_dir, **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            page = Path(output_dir) / "page-001.png"
            page.write_bytes(b"\x89PNG")
            return [page]

        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            code, out = self.run_in("issue")
            self.assertEqual(0, code, out)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=fake_render_pages
                )
            )
            self.set_remaining(5)
            code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        self.assertEqual(["executive"], rendered)
        self.assertIn("tooling/render", out)

    # J10 -----------------------------------------------------------------
    def test_an_aborted_issue_takes_its_verification_note_back_out(self):
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()

        def refused(*args, **kwargs):
            raise ValueError("network unavailable")

        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity,
                    "issue_source_fidelity_receipt",
                    side_effect=refused,
                )
            )
            code, _out = self.run_in("issue")
        self.assertEqual(1, code)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(alx.VERIFICATION_NOTE_PREFIX["en"], report)


class RemedyTests(AlxTestCase):
    def test_every_remedy_is_a_parsable_command_or_closed_imperative(self):
        parser = alx.build_parser()
        self.assertTrue(alx.REMEDY_TEMPLATES)
        for key, template in alx.REMEDY_TEMPLATES.items():
            text = template.format(**REMEDY_SAMPLE)
            closed = any(pattern.match(text) for pattern in CLOSED_IMPERATIVES)
            with self.subTest(remedy=key):
                if closed:
                    continue
                self.assertTrue(text.startswith("alx "), text)
                parser.parse_args(shlex.split(text)[1:])


    def test_every_family_remedy_parses(self):
        """Ruling R6: every remedy `alx` can print, for every known family."""
        parser = alx.build_parser()
        self.assertTrue(alx.FAMILIES)
        for family in alx.FAMILIES:
            for severity in ("hard", "warn"):
                item = alx.Finding(
                    family=family,
                    severity=severity,
                    klass="F",
                    ids=["C8", "S16"],
                    message=(
                        "C8: claim asserts n:1918; S16 offered d:1918-01 only; "
                        "candidates: 12; https://example.org/study "
                        "'decision_relevance' is a required property"
                    ),
                    fix="",
                    remove="",
                )
                for text in alx._remedies(item, paragraphs=7):
                    if not text:
                        continue
                    closed = any(
                        pattern.match(text) for pattern in CLOSED_IMPERATIVES
                    )
                    with self.subTest(family=family, severity=severity, remedy=text):
                        if closed:
                            continue
                        self.assertTrue(text.startswith("alx "), text)
                        parser.parse_args(shlex.split(text)[1:])

    def test_printed_remedies_of_a_failing_check_parse(self):
        parser = alx.build_parser()
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        _code, out = self.run_in("check")
        printed = re.findall(r"(?:Fix|Remove): `?(alx [^`.\n]+)", out)
        self.assertTrue(printed, out)
        for text in printed:
            if any(pattern.match(text.strip()) for pattern in CLOSED_IMPERATIVES):
                continue
            with self.subTest(remedy=text):
                parser.parse_args(shlex.split(text.strip())[1:])


if __name__ == "__main__":
    unittest.main()
