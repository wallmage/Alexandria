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

CLAIM_BROKEN = {
    "claim_id": "C3",
    "claim": "The archive released 9,999 documents in March 2026.",
    "kind": "fact",
    "importance": "supporting",
    "source_evidence": [
        {
            "source_id": "S1",
            "extract_or_location": "The archive released 9,999 documents.",
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

_EXTRACTABLE_PDF_CACHE = None


def extractable_pdf_bytes(text="A" * 600):
    """A one-page PDF whose extractable text is long enough to pass B6."""
    global _EXTRACTABLE_PDF_CACHE
    if text == "A" * 600 and _EXTRACTABLE_PDF_CACHE is not None:
        return _EXTRACTABLE_PDF_CACHE
    from weasyprint import HTML

    data = HTML(string=f"<p>{text}</p>").write_pdf()
    if text == "A" * 600:
        _EXTRACTABLE_PDF_CACHE = data
    return data


EMPTY_PDF_BYTES = b"%PDF-1.7\n"

CLOSED_IMPERATIVES = (
    re.compile(r"^set field \S+ in \S+$"),
    re.compile(r"^set field \S+ in \S+, then alx claim add \S+$"),
    re.compile(r"^alx fetch --id S\d+, then alx claim add \S+$"),
    re.compile(r"^extend the quote in \S+$"),
    re.compile(
        r"^paste the closest passage as extract_or_location in \S+, "
        r"or alx find S\d+ KEYWORD$"
    ),
    re.compile(r"^extend the report body in report\.md$"),
    re.compile(r"^delete paragraph \d+ of report\.md$"),
    re.compile(r"^remove link \S+ from report\.md$"),
    re.compile(r"^\(edit prose; warning, never blocks\)$"),
    re.compile(
        r"^write \[C\d+\] at the end of the sentence in paragraph \d+ of "
        r"report\.md, then alx check --fix$"
    ),
    re.compile(
        r"^write \[C\d+\] at the end of the sentence that states claim C\d+ "
        r"in report\.md, then alx check --fix$"
    ),
    re.compile(r"^deepen \(research, counterevidence, implications\), never pad$"),
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

    def pad_report(self, minimum=5100):
        """Keep an issue-ready report at or above the two-thirds length floor."""
        self.set_report_words(minimum)

    def set_report_words(self, n):
        path = self.dir / "report.md"
        text = re.sub(r"(?:Context )+", "", path.read_text(encoding="utf-8"))
        lang = self.state().get("lang", "en")
        count, _ = alx.report_blocks.report_length(text, lang)
        if count < n:
            filler = "Context " * (n - count)
            for heading in ("## Sources", "## 资料来源", "## 來源", "## 来源"):
                if heading in text:
                    text = text.replace(heading, filler + "\n\n" + heading, 1)
                    break
            else:
                text = text.rstrip() + "\n\n" + filler + "\n"
        path.write_text(text, encoding="utf-8")
        count, _ = alx.report_blocks.report_length(text, lang)
        if count > n:
            extra = count - n
            text = text.replace("Context ", "", extra)
            path.write_text(text, encoding="utf-8")


class InitTests(AlxTestCase):
    def test_budget_minutes_default_is_30(self):
        parser = alx.build_parser()
        init = parser._subparsers._group_actions[0].choices["init"]
        self.assertEqual(
            30, init._option_string_actions["--budget-minutes"].default
        )

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
        self.assertEqual(0, code, out)
        self.assertIn("workspace exists", out)
        self.assertIn("keeping it", out)
        self.assertIn("Next:", out)
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
        self.assertEqual(0, code, out)
        person = self.ledger()["people"][0]
        self.assertNotIn("living_status", person)
        self.assertEqual("primary_subject", person["relationship"])
        self.assertIn("archetype: person (given)", out)
        self.assertIn("language:", out)


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

    def test_dead_host_keeps_its_real_reason_class(self):
        """An http:// URL is promoted, so the failure is the https one, named."""
        self.init()
        with mock_production_transport(responses()):
            code, out = self.run_in("fetch", "http://dead.example.org/study")
        self.assertEqual(0, code)
        self.assertIn("(dns:", out)
        self.assertNotIn("plaintext-http", out)
        self.assertIn("https was tried in place of http://dead.example.org/study", out)

    def test_non_http_scheme_is_rejected(self):
        self.init()
        code, out = self.run_in("fetch", "ftp://example.org/study")
        self.assertEqual(0, code)
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
            code, out = self.run_in("fetch", "--id", "S1")
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
            code, out = self.run_in("fetch", "--id", "S1")
            self.assertEqual(0, code, out)
        workspace = alx.Workspace(self.dir)
        self.assertEqual([False, True], [call["refresh"] for call in seen])
        for call in seen:
            self.assertEqual(workspace.sources, call["cache_dir"])
            self.assertEqual(20, alx.FETCH_TIMEOUT_SECONDS)
            self.assertEqual(alx.FETCH_TIMEOUT_SECONDS, call["timeout"])
            self.assertNotIn("deadline", call)

    def test_fetch_batch_stops_near_the_deadline(self):
        self.init()
        self.set_remaining(10)
        code, out = self.fetch("https://example.org/study")
        self.assertEqual(0, code, out)
        self.assertNotIn("fetch batch stopped", out)
        self.assertEqual(1, len(self.ledger()["sources"]))


class LanguageTests(AlxTestCase):
    def test_verification_note_templates_per_language(self):
        self.assertFalse(hasattr(alx, "_verification_note"))
        self.assertFalse(hasattr(alx, "_insert_verification_note"))

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
        # One line per hit: the paste line carries the window, nothing repeats.
        self.assertIn("S1 #1 extract_or_location: ", out)
        self.assertIn("1,204 documents", out)
        self.assertNotIn("…", out)
        self.assertNotIn("S1 #1 · ", out)
        for line in out.splitlines():
            if line.startswith("S1 #"):
                self.assertLessEqual(len(line), 340, line)

    def test_find_takes_many_sources_and_many_keywords(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        code, out = self.run_in("find", "S1,S2", "1,204", "retention")
        self.assertEqual(0, code, out)
        self.assertIn("S1 #1 extract_or_location: ", out)
        self.assertIn("S2 #1 extract_or_location: ", out)
        # `retention` is only in S1, so it still reports one hit, not a miss.
        self.assertNotIn("no source contains retention", out)
        code, all_out = self.run_in("find", "all", "1,204")
        self.assertEqual(0, code, all_out)
        self.assertIn("S1 #1 extract_or_location: ", all_out)
        self.assertIn("S2 #1 extract_or_location: ", all_out)

    def test_find_reports_a_missing_cache_and_a_missing_keyword(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("find", "S1,S9", "nowhere-in-any-source")
        self.assertEqual(0, code, out)
        self.assertIn("S9 has no cache; run alx fetch", out)
        self.assertIn("no source contains nowhere-in-any-source", out)

    def test_find_paste_line_round_trips_to_the_window(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("find", "S1", "1,204")
        self.assertEqual(0, code, out)
        prefix = "S1 #1 extract_or_location: "
        paste = next(
            line for line in out.splitlines() if line.startswith(prefix)
        )
        window = json.loads(paste[len(prefix) :])
        self.assertIn("1,204", window)
        # The whole hit is one line; `find` prints nothing else about it.
        self.assertEqual(1, len([1 for line in out.splitlines() if "#1 " in line]))


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

    def test_missing_claim_id_fails_while_a_warned_claim_is_upserted(self):
        # A2: a quantity not in the extract/page warns; the claim still lands.
        self.init()
        self.fetch("https://example.org/study")
        bad = dict(CLAIM_ONE)
        bad.pop("claim_id")
        warned = dict(
            CLAIM_ONE,
            claim_id="C9",
            claim="The archive released 7,777 documents in March 2026.",
        )
        batch = self.write_json("claims.json", [bad, warned])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C10 added (assigned id)", out)
        self.assertIn("C9 WARN", out)
        self.assertIn("[ledger/quantity]", out)
        self.assertEqual(
            ["C10", "C9"], [c["claim_id"] for c in self.ledger()["claims"]]
        )

    def test_warn_only_claim_is_accepted(self):
        self.init()
        self.fetch("https://example.org/study")
        warned = dict(
            CLAIM_ONE,
            claim_id="C9",
            claim="The archive released 7,777 documents in March 2026.",
        )
        batch = self.write_json("claims.json", [warned])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code)
        self.assertIn("C9 added", out)
        self.assertIn("C9 WARN", out)
        self.assertIn("[ledger/quantity]", out)
        self.assertNotIn("FAIL", out)
        self.assertEqual(["C9"], [c["claim_id"] for c in self.ledger()["claims"]])

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

    def test_person_claims_accepted_while_status_unknown(self):
        """R25 restatement of test_person_claims_refused_while_status_unknown.

        `living_status` gates nothing; an unregistered id is the only person
        finding, and it warns.
        """
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
        )
        self.fetch("https://example.org/study")
        claim = dict(CLAIM_ONE)
        claim["person_ids"] = ["P1"]
        batch = self.write_json("claims.json", [claim])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertNotIn("living_status", out)
        self.assertEqual(["C1"], [c["claim_id"] for c in self.ledger()["claims"]])

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
        self.assertEqual(0, code)
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
                },
                # R28 restatement: a missing `reasoning` no longer refuses the
                # claim, so the claim-input half of this test is now the empty
                # extract, which is still hard.
                {"source_id": "S1", "extract_or_location": ""},
            ],
        }
        batch = self.write_json("broken.json", [broken])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code)
        self.assertIn("ledger/claim-input", out)
        self.assertIn("extract_or_location", out)
        self.assertIn("fidelity/mismatch", out)
        self.assertEqual([], self.ledger()["claims"])

    def test_r28_warn_families_are_printed_but_block_neither_add_nor_check(self):
        """R28: a downgraded family is advice — the claim still lands."""
        self.bootstrap()
        warned = dict(
            CLAIM_ONE,
            claim_id="C9",
            supports=["C99"],
            person_ids=["P9"],
        )
        batch = self.write_json("warned.json", [warned])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C9 WARN", out)
        self.assertIn("[ledger/reference]", out)
        self.assertIn("[ledger/person]", out)
        self.assertIn("C9", {claim["claim_id"] for claim in self.ledger()["claims"]})
        _code, out = self.run_in("check")
        hard = out.split("=== WARN")[0]
        for family in ("ledger/reference", "ledger/person", "ledger/synthesis"):
            self.assertNotIn(family, hard)

    def test_quantity_is_warn_and_does_not_block_add_or_check(self):
        """A2: ledger/quantity is advice — the claim still lands."""
        self.bootstrap()
        warned = dict(
            CLAIM_ONE,
            claim_id="C9",
            claim="The archive released 7,777 documents in March 2026.",
        )
        batch = self.write_json("warned.json", [warned])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C9 WARN", out)
        self.assertIn("[ledger/quantity]", out)
        self.assertIn("C9", {claim["claim_id"] for claim in self.ledger()["claims"]})
        _code, out = self.run_in("check")
        # R33 (user): an unsupported figure is a warning, never a block.
        self.assertIn("ledger/quantity", out.split("=== WARN")[1])

    def test_omitted_kind_and_importance_warn_and_still_land(self):
        """A3: missing kind/importance is advice — defaults recorded, claim lands."""
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "defaults.json",
            [
                {
                    "claim_id": "C3",
                    "claim": "The archive released 1,204 documents in March 2026.",
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
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C3 added", out)
        self.assertNotIn("FAIL", out)
        self.assertIn("C3 WARN", out)
        self.assertIn("[ledger/claim-input]", out)
        self.assertIn(
            "C3: kind not given (recorded as fact); "
            "importance not given (recorded as supporting)",
            out,
        )
        claim = self.ledger()["claims"][0]
        self.assertEqual("fact", claim["kind"])
        self.assertEqual("supporting", claim["importance"])

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
        self.assertEqual(0, code, out)
        self.assertIn("ignored keys: claims", out)
        self.assertIn("claims only via claim add", out)
        self.assertNotIn("C7", {c["claim_id"] for c in self.ledger()["claims"]})
        patch = self.write_json("patch.json", {"sources": [{"source_id": "S9"}]})
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.assertIn("ignored keys: sources", out)

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

    def test_unmergeable_keys_are_warned_and_ignored(self):
        """§6.5 forbids only claims/sources; other keys are ignored, not refused."""
        self.bootstrap()
        patch = self.write_json(
            "patch.json",
            {"brief": {"decision_or_use": "a call"}, "excluded_claims": [], "notes": 1},
        )
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.assertIn("WARN: ignored key(s) not merged", out)
        self.assertIn("excluded_claims, notes", out)
        ledger = self.ledger()
        self.assertEqual("a call", ledger["brief"]["decision_or_use"])
        self.assertNotIn("notes", ledger)

    def test_merge_arbitrary_synthesis_prints_only_merged(self):
        self.bootstrap()
        patch = self.write_json("syn.json", {"synthesis": "arbitrary-shape notes"})
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        content = [
            line
            for line in out.splitlines()
            if line and not line.startswith("elapsed")
        ]
        self.assertEqual(["merged: synthesis"], content)
        self.assertEqual("arbitrary-shape notes", self.ledger()["synthesis"])


class CheckTests(AlxTestCase):
    def test_cache_detached_is_hard_with_refresh_remedy(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(0, code)
        self.assertIn("cache-detached", out)
        self.assertIn("alx fetch --id S1", out)

    def test_cache_missing_is_hard(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.meta.json").unlink()
        code, out = self.run_in("check")
        self.assertEqual(0, code)
        self.assertIn("cache", out)

    def test_link_outside_the_ledger_is_hard(self):
        self.bootstrap()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(
            "## Sources", "See [another page](https://elsewhere.example/x).\n\n## Sources"
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(0, code)
        self.assertIn("elsewhere.example", out)

    def test_a_figure_invented_after_the_snapshot_is_restored_at_issue(self):
        """R30: `issue` restores the snapshot on fidelity/rewild, never ships it."""
        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("1,204", report)
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        (self.dir / "report.md").write_text(
            report.replace("1,204", "1,304"), encoding="utf-8"
        )
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("fidelity/rewild", out)
        code, out = self.run_in("issue", "--offline")
        self.assertEqual(0, code, out)
        self.assertIn("restored from the latest snapshot", out)
        self.assertIn("1,204", (self.dir / "report.md").read_text(encoding="utf-8"))

    def test_control_characters_and_quotation_loss_after_snapshot(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        damaged = report.replace("「原始日記」", "\x01")
        (self.dir / "report.md").write_text(damaged, encoding="utf-8")
        code, out = self.run_in("check")
        self.assertEqual(0, code)
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
        self.assertEqual(0, code)
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
        self.assertEqual(0, code)
        self.assertRegex(out, r"=== HARD \d+ \(fix, or alx issue drops them\) ===")
        self.assertRegex(out, r"=== STATUS: check #1\. Next:")
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
        self.assertRegex(out.strip().splitlines()[-1], r"^elapsed \d+ min, remaining \d+ min$")
        self.assertNotIn("stop fixing", out)
        self.assertNotIn("--deliver", out)


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
        self.assertIn("references/content-quality.md §13 review protocol", out)
        code, out = self.run_in("review", "start", "rewild")
        self.assertEqual(0, code, out)
        self.assertIn("references/rewild-gate.md blind-review protocol", out)

    def test_finish_refuses_an_incomplete_note(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertIn("WARN review/content:", out)
        self.assertIn("scores", out)
        self.assertTrue(self.state()["reviews"]["content"]["finished"])

    def test_only_a_qualified_or_removed_claim_needs_a_support_note(self):
        """Restates test_content_note_needs_a_disposition_per_mapped_claim.

        A retained claim with no entry is supported by default; only the ones
        the reviewer changed or rejected owe a note.
        """
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        self.fill_note("content")
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["claim_support"] = []
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        note["claim_support"] = [
            {"claim_id": "C1", "paragraph": 1, "disposition": "qualified", "note": ""}
        ]
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertIn("WARN review/content: claim_support[C1].note", out)

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

    def test_changes_after_a_review_never_ask_for_another_review(self):
        """R30: reviews are optional, so a stale one is never a finding."""
        self.bootstrap()
        self.run_in("check", "--fix")
        self.finish_reviews()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(
            "as the [registry note]", "and independently, as the [registry note]"
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        ledger = self.ledger()
        ledger["claims"][0]["claim"] = "The archive released 1,204 documents in March."
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("re-review required", out)
        self.assertNotIn("re-review required", out.split("=== WARN")[0])


class IssueTests(AlxTestCase):
    def prepared(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertGreaterEqual(calls["online"], 1)
        self.assertIn("source fidelity:", out)
        receipt = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            alx.file_sha256(self.dir / "report.md"), receipt["report_sha256"]
        )
        self.assertIn("ledger_sha256", receipt)
        self.assertIn("receipts", receipt)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        for prefix in alx.VERIFICATION_NOTE_PREFIX.values():
            self.assertNotIn(prefix, report)

    def test_issue_records_min_sections_fail_and_still_writes_receipts(self):
        from contextlib import ExitStack

        self.prepared()
        with ExitStack() as stack:
            self.stub_gates(stack)
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())
        self.assertTrue((self.dir / "receipts" / "rewild.json").exists())
        self.assertTrue((self.dir / "receipts" / "content.json").exists())
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )["notes"]
        self.assertTrue(
            any(
                "Report has 2 H2 sections; minimum is 3." in note
                and "validate_report --fast --final-once failed:" in note
                for note in notes
            ),
            notes,
        )

    def test_length_floor_is_warn_and_issue_delivers_without_deliver(self):
        """R28: `rewild/length` is a warning; plain `issue` still delivers."""
        from contextlib import ExitStack

        self.prepared()
        _code, out = self.run_in("check")
        self.assertIn("[rewild/length]", out)
        self.assertEqual(0, self.state()["last_check"]["hard"])
        self.assertNotIn("class_f", self.state()["last_check"])
        with ExitStack() as stack:
            self.stub_gates(stack, rewild=False)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any("minimum is" in note for note in notes["notes"]), notes)

    def test_every_downgraded_family_is_warn_and_never_blocks(self):
        """R28 severity table: the families `alx` itself emits as warnings."""
        for family in (
            "tooling/receipt",
            "tooling/render",
            "review/rewild",
            "review/content-stale",
            "fidelity/unreachable",
            "fidelity/undecodable",
        ):
            with self.subTest(family=family):
                item = alx.finding(family, "message", severity="hard")
                self.assertEqual("warn", item.severity)
                self.assertEqual("A", item.klass)
                self.assertEqual([], alx.hard_findings([item]))
                self.assertEqual([], alx.class_f_findings([item]))

    def test_issue_default_does_not_call_live_sampler(self):
        from contextlib import ExitStack

        self.prepared()
        with ExitStack() as stack:
            calls = self.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertEqual(0, calls["online"])
        self.assertNotIn("source fidelity:", out)

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

    def test_issue_drops_the_class_f_claim_and_still_issues(self):
        """C1 restatement of ..._refuses_class_f_without_deliver.

        `issue` applies the Remove remedies, prints the finding it cannot
        remove (a detached cache is not a claim), and writes the receipts.
        """
        from contextlib import ExitStack

        self.prepared()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        with ExitStack() as stack:
            calls = self.stub_gates(stack)
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertIn("dropped C1 (fidelity/mismatch)", out)
        self.assertIn("cache-detached", out)
        self.assertGreaterEqual(calls["online"], 1)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

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
            code, out = self.run_in("issue")
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
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(notes["notes"])
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_a_refused_fidelity_receipt_is_a_warning_not_an_abort(self):
        """R28: tooling/receipt is a warning; `issue` delivers and records it."""
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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )["notes"]
        self.assertTrue(
            any("source-fidelity receipt not issued" in note for note in notes),
            notes,
        )


class RenderTests(AlxTestCase):
    def test_render_runs_the_issue_step_itself(self):
        """C2 restatement of ..._refuses_without_a_matching_issue_receipt.

        A missing receipt, then a stale one: both times `render` runs the
        issue step and renders, instead of refusing.
        """
        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        self.run_in("snapshot")
        code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        self.assertIn("receipts/issue.json written", out)
        self.assertTrue(list(self.dir.glob("report-*.pdf")), out)
        (self.dir / "receipts" / "issue.json").write_text(
            json.dumps({"report_sha256": "0" * 64, "ledger_sha256": "0" * 64}),
            encoding="utf-8",
        )
        code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        self.assertIn("receipts/issue.json written", out)

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
                Path(output_path).write_bytes(extractable_pdf_bytes())
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

    def test_a_missing_gate_receipt_is_noted_and_render_still_returns(self):
        """R28: tooling/render is a warning — render produces what it can."""
        from contextlib import ExitStack

        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(issue_tests, name, getattr(self, name))
        issue_tests.prepared()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            code, out = self.run_in("issue")
            self.assertEqual(0, code, out)
            (self.dir / "receipts" / "rewild.json").unlink()

            from scripts import md_to_pdf

            def strict_render(input_path, output_path, **kwargs):
                if "rewild_receipt" not in kwargs:
                    raise ValueError("A Rewild gate receipt is required.")
                Path(output_path).write_bytes(extractable_pdf_bytes())

            stack.enter_context(
                mock.patch.object(
                    md_to_pdf, "render_pdf", side_effect=strict_render
                )
            )
            code, out = self.run_in("render")
        self.assertEqual(1, code, out)
        self.assertIn("[tooling/render]", out)
        self.assertIn("=== WARN", out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )["notes"]
        self.assertTrue(any("not rendered" in note for note in notes), notes)


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
        lines = re.findall(r"`([^`]*scripts/alx\.py[^`]*)`", text)
        self.assertGreaterEqual(len(lines), 7, "SKILL.md lost its command lines")
        for line in lines:
            command = line
            for placeholder, value in SKILL_PLACEHOLDERS.items():
                command = command.replace(placeholder, value)
            with self.subTest(command=line):
                self.assertNotIn("$", command)
                parser.parse_args(shlex.split(command))

    def test_skill_md_is_the_core_path_only(self):
        """Recovered SKILL.md: no intake flags; reviews stay optional."""
        text = (
            Path(alx.__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 260)
        for token in ("--dry-run", "--deliver", "--subject-status"):
            self.assertNotIn(token, text)


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
        end = next(
            (i for i, line in enumerate(lines) if line.startswith("=== STATUS:")),
            len(lines),
        )
        return "\n".join(lines[start:end])

    # item 1 --------------------------------------------------------------
    def test_producer_remedies_are_printed_once_and_kept(self):
        rendered = self.rendered(self.item())
        self.assertEqual(1, rendered.count("alx find S1 1916"), rendered)
        self.assertEqual(1, rendered.count("alx claim drop C1 --apply"), rendered)
        self.assertNotIn("alx find S1 C1", rendered)

    def test_a_producer_set_field_synthesis_completes_to_ledger_merge(self):
        rendered = self.rendered(
            self.item(
                family="ledger/synthesis",
                severity="warn",
                klass="A",
                ids=["C1"],
                message="C1: synthesis names a missing claim",
                fix="set field synthesis",
                remove="",
            )
        )
        self.assertIn(
            "set field synthesis, then alx ledger merge ledger-patch.json",
            rendered,
        )
        self.assertNotIn("in claims/", rendered)

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
                    "Fix: (edit prose; warning, never blocks)", rendered
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
        ledger = self.ledger()
        ledger["claims"][0]["claim"] = (
            "The archive released 7,777 documents in March 2026."
        )
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, first = self.run_in("check", "--fix")
        self.assertIn("integrity/date-line", first)
        self.assertIn("ledger/quantity", first)
        self.assertNotIn("Fix: alx check --fix", first)
        _code, second = self.run_in("check", "--fix")
        self.assertEqual(self.grouped_block(first), self.grouped_block(second))

    def test_an_unrepairable_date_line_keeps_its_prose_remedy(self):
        """R28: no class label is printed; the prose remedy still is.

        R29: the WARN tier is compact, so the per-item line the remedy lives
        on is printed by `check --verbose`.
        """
        self.bootstrap()
        self.break_the_date_line_and_the_supports()
        _code, out = self.run_in("check", "--fix", "--verbose")
        line = next(
            line for line in self.finding_lines(out) if "Date line" in line
        )
        self.assertIn("(edit prose; warning, never blocks)", line)
        self.assertIn("[integrity/date-line] 1", out)
        self.assertNotIn("waivable by --deliver)", out)

    # item 3 --------------------------------------------------------------
    def test_family_headers_and_the_status_line_carry_the_tier_not_a_class(self):
        """R28: "Class A" is gone from the output; HARD/WARN is the whole story."""
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertRegex(out, r"\[fidelity/cache-detached\] \d+\n")
        self.assertRegex(out, r"=== HARD \d+ \(fix, or alx issue drops them\) ===")
        self.assertRegex(out, r"=== WARN \d+ ===")
        self.assertNotIn("Class A", out)

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
    def test_no_finding_line_is_longer_than_800_characters(self):
        rendered = self.rendered(
            self.item(message="C1: quantity '1916' is uncovered. " + "窗" * 900)
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
        collected = alx.as_findings(
            alx.validate_ledger._offline_probe_findings(
                self.ledger(), self.dir / "sources"
            )
        )
        self.assertTrue(collected, "section (d) dropped T1's payload findings")
        self.assertIn("fidelity/mismatch", {item.family for item in collected})
        # R28: the mismatch is fabrication (F); a changed context only warns.
        self.assertEqual(
            {"fidelity/mismatch": "F", "fidelity/context-changed": "A"}[
                "fidelity/mismatch"
            ],
            next(
                alx.adopted_class(item)
                for item in collected
                if item.family == "fidelity/mismatch"
            ),
        )
        self.assertEqual(
            {"A"},
            {
                alx.adopted_class(item)
                for item in collected
                if item.family == "fidelity/context-changed"
            },
        )
        _code, out = self.run_in("check")
        self.assertIn("[fidelity/mismatch]", out)

    def test_an_online_mismatch_drops_the_claim_it_names(self):
        """C1 restatement of ..._refuses_issue_as_class_f."""
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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertRegex(out, r"dropped C\d+ \(fidelity/mismatch\): ")
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_a_live_unreachable_beyond_quorum_is_a_warning(self):
        """R28: an unreachable source is availability, never a refusal."""
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
        self.assertEqual({"warn"}, {item.severity for item in adopted})
        self.assertTrue(
            any("past the 25% quorum" in item.message for item in adopted), adopted
        )
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.source_fidelity, "check_source_fidelity", return_value=result
                )
            )
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any("unreachable" in note for note in notes["notes"]), notes)

    def test_a_live_unreachable_within_quorum_is_still_a_warning(self):
        """A8: every unverified sampled check is a finding; quorum is the sentence."""
        result = {
            "findings": [],
            "checks": [
                {
                    "status": "unreachable",
                    "claim_id": "C1",
                    "source_id": "S1",
                    "detail": "timeout",
                },
                {"status": "verified", "claim_id": "C2", "source_id": "S2"},
                {"status": "verified", "claim_id": "C3", "source_id": "S3"},
                {"status": "verified", "claim_id": "C4", "source_id": "S4"},
            ],
        }
        findings = alx._online_findings(result)
        adopted = alx.adopt(findings, online=True)
        unverified = [
            item
            for item in adopted
            if item.family == "fidelity/unreachable"
        ]
        self.assertEqual(1, len(unverified), adopted)
        self.assertEqual("warn", unverified[0].severity)
        self.assertEqual("A", unverified[0].klass)
        self.assertEqual("timeout", unverified[0].message)
        self.assertNotIn("past the 25% quorum", unverified[0].message)
        beyond = {
            "findings": [],
            "checks": [
                {
                    "status": "unreachable",
                    "claim_id": "C1",
                    "source_id": "S1",
                    "detail": "timeout",
                },
                {"status": "verified", "claim_id": "C2", "source_id": "S2"},
                {"status": "verified", "claim_id": "C3", "source_id": "S3"},
            ],
        }
        past = [
            item
            for item in alx._online_findings(beyond)
            if item.family == "fidelity/unreachable"
        ]
        self.assertEqual(1, len(past))
        self.assertIn("timeout", past[0].message)
        self.assertIn("past the 25% quorum", past[0].message)


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
        code, out = self.run_in("check", "--verbose")
        # R32: the stale excerpt prints again as a content/check WARN (as at
        # 4a1825c); it informs and never blocks.
        self.assertEqual(0, code, out)
        self.assertIn("cannot be located in the report", out)

    def test_a_missing_citation_asks_for_the_link_not_a_re_review(self):
        self.started_content_review()
        url = self.ledger()["sources"][0]["url"]
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report.replace(f"[recorded in the study]({url})", "recorded in the study"),
            encoding="utf-8",
        )
        code, out = self.run_in("check", "--verbose")
        # R32: the binding gate names the paragraph and content/check prints
        # the missing-citation WARN again (as at 4a1825c); exit stays 0.
        self.assertEqual(0, code, out)
        self.assertIn("no nearby citation", out)
        line = self.line_with(out, "binding/claim-paragraph")
        self.assertIn("] 1", line)

    # item 4 --------------------------------------------------------------
    def test_review_start_prints_every_field_and_prefills_the_whole_form(self):
        """Restates test_review_start_prints_every_field_and_prefills_claim_support.

        The skeleton is the fixed form — every score and check key — and
        `claim_support` starts empty instead of one entry per claim.
        """
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
            "claim_support[]: may stay empty",
        ):
            self.assertIn(token, out)
        note = json.loads(
            (self.dir / "reviews" / "content.json").read_text(encoding="utf-8")
        )
        self.assertEqual([], note["claim_support"])
        self.assertEqual(sorted(alx.CONTENT_SCORE_KEYS), sorted(note["scores"]))
        self.assertEqual(
            [{"score": None, "rationale": ""}] * len(alx.CONTENT_SCORE_KEYS),
            list(note["scores"].values()),
        )
        self.assertEqual(sorted(alx.CONTENT_CHECK_KEYS), sorted(note["checks"]))
        self.assertEqual({False}, set(note["checks"].values()))

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
        self.assertEqual(0, code, out)
        self.assertTrue(self.state()["reviews"]["content"]["finished"])
        for path in (
            "scores.question_answered.score",
            "scores.question_answered.rationale",
            "checks.central_judgment_answers_question",
            "section_reviews",
            "completion_note",
        ):
            with self.subTest(path=path):
                self.assertIn(f"WARN review/content: {path}", out)
        # The list is the fixed form, never one line per claim.
        self.assertNotIn("claim_support[C1]", out)

    def test_a_producer_remedy_names_the_real_claim_file(self):
        rendered = alx.render_grouped(
            alx.adopt(
                [
                    alx.Finding(
                        family="ledger/reference",
                        severity="hard",
                        klass="F",
                        ids=["C1", "P3"],
                        message=(
                            "C1: claim names registered person P3 but does "
                            "not link that person_id."
                        ),
                        fix=(
                            "set field person_ids in claims/*.json, "
                            "then alx claim add claims/*.json"
                        ),
                        remove="",
                    )
                ],
                claim_files={"C1": "claims/c1.json"},
            )
        )
        self.assertIn(
            "set field person_ids in claims/c1.json, "
            "then alx claim add claims/c1.json",
            rendered,
        )
        self.assertNotIn("set field supports", rendered)

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
        self.assertIn(
            "Fix: write [C2] at the end of the sentence in paragraph", line
        )
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
        self.assertIn("Fix: (edit prose; warning, never blocks)", rendered)
        self.assertNotIn("Remove:", rendered)
        self.assertNotIn("alx check", rendered)

    def test_a_line_with_no_budget_left_still_cuts_its_message(self):
        """Minor 2: the ids and the remedy may overrun; the message may not."""
        body = alx._fit(
            "m" * 500,
            [f"C{number}" for number in range(1, 200)],
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
        # One line binds every unbound claim: `alx claim bind C1:3 C4:15`.
        printed = re.search(r"Fix: (alx claim bind C1:(\d+)(?: C\d+:\d+)*)", ambiguous)
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
            code, out = self.run_in("fetch", "--id", "S1")
        self.assertEqual(0, code, out)

    def test_context_changed_is_reported_with_the_two_step_remedy(self):
        self.stale_context()
        _code, out = self.run_in("check")
        self.assertIn("[fidelity/context-changed]", out)
        line = self.line_with(out, "context changed")
        # K5: the remedy names the file C1 came from, not an unexpanded glob.
        self.assertIn(
            "Fix: alx fetch --id S1, then alx claim add "
            f"{self.state()['claim_files']['C1']}",
            line,
        )
        # R28: fidelity/context-changed is a warning, so it carries no
        # scope-dropping Remove remedy.
        self.assertNotIn("Remove:", line)

    def test_the_two_step_remedy_clears_the_context_finding(self):
        self.stale_context()
        with mock_production_transport(responses(CHANGED_PAGE)):
            self.run_in("fetch", "--id", "S1")
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
        self.pad_report()
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
    def test_a_live_mismatch_writes_no_fidelity_receipt(self):
        """C1 restatement of ..._never_reaches_a_receipt: the mismatch drops
        the claim it names and `issue` finishes; the live receipt, which a
        standing mismatch withholds, is the only thing missing."""
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(stack, [self.mismatch_result()])
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertIn("dropped C2 (fidelity/mismatch)", out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())
        self.assertNotIn("C2", {claim["claim_id"] for claim in self.ledger()["claims"]})
        self.assertIn(
            "C2", {claim["claim_id"] for claim in self.ledger()["excluded_claims"]}
        )
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
            code, out = self.run_in("issue", "--live")
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

    def test_the_auto_drop_prints_one_line_and_one_worklog_entry(self):
        """H1: the auto-drop reports what it did; it is not a remedy to run."""
        from contextlib import ExitStack

        issue_tests = self.helper()
        issue_tests.prepared()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(
                stack, [self.mismatch_result(), self.passed_result()]
            )
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        drops = [line for line in out.splitlines() if line.startswith("dropped ")]
        self.assertEqual(1, len(drops), out)
        self.assertRegex(drops[0], r"^dropped C2 \(fidelity/mismatch\): .+")
        self.assertNotIn("alx claim drop", out)
        worklog = (self.dir / "worklog.md").read_text(encoding="utf-8").splitlines()
        auto = [line for line in worklog if "auto-drop" in line]
        self.assertEqual(1, len(auto), worklog)
        self.assertTrue(auto[0].endswith("issue auto-drop C2"), auto[0])

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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertFalse((self.dir / "receipts" / "source-fidelity.json").exists())

    # J5 ------------------------------------------------------------------
    def test_deliver_rechecks_after_an_online_drop_and_issues_survivors(self):
        """R28 restatement of ..._and_refuses_survivors.

        The survivor's `supports` still names the dropped claim, but
        ledger/excluded-supports is a WARN now, so the recheck issues instead
        of refusing. The drop itself is still applied and still reported.
        """
        from contextlib import ExitStack

        self.prepared_with_supporter()
        issue_tests = self.helper()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            self.live_sequence(
                stack, [self.mismatch_result(), self.passed_result()]
            )
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertIn("dropped C2 (", out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

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
        self.assertEqual(0, code, out)
        self.assertNotEqual(before["at"], self.state()["last_check"]["at"])

    def test_render_keeps_the_companion_past_the_reserve(self):
        """Restates test_render_drops_the_companion_inside_the_reserve (B5).

        The J7 skip is gone: the rasterizer keeps its own 90 s cap, so both
        templates are rendered however little of the budget is left.
        """
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        issue_tests = self.helper()
        issue_tests.prepared()
        rendered = []

        def fake_render_pdf(input_path, output_path, **kwargs):
            rendered.append(kwargs.get("template"))
            Path(output_path).write_bytes(extractable_pdf_bytes())
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
        self.assertEqual(["executive", "atlas"], rendered)
        self.assertNotIn("tooling/render", out)

    # J10 -----------------------------------------------------------------
    def test_a_recorded_online_failure_keeps_its_verification_note(self):
        """R28: nothing is aborted, so the note that records it stays in."""
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
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(alx.VERIFICATION_NOTE_PREFIX["en"], report)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )
        self.assertTrue(
            any("source-fidelity receipt not issued" in note for note in notes["notes"]),
            notes,
        )


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


class RewildEffectiveSnapshotTests(AlxTestCase):
    """Ruling R11: the Rewild receipt is taken against the EFFECTIVE snapshot.

    `claim drop --apply` deletions are mechanical (spec §6.8), so a quotation
    that only ever lived in a dropped paragraph is not a lost quotation. A
    quotation lost from a surviving paragraph still is.
    """

    QUOTE = "\u300c\u767b\u8a18\u518a\u8a18\u9304\u300d"

    def prepared_with_quote(self):
        """bootstrap + a quotation inside C2's paragraph, snapshotted."""
        self.bootstrap()
        self.run_in("check", "--fix")
        path = self.dir / "report.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "as the [registry note]",
                f"as {self.QUOTE} in the [registry note]",
            ),
            encoding="utf-8",
        )
        self.pad_report()
        self.run_in("snapshot")
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("dir", "root", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        reviews.finish_reviews()

    def quotation_gate(self, stack, seen):
        """Replace the Rewild gate with its real quotation tier only."""
        def gate(report_path, source_path, **kwargs):
            seen["source"] = Path(source_path)
            lost = alx.rewild_gate._quotation_findings(
                Path(source_path).read_text(encoding="utf-8"),
                Path(report_path).read_text(encoding="utf-8"),
            )
            if lost:
                return [item.message for item in lost]
            Path(kwargs["receipt_path"]).write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "report_sha256": alx.file_sha256(self.dir / "report.md"),
                        "ledger_sha256": alx.file_sha256(self.dir / "ledger.json"),
                        "source_sha256": alx.file_sha256(source_path),
                        "snapshot_sha256": kwargs.get("snapshot_sha256"),
                    }
                ),
                encoding="utf-8",
            )
            return []

        stack.enter_context(
            mock.patch.object(alx.rewild_gate, "run_gate", side_effect=gate)
        )

    def test_a_dropped_paragraph_s_quotation_does_not_refuse_the_receipt(self):
        from contextlib import ExitStack

        self.prepared_with_quote()
        code, out = self.run_in("claim", "drop", "C2", "--apply")
        self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(self.QUOTE, report)
        snapshot = self.dir / "report.pre-rewild.md"
        self.assertIn(self.QUOTE, snapshot.read_text(encoding="utf-8"))
        seen = {}
        with ExitStack() as stack:
            issues = IssueTests("test_issue_writes_receipts_and_verification_note")
            issues.dir = self.dir
            issues.stub_gates(stack, rewild=False)
            self.quotation_gate(stack, seen)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertEqual("snapshot.effective.md", seen["source"].name)
        self.assertNotIn(self.QUOTE, seen["source"].read_text(encoding="utf-8"))
        receipt = json.loads(
            (self.dir / "receipts" / "rewild.json").read_text(encoding="utf-8")
        )
        self.assertEqual(alx.file_sha256(seen["source"]), receipt["source_sha256"])
        self.assertEqual(alx.file_sha256(snapshot), receipt["snapshot_sha256"])
        note = json.loads(
            (self.dir / "reviews" / "rewild.json").read_text(encoding="utf-8")
        )
        self.assertEqual(alx.file_sha256(seen["source"]), note["source_sha256"])

    def test_a_quotation_lost_from_a_surviving_paragraph_is_restored(self):
        """C1 restatement of ..._still_refuses: the Remove remedy of a lost
        quotation is the snapshot restore, and `issue` applies it itself."""
        from contextlib import ExitStack

        self.prepared_with_quote()
        code, out = self.run_in("claim", "drop", "C2", "--apply")
        self.assertEqual(0, code, out)
        path = self.dir / "report.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "\u300c\u539f\u59cb\u65e5\u8a18\u300d", "the original diaries"
            ),
            encoding="utf-8",
        )
        seen = {}
        with ExitStack() as stack:
            issues = IssueTests("test_issue_writes_receipts_and_verification_note")
            issues.dir = self.dir
            issues.stub_gates(stack, rewild=False)
            self.quotation_gate(stack, seen)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertIn("restored from the latest snapshot", out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())


class ParkedReviewNoteTests(AlxTestCase):
    """Item 4 leftovers: every invalid note path is named, nothing is guessed."""

    def test_the_missing_list_is_the_form_not_one_line_per_claim(self):
        """Restates test_finish_names_the_empty_claim_support_note and
        test_an_unbound_claim_is_prefilled_null_and_named_by_finish.

        Neither an empty nor an unbound claim_support entry exists any more:
        an untouched skeleton owes the fixed form and nothing else.
        """
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertNotIn("claim_support", out)
        missing = alx._note_completeness(
            alx.Workspace(self.dir), self.state(), self.ledger(), "content"
        )
        # score/rationale per score key + one per check key + section_reviews
        # + completion_note: the form, whatever the claim count. `status` is
        # no longer among them — `finish` writes it itself (B6).
        own = [item for item in missing if "(content-review schema)" not in item]
        self.assertEqual(
            2 + 2 * len(alx.CONTENT_SCORE_KEYS) + len(alx.CONTENT_CHECK_KEYS),
            len(own),
            own,
        )
        self.assertNotIn("status", out)
        paths = [item.split(":", 1)[0].split()[0] for item in missing]
        self.assertEqual(len(paths), len(set(paths)), paths)

    def test_review_start_prints_the_rewild_guide(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        code, out = self.run_in("review", "start", "rewild")
        self.assertEqual(0, code, out)
        self.assertIn("Fill reviews/rewild.json", out)
        self.assertIn("fidelity_checks.<key>: true | false; all must be true", out)
        for name in sorted(alx.rewild_gate.REQUIRED_FIDELITY_CHECKS):
            with self.subTest(check=name):
                self.assertIn(name, out)
        self.assertIn("disposition resolved|rejected", out)
        self.assertIn("alx review finish rewild", out)


class ClaimInputRoundTripTests(AlxTestCase):
    """Spec §10/§6.4: one round-trip per conditional claim-input path."""

    EXTRACT = (
        "Retention rose to 88 percent after the second review round, "
        "the registry reported."
    )

    def setUp(self):
        super().setUp()
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("first.json", [CLAIM_ONE])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)

    def fixture(self, claim_id, **extra):
        item = {
            "claim_id": claim_id,
            "claim": "Retention rose to 88 percent after the second review round.",
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S1", "extract_or_location": self.EXTRACT}
            ],
        }
        item.update(extra)
        return item

    def claim_schema(self):
        schema = json.loads(
            alx.validate_ledger.DEFAULT_SCHEMA.read_text(encoding="utf-8")
        )
        return {"$defs": schema["$defs"], "$ref": "#/$defs/claim"}

    def round_trip(self, item):
        path = self.write_json(f"{item['claim_id']}.json", [item])
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(0, code, out)
        claim = next(
            entry
            for entry in self.ledger()["claims"]
            if entry["claim_id"] == item["claim_id"]
        )
        self.assertEqual(
            [],
            alx.validate_ledger.validate_schema(claim, self.claim_schema()),
        )
        for key, value in item.items():
            self.assertEqual(value, claim[key])
        return claim

    def missing_key_is_accepted(self, item, key):
        """R28 restatement of missing_key_is_named.

        Every conditional claim-input field is optional, so dropping one is
        accepted outright rather than raising ledger/claim-input.
        """
        broken = {name: value for name, value in item.items() if name != key}
        path = self.write_json("broken.json", [broken])
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(0, code, out)
        self.assertNotIn("[ledger/claim-input]", out)

    def test_analysis_claim_round_trips_without_reasoning(self):
        item = self.fixture(
            "C10",
            kind="analysis",
            reasoning=(
                "The second review round is the only change between the two "
                "retention figures."
            ),
        )
        self.round_trip(item)
        self.missing_key_is_accepted(item, "reasoning")

    def test_estimate_claim_round_trips_without_assumptions(self):
        item = self.fixture(
            "C11",
            kind="estimate",
            assumptions=[
                "The review round applied one retention rule to every file."
            ],
        )
        self.round_trip(item)
        self.missing_key_is_accepted(item, "assumptions")

    def test_response_role_round_trips_without_responds_to(self):
        item = self.fixture(
            "C12",
            responds_to_claim_ids=["C1"],
        )
        self.round_trip(item)
        self.missing_key_is_accepted(item, "responds_to_claim_ids")

    def test_resolution_role_round_trips_without_resolves(self):
        item = self.fixture(
            "C13",
            resolves_claim_ids=["C1"],
        )
        self.round_trip(item)
        self.missing_key_is_accepted(item, "resolves_claim_ids")

    def test_an_accountable_source_claim_round_trips(self):
        code, out = self.run_in(
            "source", "set", "S1", "--accountability", "court_or_regulator_record"
        )
        self.assertEqual(0, code, out)
        source = next(
            entry for entry in self.ledger()["sources"] if entry["source_id"] == "S1"
        )
        self.assertEqual("court_or_regulator_record", source["accountability_basis"])
        claim = self.round_trip(self.fixture("C14"))
        self.assertEqual(["S1"], claim["source_ids"])


NINE_SENTENCES = (
    "The archive published the reading room rules for named researchers.",
    "The registry recorded the transfer of the papers to the reading room.",
    "The archive asked the registry to confirm each finding aid entry.",
    "The reading room admits researchers who carry a named sponsor letter.",
    "The registry keeps a separate index of the transferred boxes.",
    "The archive trains its staff on the handling of fragile paper.",
    "The registry publishes a monthly note on its cataloguing work.",
    "The archive stores the original wrappers with the catalogued boxes.",
    "The reading room closes for one week of conservation each spring.",
)


def _nine_page(sentences):
    """One page per claim, padded so each probe context stands alone.

    `PROBE_CONTEXT_RADIUS` is 500 characters, so the filler between two
    sentences keeps the removal of the last one out of its neighbour's
    recorded context (spec §7.2.6).
    """
    parts = ["<html><head><title>Reading Room</title></head><body>"]
    for index, sentence in enumerate(sentences):
        parts.append(f"<p>{sentence}</p>")
        parts.append("<p>" + f"Filler line {index} for the reading room. " * 24 + "</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


class RefreshedSourceReprobeTests(AlxTestCase):
    """Spec §10/§6.9.2: a refreshed source re-probes every claim it carries."""

    URL = "https://example.org/study"

    def responses_for(self, page):
        return {"example.org": (200, {"content-type": "text/html"}, page.encode("utf-8"))}

    def claim(self, index):
        sentence = NINE_SENTENCES[index]
        item = {
            "claim_id": f"C{index + 1}",
            "claim": sentence,
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S1", "extract_or_location": sentence}
            ],
        }
        if index == 0:
            item["importance"] = "key"
            item["decision_relevance"] = "The rules decide who may read the papers."
            item["what_would_change"] = "A published rule admitting unnamed readers."
        return item

    def draft(self):
        date_line = alx.report_contract.localized_date("en", None)
        body = "\n\n".join(
            f"{sentence} The study [records this]({self.URL}) for the reading room."
            for sentence in NINE_SENTENCES
        )
        text = (
            "# Reading Room\n\n"
            "> How the archive and the registry run the reading room.\n"
            f"> {date_line}\n\n"
            "## Findings\n\n"
            f"{body}\n\n"
            "## Sources\n\n"
            f"- [Reading Room]({self.URL})\n"
        )
        (self.dir / "report.md").write_text(text, encoding="utf-8")

    def prepared(self):
        self.init()
        with mock_production_transport(self.responses_for(_nine_page(NINE_SENTENCES))):
            code, out = self.run_in("fetch", self.URL)
        self.assertEqual(0, code, out)
        code, out = self.run_in(
            "source", "set", "S1", "--provenance", "primary_independent"
        )
        self.assertEqual(0, code, out)
        batch = self.write_json(
            "nine.json", [self.claim(index) for index in range(len(NINE_SENTENCES))]
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.draft()
        for index in range(len(NINE_SENTENCES)):
            code, out = self.run_in(
                "claim", "bind", f"C{index + 1}", "--paragraph", str(index + 1)
            )
            self.assertEqual(0, code, out)
        patch = self.write_json("coverage.json", self.coverage_patch())
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        code, out = self.run_in("check", "--fix")
        self.pad_report()
        self.run_in("snapshot")
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("dir", "root", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        reviews.finish_reviews()

    def coverage_patch(self):
        ids = [f"C{index + 1}" for index in range(len(NINE_SENTENCES))]
        return {
            "coverage": [
                {
                    "area": "reading room",
                    "question": "How is access to the reading room governed?",
                    "priority": "high",
                    "decision_relevance": "Access decides who can verify the papers.",
                    "completion_criteria": "The published rules are recorded.",
                    "status": "supported",
                    "claim_ids": ids,
                    "gap_impact": None,
                }
            ],
            "synthesis": {
                "central_judgment_claim_ids": ["C1"],
                "counterevidence_claim_ids": [],
                "adversarial_tests": [
                    {
                        "hypothesis": "The reading room admits unnamed readers.",
                        "test": "Read the published rules for the reading room.",
                        "claim_ids": ["C1"],
                        "outcome": "rejected",
                        "result": "The rules name the sponsor requirement.",
                        "effect_on_conclusion": "The access claim stands.",
                    }
                ],
                "implications": [
                    {
                        "statement": "Verification needs a named sponsor letter.",
                        "claim_ids": ["C1"],
                        "for_whom": "Archive researchers",
                        "timing": "Immediately",
                    }
                ],
                "decisions_or_takeaways": [
                    {
                        "statement": "Apply for a sponsor letter before travelling.",
                        "rationale_claim_ids": ["C1"],
                        "tradeoff": "The letter takes time to obtain.",
                        "success_signal": "Readers are admitted on arrival.",
                        "failure_signal": "Readers are turned away at the door.",
                    }
                ],
                "scenarios": [],
                "limitations": ["Only the archive's own page was available."],
                "research_stop_reason": "The published rules answer the question.",
            },
        }

    def stub_gates(self, stack):
        """Only the two gates; the live fidelity pass must stay real."""

        def bound(payload):
            payload = dict(payload)
            payload["report_sha256"] = alx.file_sha256(self.dir / "report.md")
            payload["ledger_sha256"] = alx.file_sha256(self.dir / "ledger.json")
            return json.dumps(payload)

        def fake_rewild(*args, **kwargs):
            Path(kwargs["receipt_path"]).write_text(
                bound({"status": "passed"}), encoding="utf-8"
            )
            return []

        def fake_content(report_path, ledger_path, note_path, receipt_path, **kwargs):
            Path(receipt_path).write_text(bound({"status": "passed"}), encoding="utf-8")
            return []

        stack.enter_context(
            mock.patch.object(alx.rewild_gate, "run_gate", side_effect=fake_rewild)
        )
        stack.enter_context(
            mock.patch.object(
                alx.content_gate, "run_content_gate", side_effect=fake_content
            )
        )

    def changed_page(self):
        """The live page loses the sentence C9 quotes; C1 (sampled) survives."""
        return _nine_page(NINE_SENTENCES[:-1])

    def issue(self, stack, *extra):
        self.stub_gates(stack)
        stack.enter_context(
            mock_production_transport(self.responses_for(self.changed_page()))
        )
        return self.run_in("issue", "--live", "--sample-size", "1", *extra)

    def test_a_claim_outside_the_sample_is_dropped_by_issue(self):
        """C1 restatement of ..._blocks_issue."""
        from contextlib import ExitStack

        self.prepared()
        with ExitStack() as stack:
            code, out = self.issue(stack)
        self.assertEqual(0, code, out)
        # The live sample covered C1 only; C9 is caught by the re-probe that
        # the refreshed cache triggers.
        result = json.loads(
            (self.dir / ".alx" / "fidelity-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"C1"}, {check["claim_id"] for check in result["checks"]})
        self.assertIn("1 source(s) refreshed", out)
        self.assertIn("C9", out)
        self.assertNotIn("C8", out)
        self.assertIn("dropped C9 (fidelity/mismatch)", out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_deliver_drops_the_claim_outside_the_sample(self):
        from contextlib import ExitStack

        self.prepared()
        with ExitStack() as stack:
            code, out = self.issue(stack)
        self.assertEqual(0, code, out)
        surviving = {claim["claim_id"] for claim in self.ledger()["claims"]}
        self.assertNotIn("C9", surviving)
        self.assertEqual(8, len(surviving))
        self.assertIn(
            "C9", {claim["claim_id"] for claim in self.ledger()["excluded_claims"]}
        )
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(NINE_SENTENCES[-1], report)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())


class VerificationNotePdfTests(AlxTestCase):
    """Spec §10/§6.9.3: the machine-written note survives into both PDFs."""

    def pdf_text(self, path):
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def test_the_note_reaches_both_pdfs_with_matching_issue_hashes(self):
        from contextlib import ExitStack

        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
        ):
            setattr(issue_tests, name, getattr(self, name))
        issue_tests.prepared()
        with ExitStack() as stack:
            # Step 2 reports a central judgment it could not re-read live, so
            # step 3 has a non-empty note to write (spec §6.9.3).
            issue_tests.stub_gates(
                stack,
                online={
                    "status": "passed",
                    "checks": [],
                    "refreshed_source_ids": [],
                    "disclosure_required": ["C1"],
                },
            )
            code, out = self.run_in("issue", "--live")
            self.assertEqual(0, code, out)
            code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(alx.VERIFICATION_NOTE_PREFIX["en"], report)
        receipt = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertEqual(alx.file_sha256(self.dir / "report.md"), receipt["report_sha256"])
        self.assertEqual(
            alx.file_sha256(self.dir / "ledger.json"), receipt["ledger_sha256"]
        )
        self.assertTrue(
            any(
                "central-judgment evidence not re-read live" in note
                for note in receipt["delivery_notes"]
            ),
            receipt["delivery_notes"],
        )
        pdfs = sorted(self.dir.glob("report-*.pdf"))
        self.assertEqual(2, len(pdfs), pdfs)


if __name__ == "__main__":
    unittest.main()


class FileArgumentTests(AlxTestCase):
    """J1 / D10: every FILE-typed argument is a path, validated before the run.

    Prose passed inline used to reach `Path(...).read_text` and traceback with
    `FileNotFoundError`; it must be one line and exit 2.
    """

    PROSE = "OAC finding aid is a living catalog record, not a dated publication."

    def assert_refused(self, flag, code, out):
        self.assertEqual(2, code, out)
        # C3: restated for the message that names both locations tried.
        self.assertIn(f"{flag}: no file at ", out)
        self.assertIn(" nor at ", out)
        self.assertIn(f"(cwd {Path.cwd()})", out)
        self.assertNotIn("Traceback", out)

    def test_init_refuses_prose_for_subject_and_reader(self):
        code, out = self.run_alx(
            "init", self.dir, "--lang", "en", "--subject", self.PROSE
        )
        self.assert_refused("--subject", code, out)
        subject = self.root / "subject.txt"
        subject.write_text("Ledger Study\n", encoding="utf-8")
        code, out = self.run_alx(
            "init",
            self.dir,
            "--lang",
            "en",
            "--subject",
            subject,
            "--reader",
            self.PROSE,
        )
        self.assert_refused("--reader", code, out)

    def test_source_set_refuses_prose_for_both_file_flags(self):
        self.init()
        self.fetch("https://example.org/study")
        for flag in ("--undated-reason", "--family-justification"):
            with self.subTest(flag=flag):
                code, out = self.run_in("source", "set", "S1", flag, self.PROSE)
                self.assert_refused(flag, code, out)

    def test_claim_add_and_ledger_merge_refuse_prose_paths(self):
        self.init()
        code, out = self.run_in("claim", "add", self.PROSE)
        self.assert_refused("FILE", code, out)
        code, out = self.run_in("ledger", "merge", self.PROSE)
        self.assert_refused("PATCH", code, out)


ZH_SENTENCE = "档案馆在三月公开了一千二百零四件文件，登记处也确认了同一数字。"


def zh_report(paragraphs):
    date_line = alx.report_contract.localized_date("zh-CN", None)
    body = "\n\n".join(
        "".join(ZH_SENTENCE for _ in range(6)) for _ in range(paragraphs)
    )
    return (
        "# 档案研究\n\n"
        "> 档案公开是否与登记处的统计一致。\n"
        f"> {date_line}\n\n"
        "## 发现\n\n"
        f"{body}\n\n"
        "## 来源\n\n"
        "- [档案研究](https://example.org/study)\n"
    )


class ReportLengthTests(AlxTestCase):
    """Ruling R12: one length definition for every consumer.

    `report_blocks.report_length` is the only counter; `validate_report`'s
    integrity check, `rewild_gate`'s floor and `alx check` all quote it, so a
    report can never be long enough for one gate and short for another.
    """

    def test_six_thousand_character_zh_report_passes_both_length_checks(self):
        text = zh_report(32)
        count, unit = alx.report_blocks.report_length(text, "zh-CN")
        self.assertEqual("report-body characters", unit)
        self.assertGreaterEqual(count, 5000)
        self.assertLessEqual(count, 10000)
        ledger = {"report_date": "2026-09-14", "brief": {"report_language": "zh-CN"}}
        families = [
            item.family
            for item in alx.validate_report.integrity_findings(
                text, ledger, lang="zh-CN"
            )
        ]
        self.assertNotIn("integrity/length", families)
        self.assertEqual([], alx.rewild_gate._length_errors(text, "zh-CN"))

    def test_a_short_zh_report_fails_both_with_the_same_count(self):
        text = zh_report(2)
        count, unit = alx.report_blocks.report_length(text, "zh-CN")
        self.assertLess(count, 5000)
        messages = [
            item.message
            for item in alx.validate_report.integrity_findings(
                text,
                {"report_date": "2026-09-14", "brief": {"report_language": "zh-CN"}},
                lang="zh-CN",
            )
            if item.family == "integrity/length"
        ]
        self.assertTrue(any(f"{count} {unit}" in item for item in messages), messages)
        rewild = alx.rewild_gate._length_errors(text, "zh-CN")
        self.assertTrue(any(f"{count} {unit}" in item for item in rewild), rewild)

    def test_check_prints_the_same_count_unit_and_band(self):
        self.bootstrap()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        count, unit = alx.report_blocks.report_length(report, "en")
        _code, out = self.run_in("check")
        self.assertIn(f"length {count} {unit}; floor 7500, ceiling 15000", out)


class ReviewNoteFloorTests(AlxTestCase):
    """J3: `review finish` keeps the full floor for non-CJK review prose."""

    def note(self, text):
        return {
            "section_reviews": [
                {
                    "section_heading": "Findings",
                    "purpose": "Advance the report's governing question fully.",
                    "new_value": "Adds distinct evidence and decision value.",
                    "evidence_or_reasoning": "Supported by the bound ledger.",
                    "limitation_or_tradeoff": text,
                    "contribution_to_governing_question": "Moves to the judgment.",
                    "disposition": "keep",
                }
            ]
        }

    def test_chinese_note_passes_and_english_of_the_same_length_does_not(self):
        self.assertEqual([], alx._prose_floor_missing(self.note("1915年残13天没有逐日表。"), "content"))
        missing = alx._prose_floor_missing(self.note("Thin, unusable"), "content")
        self.assertTrue(
            any("threshold 20, actual 14" in item for item in missing), missing
        )
        self.assertTrue(
            all("content-review schema" in item for item in missing), missing
        )


class DropIdentityTests(AlxTestCase):
    """K3: a drop deletes the paragraph the binding meant, not its twin."""

    def twin_report(self):
        """Paragraphs 1 and 2 read alike and differ only by their citation."""
        ledger = self.ledger()
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        sentence = (
            "The archive released 1,204 documents in March 2026, a release "
            "[recorded in the study]({url}) that the registry confirmed."
        )
        text = (
            "# Ledger Study\n\n"
            "> Whether the archive release matches the registry tally.\n"
            f"> {alx.report_contract.localized_date('en', None)}\n\n"
            "## Findings\n\n"
            f"{sentence.format(url=first)}\n\n"
            f"{sentence.format(url=second)}\n\n"
            "The reading room keeps 「原始日記」 under restricted access, "
            "so the counts above are the only public record.\n\n"
            "## Sources\n\n"
            f"- [Ledger Study]({first})\n"
            f"- [Registry Note]({second})\n"
        )
        (self.dir / "report.md").write_text(text, encoding="utf-8")
        return first, second

    def test_the_twin_paragraph_of_the_dropped_claim_survives(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        first, second = self.twin_report()
        for claim_id, number in (("C1", 1), ("C2", 2)):
            code, out = self.run_in("claim", "bind", claim_id, "--paragraph", number)
            self.assertEqual(0, code, out)
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        code, out = self.run_in("claim", "drop", "C2", "--apply")
        self.assertEqual(0, code, out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(f"[recorded in the study]({first})", report)
        self.assertNotIn(f"[recorded in the study]({second})", report)
        _code, out = self.run_in("check")
        self.assertNotIn("binding/leftover-prose", out)
        code, out = self.run_in("snapshot", "--restore")
        self.assertEqual(0, code, out)
        restored = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(f"[recorded in the study]({first})", restored)
        self.assertNotIn(f"[recorded in the study]({second})", restored)

    def test_a_standfirst_that_clones_paragraph_one_is_never_deleted(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        first, _second = self.twin_report()
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        clone = (
            "The archive released 1,204 documents in March 2026, a release "
            f"[recorded in the study]({first}) that the registry confirmed."
        )
        report = report.replace(
            "> Whether the archive release matches the registry tally.",
            f"> {clone}",
            1,
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        code, out = self.run_in("claim", "bind", "C1", "--paragraph", 1)
        self.assertEqual(0, code, out)
        code, out = self.run_in("claim", "drop", "C1", "--apply")
        self.assertEqual(0, code, out)
        dropped = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(f"> {clone}", dropped)
        self.assertEqual(1, dropped.count(clone))


class ClaimFileRemedyTests(AlxTestCase):
    """K5: the printed context-changed remedy runs verbatim."""

    def fix_round(self):
        helper = FixRoundTests("test_context_changed_is_reported_with_the_two_step_remedy")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "assertEqual", "assertIn",
        ):
            setattr(helper, name, getattr(self, name))
        return helper

    def test_the_printed_remedy_clears_the_finding_when_run_verbatim(self):
        helper = self.fix_round()
        helper.stale_context()
        _code, out = self.run_in("check")
        line = next(item for item in out.splitlines() if "context changed" in item)
        printed = line.split("Fix: ")[1].split(". Remove:")[0].rstrip(".")
        first, second = printed.split(", then ")
        with mock_production_transport(responses(CHANGED_PAGE)):
            code, out = self.run_in(*shlex.split(first)[1:])
        self.assertEqual(0, code, out)
        code, out = self.run_in(*shlex.split(second)[1:])
        self.assertEqual(0, code, out)
        _code, out = self.run_in("check")
        self.assertNotIn("fidelity/context-changed", out)

    def test_claim_add_expands_an_unexpanded_glob(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.root / "claims"
        batch.mkdir()
        (batch / "one.json").write_text(json.dumps([CLAIM_ONE]), encoding="utf-8")
        (batch / "two.json").write_text(json.dumps([CLAIM_TWO]), encoding="utf-8")
        code, out = self.run_in("claim", "add", f"{batch}/*.json")
        self.assertEqual(0, code, out)
        self.assertEqual(
            ["C1", "C2"],
            [claim["claim_id"] for claim in self.ledger()["claims"]],
        )


class AccountabilityNoteTests(AlxTestCase):
    """K2: the note floor prints a command that can set the note."""

    def short_note(self):
        self.bootstrap()
        ledger = self.ledger()
        ledger["sources"][0]["accountability_note"] = "a named research desk"
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )

    def test_source_set_writes_the_note_and_clears_the_finding(self):
        self.short_note()
        path = self.root / "accountability-note.txt"
        path.write_text(
            "The study is signed by its named research desk, which corrects "
            "its own record in public.\n",
            encoding="utf-8",
        )
        code, out = self.run_in("source", "set", "S1", "--accountability-note", path)
        self.assertEqual(0, code, out)
        self.assertIn(
            "named research desk",
            self.ledger()["sources"][0]["accountability_note"],
        )
        _code, out = self.run_in("check")
        self.assertNotIn("accountability_note must say", out)

    def test_the_floor_remedy_names_the_flag_and_the_real_id(self):
        self.short_note()
        _code, out = self.run_in("check")
        line = next(item for item in out.splitlines() if "accountability_note" in item)
        self.assertIn(
            "Fix: alx source set S1 --accountability-note accountability-note.txt",
            line,
        )


class ReserveReceiptTests(AlxTestCase):
    """K1/K4: what the §6.11 reserve skip may destroy, and what it owes."""

    def issue_helper(self):
        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
        ):
            setattr(helper, name, getattr(self, name))
        return helper

    def test_the_reserve_skip_keeps_a_valid_fidelity_receipt(self):
        from contextlib import ExitStack

        helper = self.issue_helper()
        helper.prepared()
        receipt = self.dir / "receipts" / "source-fidelity.json"
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue", "--live")
            self.assertEqual(0, code, out)
            self.assertTrue(receipt.exists(), out)
            self.set_remaining(2)
            code, out = self.run_in("issue", "--live")
        self.assertEqual(0, code, out)
        self.assertTrue(receipt.exists())
        issued = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertIn("source-fidelity", issued["receipts"])
        self.assertFalse(
            any("re-check skipped" in note for note in issued["delivery_notes"]),
            issued["delivery_notes"],
        )

    def test_the_content_gate_runs_without_a_fidelity_receipt(self):
        from contextlib import ExitStack

        helper = self.issue_helper()
        helper.prepared()
        errors = []
        real_gate = alx.content_gate.run_content_gate

        def real(*args, **kwargs):
            """K4: the content gate itself, never a stub."""
            result = real_gate(*args, **kwargs)
            errors.append(result)
            return result

        with ExitStack() as stack:
            helper.stub_gates(stack)
            stack.enter_context(
                mock.patch.object(
                    alx.content_gate, "run_content_gate", side_effect=real
                )
            )
            self.set_remaining(2)
            code, out = self.run_in("issue", "--offline")
        self.assertEqual(0, code, out)
        self.assertEqual([[]], errors)
        self.assertFalse((self.dir / "receipts" / "source-fidelity.json").exists())
        content = self.dir / "receipts" / "content.json"
        self.assertTrue(content.exists())
        self.assertTrue(
            json.loads(content.read_text(encoding="utf-8"))[
                "source_fidelity_receipt_skipped"
            ]
        )
        issued = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertIn("content", issued["receipts"])
        self.assertIn(
            "content receipt issued without a source-fidelity receipt: "
            "live fidelity never ran",
            issued["delivery_notes"],
        )


class RenderDegradeTests(AlxTestCase):
    """K6 (D4b): every rasterizer backend failed; the delivery still stands."""

    def issued(self, stack):
        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        helper.stub_gates(stack)
        code, out = self.run_in("issue")
        self.assertEqual(0, code, out)

    def test_a_failed_rasterizer_keeps_both_pdfs_and_notes_the_loss(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        with ExitStack() as stack:
            self.issued(stack)

            def fake_render_pdf(input_path, output_path, **kwargs):
                Path(output_path).write_bytes(extractable_pdf_bytes())
                return Path(output_path)

            def dead_rasterizer(pdf_path, output_dir, **kwargs):
                raise RuntimeError("every rasterizer backend failed")

            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=dead_rasterizer
                )
            )
            code, out = self.run_in("render")
        self.assertEqual(0, code, out)
        self.assertEqual(2, len(list(self.dir.glob("report-*.pdf"))))
        self.assertIn("tooling/render", out)
        self.assertNotIn("contact sheet: ", out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )["notes"]
        self.assertEqual(
            2, sum(1 for note in notes if "contact sheet not rendered" in note), notes
        )


class RenderPdfkitVisibilityTests(AlxTestCase):
    """F1 (pdf-06): darwin Preview path — PDFKit failure is visible, not a refusal."""

    def issued(self, stack):
        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        helper.stub_gates(stack)
        code, out = self.run_in("issue")
        self.assertEqual(0, code, out)

    def test_darwin_pdfkit_failure_prints_line_and_keeps_sheet(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        def fake_render_pdf(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(extractable_pdf_bytes())
            return Path(output_path)

        def fail_pdfkit(*args, **kwargs):
            raise RuntimeError("swift missing")

        def succeed_pdfium(pdf_path, output_dir, **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / "page-0001.png").write_bytes(b"png")

        with ExitStack() as stack:
            self.issued(stack)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=fail_pdfkit
                )
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfium", side_effect=succeed_pdfium
                )
            )
            stack.enter_context(mock.patch.object(alx.sys, "platform", "darwin"))
            stack.enter_context(
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin")
            )
            stack.enter_context(
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock())
            )
            code, out = self.run_in("render", "--template", "executive")
        self.assertEqual(0, code, out)
        self.assertIn(
            "executive contact sheet: PDFKit failed (swift missing); "
            "rendered with pdfium",
            out,
        )
        self.assertTrue((self.dir / "pages-executive" / "page-0001.png").is_file())

    def test_darwin_pdfkit_success_prints_nothing_extra(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        def fake_render_pdf(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(extractable_pdf_bytes())
            return Path(output_path)

        def succeed_pdfkit(pdf_path, output_dir, **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / "page-0001.png").write_bytes(b"png")

        with ExitStack() as stack:
            self.issued(stack)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=succeed_pdfkit
                )
            )
            stack.enter_context(mock.patch.object(alx.sys, "platform", "darwin"))
            stack.enter_context(
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin")
            )
            stack.enter_context(
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock())
            )
            code, out = self.run_in("render", "--template", "executive")
        self.assertEqual(0, code, out)
        self.assertNotIn("PDFKit failed", out)
        self.assertIn("executive contact sheet:", out)
        self.assertTrue((self.dir / "pages-executive" / "page-0001.png").is_file())


class RenderPdfCheckTests(AlxTestCase):
    """A2 / content-07: baseline --min-text-chars 5000; print-only."""

    def issued(self, stack):
        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        helper.stub_gates(stack)
        code, out = self.run_in("issue")
        self.assertEqual(0, code, out)

    def test_render_pdf_check_uses_5000_chars_for_every_language(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        captured = []

        class PdfErrors(list):
            text_chars = 500

        def fake_validate(path, **kwargs):
            captured.append(kwargs)
            return PdfErrors(
                ["PDF has 12 extracted text characters; minimum is 5000."]
            )

        def fake_render_pdf(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(extractable_pdf_bytes())
            return Path(output_path)

        def fake_render_pages(pdf_path, output_dir, **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            page = Path(output_dir) / "page-001.png"
            page.write_bytes(b"\x89PNG")
            return [page]

        with ExitStack() as stack:
            self.issued(stack)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=fake_render_pages
                )
            )
            stack.enter_context(
                mock.patch.object(
                    alx.validate_report, "validate_pdf", side_effect=fake_validate
                )
            )
            for lang in ("en", "zh-CN"):
                state = self.state()
                state["lang"] = lang
                (self.dir / ".alx" / "state.json").write_text(
                    json.dumps(state), encoding="utf-8"
                )
                captured.clear()
                code, out = self.run_in("render", "--template", "executive")
                with self.subTest(lang=lang):
                    self.assertEqual(0, code, out)
                    self.assertEqual(1, len(captured), captured)
                    self.assertEqual(5000, captured[0]["min_text_chars"])
                    self.assertIn(
                        "executive PDF check: PDF has 12 extracted text "
                        "characters; minimum is 5000.",
                        out,
                    )

    def test_render_pdf_check_has_no_page_minimum_line(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        captured = []

        class PdfErrors(list):
            text_chars = 5000

        def fake_validate(path, **kwargs):
            captured.append(kwargs)
            return PdfErrors()

        def fake_render_pdf(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(extractable_pdf_bytes())
            return Path(output_path)

        def fake_render_pages(pdf_path, output_dir, **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            page = Path(output_dir) / "page-001.png"
            page.write_bytes(b"\x89PNG")
            return [page]

        with ExitStack() as stack:
            self.issued(stack)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=fake_render_pages
                )
            )
            stack.enter_context(
                mock.patch.object(
                    alx.validate_report, "validate_pdf", side_effect=fake_validate
                )
            )
            code, out = self.run_in("render", "--template", "executive")
        self.assertEqual(0, code, out)
        self.assertEqual(1, len(captured), captured)
        self.assertEqual(0, captured[0].get("min_pages", 1))
        self.assertNotIn("pages; minimum is", out)


class CheckerBudgetTests(AlxTestCase):
    """K7 (D7): a stalled rewild checker costs its timeout once per command."""

    def test_one_issue_runs_the_stalled_checker_once(self):
        import subprocess
        import time
        from contextlib import ExitStack

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        calls = []
        real_run = subprocess.run

        def stalled(command, **kwargs):
            if not any("naturalness-check" in str(item) for item in command):
                return real_run(command, **kwargs)
            calls.append(kwargs.get("timeout"))
            time.sleep(0.05)
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

        with ExitStack() as stack:
            # rewild=False: the real gate runs, so the checker is reached from
            # the check, the gate, and the refused gate's findings.
            helper.stub_gates(stack, rewild=False)
            stack.enter_context(
                mock.patch.object(
                    alx.rewild_gate.subprocess, "run", side_effect=stalled
                )
            )
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertEqual([alx.REWILD_CHECKER_TIMEOUT_SECONDS], calls)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(encoding="utf-8")
        )["notes"]
        # R28: the timeout is a warning, recorded in the notes; `calls` above
        # is what pins the single subprocess payment.
        self.assertTrue(
            any("Rewild checker timed out" in note for note in notes), notes
        )


class ClaimAddDryRunTests(AlxTestCase):
    """Field-test P0/P1: a rehearsal, a summary, and one readable transcript."""

    def prepared(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        return self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO, CLAIM_BROKEN])

    def test_summary_line_leads_the_output_and_the_transcript_is_written(self):
        batch = self.prepared()
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code, out)
        lines = out.splitlines()
        self.assertEqual("3 submitted, 2 accepted, 1 failed: C3(1)", lines[0])
        self.assertIn("full output: .alx/last-claim-add.txt", out)
        transcript = (self.dir / ".alx" / "last-claim-add.txt").read_text(
            encoding="utf-8"
        )
        self.assertTrue(transcript.startswith("3 submitted, 2 accepted, 1 failed: C3("))
        self.assertIn("C3 FAIL", transcript)

    def test_summary_line_says_zero_failed_without_a_list(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertEqual("2 submitted, 2 accepted, 0 failed", out.splitlines()[0])

    def test_a_top_level_array_file_is_one_claim_per_element(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertEqual({"C1", "C2"}, {c["claim_id"] for c in self.ledger()["claims"]})
        self.assertEqual(
            {"C1": str(batch), "C2": str(batch)}, self.state()["claim_files"]
        )


class InitEchoTests(AlxTestCase):
    def test_init_echoes_an_inferred_archetype_and_the_language(self):
        subject = self.root / "subject.txt"
        subject.write_text("Ledger Study\n", encoding="utf-8")
        code, out = self.run_alx(
            "init", self.dir, "--lang", "en", "--subject", subject
        )
        self.assertEqual(0, code, out)
        self.assertIn(
            "archetype: hybrid (inferred) — change with "
            "`alx init … --archetype <name>`",
            out,
        )
        self.assertIn("language: en — change with", out)
        self.assertIn("Workspace ready", out)
        self.assertIn("target length", out)
        self.assertIn("Next:", out)
        self.assertEqual("hybrid", self.state()["archetype"])

    def test_init_echoes_a_given_archetype_and_the_person_status_flag(self):
        code, out = self.init()
        self.assertEqual(0, code, out)
        self.assertIn("archetype: artifact (given)", out)
        self.assertNotIn("--subject-status", out)
        subject = self.root / "person.txt"
        subject.write_text("Someone Notable\n", encoding="utf-8")
        code, out = self.run_alx(
            "init",
            self.root / "person-ws",
            "--lang",
            "en",
            "--subject",
            subject,
            "--archetype",
            "person",
        )
        self.assertEqual(0, code, out)
        self.assertIn(
            "archetype: person (given) — change with `alx init … "
            "--archetype <name>`",
            out,
        )
        self.assertNotIn("--subject-status", out)
        self.assertIn("Workspace ready", out)


class FlowFixTests(AlxTestCase):
    """The blocker audit's flow fixes: skeleton, foreign links, degrade, bind."""

    FOREIGN = "https://elsewhere.example/page"

    def issue_helper(self):
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(issue_tests, name, getattr(self, name))
        return issue_tests

    def link_a_foreign_url(self):
        path = self.dir / "report.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "so the counts above are",
                f"so the counts [above]({self.FOREIGN}) are",
            ),
            encoding="utf-8",
        )

    # item 1 ---------------------------------------------------------------
    def test_a_fresh_workspace_starts_with_a_valid_limitations_list(self):
        code, out = self.init()
        self.assertEqual(0, code, out)
        self.assertEqual([], self.ledger()["synthesis"]["limitations"])
        code, out = self.run_in("check")
        self.assertNotIn("limitations", out)

    # item 2 ---------------------------------------------------------------
    def test_a_foreign_link_prints_a_remove_remedy(self):
        self.bootstrap()
        self.link_a_foreign_url()
        _code, out = self.run_in("check")
        self.assertIn("binding/link-not-in-ledger", out)
        self.assertIn(f"Remove: `remove link {self.FOREIGN} from report.md`", out)

    def test_issue_strips_the_foreign_link_and_issues(self):
        """C1 restatement of test_deliver_strips_...: plain `issue` strips."""
        from contextlib import ExitStack

        issue_tests = self.issue_helper()
        issue_tests.prepared()
        self.link_a_foreign_url()
        with ExitStack() as stack:
            issue_tests.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertIn(f"link removed: {self.FOREIGN}", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(self.FOREIGN, report)
        # The anchor text stays; only the URL goes.
        self.assertIn("so the counts above are", report)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    # item 4 ---------------------------------------------------------------
    def test_the_next_command_is_issue_and_never_a_snapshot(self):
        """C6 restatement of test_the_next_command_degrades_to_deliver."""
        self.bootstrap()
        self.run_in("check", "--fix")
        self.set_remaining(5)
        code, out = self.run_in("status")
        self.assertEqual(0, code, out)
        self.assertIn("Next: `alx issue`", out)
        self.assertNotIn("alx snapshot", out)
        self.assertNotIn("alx review start", out)

    # item 8 ---------------------------------------------------------------
    def test_claim_bind_takes_repeated_pairs_and_the_flag_form(self):
        self.bootstrap()
        code, out = self.run_in("claim", "bind", "C1:1", "C2:2")
        self.assertEqual(0, code, out)
        bindings = self.state()["bindings"]
        self.assertEqual(1, bindings["C1"])
        self.assertEqual(2, bindings["C2"])
        code, out = self.run_in("claim", "bind", "C1", "--paragraph", "3")
        self.assertEqual(0, code, out)
        self.assertEqual(3, self.state()["bindings"]["C1"])
        code, out = self.run_in("claim", "bind", "C9:1")
        self.assertEqual(1, code, out)
        self.assertIn("C9 is not in the ledger", out)

    # item 9 ---------------------------------------------------------------
    def test_a_producer_extract_length_remedy_names_the_claim_file(self):
        item = alx.Finding(
            family="ledger/extract-length",
            severity="warn",
            klass="A",
            ids=["C1"],
            message="Extract is shorter than the threshold.",
            fix="extend the quote in claims/<file>",
            remove="",
        )
        named = alx.render_grouped(
            alx.adopt([item], claim_files={"C1": "claims/batch.json"})
        )
        self.assertIn("extend the quote in claims/batch.json", named)
        self.assertNotIn("claims/<file>", named)
        bare = alx.render_grouped(alx.adopt([item]))
        self.assertIn("extend the quote in claims/*.json", bare)
        self.assertNotIn("claims/<file>", bare)


class LedgerSchemaCeremonyTests(AlxTestCase):
    """09-15-01 A1/A2/A3: the schema carries evidence, not ceremony."""

    PERSON_EXTRACT = (
        "The reading room keeps 「原始日記」 under restricted access "
        "for named researchers."
    )

    def ledger_schema(self):
        return json.loads(
            alx.validate_ledger.DEFAULT_SCHEMA.read_text(encoding="utf-8")
        )

    def merge(self, name, patch):
        return self.run_in("ledger", "merge", self.write_json(name, patch))

    # A1 -------------------------------------------------------------------
    def test_a_claim_add_accepts_validates_against_the_ledger_schema(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.merge(
            "people.json", {"people": [{"person_id": "P1", "name": "Rowan Ash"}]}
        )
        self.assertEqual(0, code, out)
        batch = self.write_json(
            "person_claim.json",
            [
                {
                    "claim_id": "C7",
                    "claim": (
                        "Rowan Ash records that the reading room keeps "
                        "「原始日記」 under restricted access for named researchers."
                    ),
                    "importance": "key",
                    "supports": [],
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": self.PERSON_EXTRACT,
                        }
                    ],
                }
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        claim = self.ledger()["claims"][-1]
        self.assertEqual(["P1"], claim["person_ids"])
        self.assertIsNone(claim["decision_relevance"])
        # R32: the schema again requires the research-design sections
        # (coverage rows, synthesis); the accepted claim itself validates.
        errors = alx.validate_ledger.validate_schema(
            self.ledger(), self.ledger_schema()
        )
        self.assertEqual([], [e for e in errors if e.startswith("claims")], errors)

    def test_a_free_form_brief_patch_merges_with_no_hard_finding(self):
        self.bootstrap()
        code, out = self.merge(
            "brief.json",
            {
                "brief": {
                    "goal": "Map the release against the registry tally.",
                    "scope": "Public records for March 2026 only.",
                    "deliverable": "One English report with a timeline.",
                }
            },
        )
        self.assertEqual(0, code, out)
        self.assertNotIn("ledger/schema", out)
        brief = self.ledger()["brief"]
        self.assertEqual("Public records for March 2026 only.", brief["scope"])
        self.assertEqual("One English report with a timeline.", brief["deliverable"])

    def test_a_name_only_people_patch_merges_with_no_hard_finding(self):
        self.bootstrap()
        code, out = self.merge(
            "people.json",
            {
                "people": [
                    {"name": "Rowan Ash", "role": "subject", "note": "1887-1975"},
                    {"name": "Wen Li", "role": "expert", "note": "archive historian"},
                ]
            },
        )
        self.assertEqual(0, code, out)
        self.assertNotIn("ledger/schema", out)
        self.assertEqual(
            ["Rowan Ash", "Wen Li"],
            [person["name"] for person in self.ledger()["people"]],
        )

    # A2 -------------------------------------------------------------------
    def test_ledger_merge_carries_unresolved_questions(self):
        self.bootstrap()
        code, out = self.merge(
            "questions.json",
            {"unresolved_questions": ["Who audited the registry tally?"]},
        )
        self.assertEqual(0, code, out)
        self.assertNotIn("ignored key(s)", out)
        self.assertEqual(
            ["Who audited the registry tally?"],
            self.ledger()["unresolved_questions"],
        )

    # A3 -------------------------------------------------------------------
    def test_fetch_normalizes_a_published_timestamp_to_a_date(self):
        page = PAGE.replace(
            '<meta property="article:published_time" content="2026-01-05">',
            '<meta property="article:published_time" '
            'content="2010-04-16 01:50:56">',
        )
        self.init()
        code, out = self.fetch("https://example.org/study", page=page)
        self.assertEqual(0, code, out)
        self.assertEqual("2010-04-16", self.ledger()["sources"][0]["published"])
        errors = alx.validate_ledger.validate_schema(
            self.ledger(), self.ledger_schema()
        )
        self.assertEqual([], [e for e in errors if e.startswith("sources")], errors)

    def test_published_forms_alx_cannot_read_are_dropped(self):
        self.assertEqual("2010-04-16", alx._normalized_published("2010/4/16"))
        self.assertEqual("1948-11-24", alx._normalized_published("1948年11月24日"))
        self.assertIsNone(alx._normalized_published("Spring 2010"))
        self.assertIsNone(alx._normalized_published(None))



# --------------------------------------------------------------------------
# 09-15-01 Part B: markers, cited sources, Sources heading, render, finish
# --------------------------------------------------------------------------


class ClaimMarkerTests(AlxTestCase):
    """B1: `[C<n>]` in a paragraph binds that claim to that paragraph."""

    def marked_report(self, first_marker="[C1]", second_marker="[C2]"):
        ledger = self.ledger()
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        text = text.replace(
            f"[recorded in the study]({first})",
            f"recorded in the study {first_marker}",
        )
        text = text.replace(
            f"as the [registry note]({second}) records",
            f"as the registry note records {second_marker}",
        )
        (self.dir / "report.md").write_text(text, encoding="utf-8")
        return text

    def mapping(self):
        return alx.paragraph_mapping(
            alx.Workspace(self.dir),
            self.state(),
            self.ledger(),
            (self.dir / "report.md").read_text(encoding="utf-8"),
        )

    def test_a_marker_binds_the_claim_to_its_paragraph(self):
        self.bootstrap()
        self.marked_report()
        mapping, unbound = self.mapping()
        self.assertEqual({"C1": 1, "C2": 2}, mapping)
        self.assertEqual({}, unbound)

    def test_every_marker_form_binds_every_id_it_names(self):
        text = (
            "# Title\n\n"
            "> Standfirst.\n> 1 January 2026\n\n"
            "One 【C3、C4】.\n\n"
            "Two [C5，C6] and [C7, C8].\n"
        )
        self.assertEqual(
            {"C3": 1, "C4": 1, "C5": 2, "C6": 2, "C7": 2, "C8": 2},
            alx._marker_bindings(text),
        )

    def test_a_multi_id_marker_binds_both_claims_to_one_paragraph(self):
        self.bootstrap()
        self.marked_report(first_marker="[C1, C2]", second_marker="")
        mapping, _unbound = self.mapping()
        self.assertEqual({"C1": 1, "C2": 1}, mapping)

    def test_fix_turns_markers_into_source_links_and_leaves_no_hard(self):
        self.bootstrap()
        self.marked_report(first_marker="[C1, C2]", second_marker="[C9]")
        _code, out = self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        ledger = self.ledger()
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        self.assertIn(f"[S1]({first}) [S2]({second})", report)
        self.assertNotIn("[C1, C2]", report)
        # A marker whose claim is not in the ledger is left alone.
        self.assertIn("[C9]", report)
        excerpts = [
            excerpt
            for claim in ledger["claims"]
            for excerpt in claim.get("report_excerpts") or []
        ]
        self.assertTrue(excerpts)
        self.assertFalse([item for item in excerpts if "[C1" in item], excerpts)
        self.pad_report()
        self.run_in("snapshot")
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("=== HARD 0", out)

    def test_an_explicit_bind_beats_the_marker(self):
        self.bootstrap()
        self.marked_report()
        code, out = self.run_in("claim", "bind", "C1:3")
        self.assertEqual(0, code, out)
        mapping, _unbound = self.mapping()
        self.assertEqual(3, mapping["C1"])

    def test_a_mixed_marker_links_the_known_id_and_keeps_the_unknown_one(self):
        self.bootstrap()
        self.marked_report(first_marker="[C1, C42]")
        self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        first = self.ledger()["sources"][0]["url"]
        self.assertIn(f"[S1]({first}) [C42]", report)

    def test_snapshot_converts_the_markers_it_copies(self):
        self.bootstrap()
        self.marked_report()
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        first = self.ledger()["sources"][0]["url"]
        for name in ("report.md", "report.pre-rewild.md"):
            text = (self.dir / name).read_text(encoding="utf-8")
            self.assertIn(f"[S1]({first})", text)
            self.assertNotIn("[C1]", text)
        self.assertEqual(1, self.state()["bindings"]["C1"])


class CitedSourceTests(AlxTestCase):
    """B2: a bound claim cites its sources without a link in the body."""

    def test_a_bound_claim_without_a_body_link_is_still_listed(self):
        self.bootstrap()
        ledger = self.ledger()
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        text = text.replace(
            f"[recorded in the study]({first})", "recorded in the study"
        )
        text = text.replace(f"[registry note]({second})", "registry note")
        (self.dir / "report.md").write_text(text, encoding="utf-8")
        code, out = self.run_in("claim", "bind", "C1:1", "C2:2")
        self.assertEqual(0, code, out)
        _code, out = self.run_in("check", "--fix")
        self.assertNotIn("binding/sources-section", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        listing = report[report.index("## Sources") :]
        self.assertIn(f"]({first})", listing)
        self.assertIn(f"]({second})", listing)


class SourcesHeadingTests(AlxTestCase):
    """B3: which H2 is the Sources section, and writing one when it is absent."""

    def test_the_predicate_accepts_every_written_form(self):
        for heading in (
            "Sources",
            "资料来源",
            "資料來源",
            "参考文献",
            "六、参考资料",
            "附录：资料来源",
            "References and sources",
            "Sources and further reading",
        ):
            with self.subTest(heading=heading):
                self.assertTrue(alx.validate_report.is_sources_heading(heading))
        for heading in (
            "Findings",
            "方法",
            "文献回顾",
            "引用日记原文的原则",
            "Cross-references between entries",
        ):
            with self.subTest(heading=heading):
                self.assertFalse(alx.validate_report.is_sources_heading(heading))
        self.assertIsNotNone(
            alx.sources_heading_offset("# T\n\n## 资料来源\n\n- [a](https://x.test/)\n")
        )

    def test_fix_appends_the_sources_section_when_the_report_has_none(self):
        self.bootstrap()
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            text[: text.index("## Sources")].rstrip("\n") + "\n", encoding="utf-8"
        )
        _code, _out = self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        listing = report[report.index("## Sources") :]
        self.assertIn(f"]({self.ledger()['sources'][0]['url']})", listing)


class MarkerFixtureTests(AlxTestCase):
    """Acceptance B: raw markers plus `## 资料来源` with bare URLs, end to end."""

    def test_check_fix_binds_markers_and_rebuilds_the_listing(self):
        self.bootstrap()
        ledger = self.ledger()
        first = ledger["sources"][0]["url"]
        second = ledger["sources"][1]["url"]
        date_line = alx.report_contract.localized_date("en", None)
        (self.dir / "report.md").write_text(
            "# Ledger Study\n\n"
            "> Whether the archive release matches the registry tally.\n"
            f"> {date_line}\n\n"
            "## Findings\n\n"
            "The archive released 1,204 documents in March 2026, a release the "
            "registry confirmed [C1].\n\n"
            "The registry logged 1,204 documents in March 2026 for the same "
            "period [C2].\n\n"
            "The reading room keeps 「原始日記」 under restricted access, so the "
            "counts above are the only public record.\n\n"
            "## 资料来源\n\n"
            f"{first}\n{second}\n",
            encoding="utf-8",
        )
        _code, out = self.run_in("check", "--fix")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(f"[S1]({first})", report)
        self.assertIn(f"[S2]({second})", report)
        self.assertNotIn("[C1]", report)
        listing = report[report.index("## 资料来源") :]
        self.assertIn(f"- [{ledger['sources'][0]['title']}]({first})", listing)
        self.pad_report()
        self.run_in("snapshot")
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("=== HARD 0", out)
        self.assertNotIn("binding/sources-section", out)


class RenderRepeatTests(AlxTestCase):
    """B4: `alx` owns `pages-<template>`; a second render refills it."""

    def issued(self, stack):
        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        helper.stub_gates(stack)
        code, out = self.run_in("issue")
        self.assertEqual(0, code, out)

    def test_render_twice_writes_both_contact_sheets(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        def fake_render_pdf(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(extractable_pdf_bytes())
            return Path(output_path)

        def strict_render_pages(pdf_path, output_dir, **kwargs):
            target = Path(output_dir)
            if target.exists() and any(target.iterdir()):
                raise RuntimeError(f"Output directory must be empty: {target}")
            target.mkdir(parents=True, exist_ok=True)
            page = target / "page-001.png"
            page.write_bytes(b"\x89PNG")
            return [page]

        with ExitStack() as stack:
            self.issued(stack)
            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=fake_render_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=strict_render_pages
                )
            )
            for attempt in range(2):
                code, out = self.run_in("render")
                with self.subTest(attempt=attempt):
                    self.assertEqual(0, code, out)
                    self.assertIn("executive contact sheet:", out)
                    self.assertNotIn("tooling/render", out)


class ReviewFinishOneRoundTests(AlxTestCase):
    """B6: `review finish` names everything once and owns its own fields."""

    def reviewer(self):
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("root", "dir", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        return reviews

    def started(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        return self.dir / "reviews" / "content.json"

    def note(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write_note(self, path, note):
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")

    def test_the_own_checks_and_the_schema_errors_come_in_one_round(self):
        self.started()
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertIn("WARN review/content:", out)
        self.assertIn("scores.question_answered.score (integer 1-5)", out)
        paths = []
        for line in out.splitlines():
            if line.startswith("WARN review/content: "):
                rest = line.split("WARN review/content: ", 1)[1]
                paths.append(rest.split(":", 1)[0].split()[0])
        self.assertEqual(len(paths), len(set(paths)), paths)

    def test_finish_writes_status_itself(self):
        path = self.started()
        self.reviewer().fill_note("content")
        note = self.note(path)
        del note["status"]
        self.write_note(path, note)
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertEqual("completed", self.note(path)["status"])

    def test_finish_fills_a_missing_section_disposition(self):
        path = self.started()
        self.reviewer().fill_note("content")
        note = self.note(path)
        del note["section_reviews"][0]["disposition"]
        self.write_note(path, note)
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertEqual("keep", self.note(path)["section_reviews"][0]["disposition"])

    def test_a_disclosure_excerpt_survives_the_report_markup(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            text.replace(
                "1,204 documents in March 2026",
                "**1,204 documents in March 2026**",
                1,
            ),
            encoding="utf-8",
        )
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        path = self.dir / "reviews" / "content.json"
        self.reviewer().fill_note("content")
        note = self.note(path)
        note["findings"] = [
            {
                "finding_id": "F1",
                "severity": "minor",
                "category": "evidence",
                "location": "Findings, paragraph 1",
                "finding": "The release count is stated without its caveat.",
                "disposition": "accepted_limitation",
                "rationale": "The registry tally is cited in the next sentence.",
                "report_disclosure_excerpt": "1,204 documents in March 2026",
            }
        ]
        self.write_note(path, note)
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)


class LiveRecheckNoteTests(AlxTestCase):
    """B7: the reserve skip says what was verified, and never prints minus."""

    def test_the_skipped_note_names_the_offline_verification(self):
        from contextlib import ExitStack

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        with ExitStack() as stack:
            helper.stub_gates(stack)
            self.set_remaining(-20)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        issued = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertFalse(
            any("re-check skipped" in note for note in issued["delivery_notes"]),
            issued["delivery_notes"],
        )


class LedgerMergeMissingClaimTests(AlxTestCase):
    """Field test 4: a patch citing unadded claims says so in its first line."""

    def patch_citing(self, *claim_ids):
        return self.write_json(
            "cov.json",
            {
                "coverage": [
                    {**COVERAGE_PATCH["coverage"][0], "claim_ids": list(claim_ids)}
                ]
            },
        )

    def test_absent_claim_ids_lead_the_output(self):
        self.bootstrap()
        code, out = self.run_in("ledger", "merge", self.patch_citing("C1", "C9"))
        self.assertEqual(
            "1 claim ids not in the ledger (C9); run alx claim add first",
            out.splitlines()[0],
            out,
        )
        self.assertEqual(0, code, out)

    def test_existing_claim_ids_print_no_such_line(self):
        self.bootstrap()
        code, out = self.run_in("ledger", "merge", self.patch_citing("C1", "C2"))
        self.assertEqual(0, code, out)
        self.assertNotIn("not in the ledger", out)

    def test_malformed_patch_json_is_one_line(self):
        self.bootstrap()
        path = self.root / "patch_cov.json"
        path.write_text('{"a":1}}', encoding="utf-8")
        code, out = self.run_in("ledger", "merge", path)
        self.assertEqual(1, code, out)
        self.assertIn("is not valid JSON: Extra data at line 1 column 8", out)
        self.assertNotIn("Traceback", out)
TRADITIONAL_PAGE = """<html><head><title>中山艦</title></head><body>
<p>中山艦事件發生於一九二六年三月，其真實性仍有爭議。</p>
</body></html>"""


class FindScriptVariantTests(AlxTestCase):
    def fetch_traditional(self):
        self.init()
        code, out = self.fetch("https://example.org/zhongshan", page=TRADITIONAL_PAGE)
        self.assertEqual(0, code, out)

    def test_a_simplified_keyword_finds_the_traditional_source(self):
        self.fetch_traditional()
        code, out = self.run_in("find", "all", "中山舰")
        self.assertEqual(0, code, out)
        line = next(
            item for item in out.splitlines() if "extract_or_location:" in item
        )
        self.assertIn("中山艦", line)
        self.assertNotIn("no source contains 中山舰", out)

    def test_the_traditional_keyword_still_hits(self):
        self.fetch_traditional()
        code, out = self.run_in("find", "all", "中山艦")
        self.assertEqual(0, code, out)
        self.assertIn("中山艦", out)
        self.assertNotIn("no source contains", out)

    def test_a_keyword_with_no_variant_behaves_as_before(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("find", "S1", "1,204")
        self.assertEqual(0, code, out)
        self.assertIn("S1 #1 extract_or_location: ", out)
        code, out = self.run_in("find", "S1", "nowhere-in-any-source")
        self.assertEqual(0, code, out)
        self.assertIn("no source contains nowhere-in-any-source", out)

    def test_variants_are_ordered_and_deduplicated(self):
        self.assertEqual(["1,204"], alx._script_variants("1,204"))
        self.assertEqual(["中山舰", "中山艦"], alx._script_variants("中山舰"))


class MarkerLinkDedupeTests(AlxTestCase):
    def test_two_claims_on_one_source_render_one_link(self):
        self.bootstrap()
        ledger = self.ledger()
        # C2 now shares S1 with C1, so `[C1, C2]` must not print S1 twice.
        for claim in ledger["claims"]:
            if claim["claim_id"] == "C2":
                claim["source_ids"] = ["S1"]
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        first = ledger["sources"][0]["url"]
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        text = text.replace(
            f"[recorded in the study]({first})",
            "recorded in the study [C1, C2] [C22]",
        )
        converted = alx._convert_claim_markers(
            alx.Workspace(self.dir), self.ledger(), text
        )
        self.assertIn(f"[S1]({first})", converted)
        self.assertEqual(1, converted.count(f"[S1]({first})"))
        self.assertIn("[C22]", converted)


class InitLengthTargetTests(AlxTestCase):
    def test_init_echoes_the_target_length_and_writes_it_into_the_report(self):
        subject = self.root / "subject.txt"
        subject.write_text("账本研究\n", encoding="utf-8")
        code, out = self.run_alx(
            "init", self.dir, "--lang", "zh-CN", "--subject", subject
        )
        self.assertEqual(0, code, out)
        self.assertIn("target length: 5000–10000", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        first_quote = next(
            line for line in report.splitlines() if line.startswith(">")
        )
        self.assertIn("5000", first_quote)

    def test_the_english_target_reaches_both_places(self):
        code, out = self.init()
        self.assertEqual(0, code, out)
        self.assertIn("target length: 7500–15000 words", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("Target 7500–15000 words.", report)


class CompactWarnTierTests(AlxTestCase):
    """R29/A5: the WARN tier is one line per family; `--verbose` expands it."""

    def _unverified(self):
        self.bootstrap()
        ledger = self.ledger()
        for source in ledger["sources"]:
            source["provenance"] = "unverified"
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )

    def test_check_prints_one_line_per_warn_family(self):
        self._unverified()
        _code, out = self.run_in("check")
        warn = out.split("=== WARN ")[1].split("=== STATUS:")[0].splitlines()[1:]
        self.assertTrue(warn)
        for line in warn:
            with self.subTest(line=line):
                self.assertTrue(line.startswith("["), line)
                self.assertIn(" — ", line)
        families = [line.split("]")[0] + "]" for line in warn]
        self.assertEqual(len(families), len(set(families)))

    def test_verbose_expands_the_warn_tier_to_one_line_per_item(self):
        self._unverified()
        _code, compact = self.run_in("check")
        _code, verbose = self.run_in("check", "--verbose")
        self.assertIn("[ledger/provenance] 2", compact)
        self.assertIn("[ledger/provenance] 2", verbose)
        self.assertGreater(
            len(verbose.splitlines()), len(compact.splitlines())
        )
        self.assertTrue(
            any(line.startswith("  ") for line in verbose.splitlines()[5:]),
            verbose,
        )

    def test_verbose_expands_quantity_warns_to_one_line_per_item(self):
        self.bootstrap()
        ledger = self.ledger()
        ledger["claims"][0]["claim"] = (
            "The archive released 7,777 documents in March 2026."
        )
        ledger["claims"][1]["claim"] = (
            "The registry logged 8,888 documents in March 2026."
        )
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, compact = self.run_in("check")
        _code, verbose = self.run_in("check", "--verbose")
        self.assertIn("[ledger/quantity] 2", compact)
        self.assertIn("[ledger/quantity] 2", verbose)
        self.assertGreater(
            len(verbose.splitlines()), len(compact.splitlines())
        )
        self.assertTrue(
            any(line.startswith("  ") for line in verbose.splitlines()[5:]),
            verbose,
        )

    def test_the_hard_tier_and_the_headers_are_unchanged(self):
        self.bootstrap()
        (self.dir / "sources" / "S1.txt").write_text("tampered", encoding="utf-8")
        _code, out = self.run_in("check")
        self.assertIn("[fidelity/cache-detached]", out)
        self.assertRegex(out, r"=== HARD \d+ \(fix, or alx issue drops them\) ===")
        self.assertRegex(out, r"=== WARN \d+ ===")
        hard = out.split("=== HARD ")[1].split("=== WARN")[0].splitlines()[1:]
        self.assertTrue(any(line.startswith("  ") for line in hard), out)


class PortfolioVocabularyTests(AlxTestCase):
    def test_the_portfolio_finding_lists_every_allowed_value(self):
        self.bootstrap()
        ledger = self.ledger()
        for source in ledger["sources"]:
            source["provenance"] = "unverified"
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, out = self.run_in("check", "--verbose")
        self.assertIn("portfolio has no independent source", out)
        for flag, values in (
            ("--provenance", alx.PROVENANCES),
            ("--type", alx.EVIDENCE_TYPES),
            ("--role", alx.SOURCE_ROLES),
        ):
            self.assertIn(f"{flag}: {', '.join(values)}", out)


class DeletedNoiseFamiliesTests(AlxTestCase):
    """R29/A4: review noise the gates no longer raise."""

    def test_a_missing_review_is_a_finding(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("review/content-missing", out)
        self.assertIn("review is missing", out)
        self.assertIn("review/rewild", out)

    def test_the_deleted_families_are_not_registered(self):
        for family in (
            "rewild/humanization",
            "content/claim-support",
            "content/claim-binding",
        ):
            with self.subTest(family=family):
                self.assertNotIn(family, alx.FAMILIES)
        self.assertIn("review/content-missing", alx.FAMILIES)


class FlowResilienceTests(AlxTestCase):
    """C3-C5: a relative input path, an unknown flag value, a second snapshot."""

    def test_claim_add_resolves_a_relative_path_under_dir(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.dir / "claims" / "batch.json"
        batch.parent.mkdir(parents=True, exist_ok=True)
        batch.write_text(
            json.dumps([CLAIM_ONE, CLAIM_TWO], ensure_ascii=False), encoding="utf-8"
        )
        code, out = self.run_in("claim", "add", "claims/batch.json")
        self.assertEqual(0, code, out)
        self.assertEqual(
            {"C1", "C2"}, {claim["claim_id"] for claim in self.ledger()["claims"]}
        )

    def test_an_unknown_fetch_flag_value_warns_and_stores_the_default(self):
        self.init()
        with mock_production_transport(responses(PAGE)):
            code, out = self.run_in(
                "fetch",
                "https://example.org/study",
                "--type",
                "commentary",
                "--role",
                "pundit",
            )
        self.assertEqual(0, code, out)
        self.assertIn("unknown --type 'commentary'; stored as news_report", out)
        self.assertIn("unknown --role 'pundit'; stored as independent_analysis", out)
        source = self.ledger()["sources"][0]
        self.assertEqual("news_report", source["evidence_type"])
        self.assertEqual(["independent_analysis"], source["roles"])

    def test_a_second_snapshot_writes_a_numbered_copy(self):
        self.bootstrap()
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        self.assertIn("Snapshot written: report.pre-rewild.md", out)
        code, out = self.run_in("snapshot")
        self.assertEqual(0, code, out)
        self.assertIn("Snapshot written: report.pre-rewild.iter1.md", out)
        self.assertTrue((self.dir / "report.pre-rewild.md").exists())
        self.assertTrue((self.dir / "report.pre-rewild.iter1.md").exists())


class InitPathResolutionTests(AlxTestCase):
    """C3 reaches `init` too: a --subject path under --dir must not crash."""

    def test_init_resolves_a_relative_subject_under_dir(self):
        work = self.root / "ws-init"
        work.mkdir()
        (work / "subject.txt").write_text("Probe subject\nWhat does it decide?\n", encoding="utf-8")
        code, out = self.run_alx(
            "--dir", work, "init", str(work), "--lang", "en", "--subject", "subject.txt"
        )
        self.assertEqual(0, code, out)
        self.assertTrue((work / "ledger.json").exists())
        self.assertNotIn("Traceback", out)


class PartBFlowTests(AlxTestCase):
    EXTRACT = (
        "The archive released 1,204 documents in March 2026, "
        "and the registry confirmed the count."
    )

    def test_fetch_id_without_refresh_implies_refresh(self):
        self.init()
        self.fetch("https://example.org/study")
        with mock_production_transport(responses()):
            code, out = self.run_in("fetch", "--id", "S1")
        self.assertEqual(0, code, out)
        self.assertNotIn("requires --refresh", out)

    def test_snapshot_restore_without_snapshot_exits_zero(self):
        self.init()
        code, out = self.run_in("snapshot", "--restore")
        self.assertEqual(0, code, out)
        self.assertIn("No snapshot to restore", out)

    def test_merge_skips_sources_and_claims_and_applies_the_rest(self):
        self.bootstrap()
        patch = self.write_json(
            "patch.json",
            {
                "sources": [{"source_id": "S9"}],
                "claims": [{"claim_id": "C7"}],
                "brief": {"audience": "editors"},
            },
        )
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.assertIn(
            "ignored keys: sources, claims (sources only via fetch; "
            "claims only via claim add)",
            out,
        )
        self.assertEqual("editors", self.ledger()["brief"]["audience"])
        self.assertNotIn("C7", {c["claim_id"] for c in self.ledger()["claims"]})

    def test_claim_add_aliases_evidence_extract_and_source(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "alias.json",
            [
                {
                    "claim_id": "C1",
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "evidence": [{"source": "s1", "extract": self.EXTRACT}],
                }
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        claim = self.ledger()["claims"][0]
        self.assertEqual("S1", claim["source_evidence"][0]["source_id"])
        self.assertEqual(self.EXTRACT, claim["source_evidence"][0]["extract_or_location"])

    def test_claim_add_canonicalizes_ids(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "ids.json",
            [
                {
                    "claim_id": "C01",
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "source_evidence": [
                        {"source_id": " S3 ", "extract_or_location": self.EXTRACT}
                    ],
                }
            ],
        )
        # S3 is not fetched; canon of source happens, then batch findings fail.
        # Use S1 as "3" / "s1".
        batch.write_text(
            json.dumps(
                [
                    {
                        "claim_id": "c1",
                        "claim": "The archive released 1,204 documents in March 2026.",
                        "source_evidence": [
                            {"source_id": 1, "extract_or_location": self.EXTRACT}
                        ],
                    },
                    {
                        "claim_id": 1,
                        "claim": "duplicate id after canon",
                        "source_evidence": [
                            {"source_id": "s1", "extract_or_location": self.EXTRACT}
                        ],
                    },
                ]
            ),
            encoding="utf-8",
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code, out)
        self.assertEqual(["C1"], [c["claim_id"] for c in self.ledger()["claims"]])
        self.assertIn("C1 appears twice", out)

    def test_claim_add_assigns_next_free_id(self):
        self.init()
        self.fetch("https://example.org/study")
        first = self.write_json("c.json", [CLAIM_ONE])
        self.run_in("claim", "add", first)
        batch = self.write_json(
            "noid.json",
            [
                {
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "source_evidence": [
                        {"source_id": "S1", "extract_or_location": self.EXTRACT}
                    ],
                }
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C2 added (assigned id)", out)
        self.assertEqual(
            ["C1", "C2"], [c["claim_id"] for c in self.ledger()["claims"]]
        )

    def test_claim_add_drops_unknown_keys(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "note.json",
            [
                {
                    "claim_id": "C3",
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "kind": "fact",
                    "importance": "supporting",
                    "importnace": "key",
                    "caveats": "extra",
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": self.EXTRACT,
                            "note": "inner",
                        }
                    ],
                }
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        self.assertIn("C3 added", out)
        self.assertIn("C3 WARN", out)
        self.assertIn("[ledger/claim-input]", out)
        self.assertIn("C3: unknown fields ignored: importnace, caveats", out)
        self.assertNotIn("FAIL", out)
        claim = self.ledger()["claims"][0]
        self.assertEqual("C3", claim["claim_id"])
        self.assertNotIn("importnace", claim)
        self.assertNotIn("caveats", claim)
        self.assertNotIn("note", claim["source_evidence"][0])

    def test_claim_add_unwraps_claims_array_wrapper(self):
        self.init()
        self.fetch("https://example.org/study")
        path = self.write_json(
            "wrap.json",
            {
                "claims": [
                    {
                        "claim_id": "C1",
                        "claim": "The archive released 1,204 documents in March 2026.",
                        "source_evidence": [
                            {"source_id": "S1", "extract_or_location": self.EXTRACT}
                        ],
                    }
                ]
            },
        )
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(0, code, out)
        self.assertEqual(["C1"], [c["claim_id"] for c in self.ledger()["claims"]])

    def test_claim_add_skips_non_object_items(self):
        self.init()
        self.fetch("https://example.org/study")
        path = self.write_json(
            "mixed.json",
            [
                CLAIM_ONE,
                "not-an-object",
                {
                    "claim_id": "C2",
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "source_evidence": [
                        {"source_id": "S1", "extract_or_location": self.EXTRACT}
                    ],
                },
            ],
        )
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(0, code, out)
        self.assertIn("item 2 is not an object; skipped", out)
        self.assertEqual(
            ["C1", "C2"], [c["claim_id"] for c in self.ledger()["claims"]]
        )

    def test_claim_add_maps_sources_and_quote_aliases(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "src.json",
            [
                {
                    "claim_id": "C1",
                    "claim": "The archive released 1,204 documents in March 2026.",
                    "sources": [{"sid": "3", "quote": self.EXTRACT}],
                }
            ],
        )
        # sid 3 is S3; use " S1 "
        batch.write_text(
            json.dumps(
                [
                    {
                        "claim_id": "C1",
                        "claim": "The archive released 1,204 documents in March 2026.",
                        "extracts": [{"id": " S1 ", "text": self.EXTRACT}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        ev = self.ledger()["claims"][0]["source_evidence"][0]
        self.assertEqual("S1", ev["source_id"])
        self.assertEqual(self.EXTRACT, ev["extract_or_location"])

    def test_issue_offline_appends_no_delivery_disclosure(self):
        from contextlib import ExitStack

        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        self.run_in("snapshot")
        with ExitStack() as stack:
            helper = IssueTests("test_issue_writes_receipts_and_verification_note")
            helper.dir = self.dir
            helper.root = self.root
            calls = helper.stub_gates(
                stack,
                online={
                    "status": "passed",
                    "checks": [],
                    "refreshed_source_ids": [],
                    "disclosure_required": ["C1"],
                },
            )
            code, out = self.run_in("issue", "--offline")
        self.assertEqual(0, code, out)
        self.assertEqual(0, calls["online"])
        self.assertNotIn("source fidelity:", out)
        issued = json.loads(
            (self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")
        )
        self.assertFalse(
            any("central-judgment" in note for note in issued["delivery_notes"]),
            issued["delivery_notes"],
        )
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("Verification note:", report)
        self.assertNotIn("核查说明", report)
        self.assertNotIn("核實說明", report)

    def test_classification_and_optional_flags_keep_help_wording(self):
        parser = alx.build_parser()
        fetch = parser._subparsers._group_actions[0].choices["fetch"]
        issue = parser._subparsers._group_actions[0].choices["issue"]
        init = parser._subparsers._group_actions[0].choices["init"]
        claim = parser._subparsers._group_actions[0].choices["claim"]
        claim_add = claim._subparsers._group_actions[0].choices["add"]
        wanted = "optional; stored, not used for the report"
        for flag in ("--provenance", "--type", "--role"):
            self.assertIn(wanted, fetch._option_string_actions[flag].help)
        self.assertIn(
            "optional; stored, never required",
            init._option_string_actions["--archetype"].help,
        )
        self.assertNotIn("--subject-status", init._option_string_actions)
        self.assertNotIn("--deliver", issue._option_string_actions)
        self.assertNotIn("--dry-run", claim_add._option_string_actions)
        self.assertIn(
            "accepted, ignored",
            issue._option_string_actions["--offline"].help,
        )
        self.assertIn("--live", issue._option_string_actions)


class DefectAuditTests(AlxTestCase):
    def test_d1_issue_prints_refused_rewild_note(self):
        from contextlib import ExitStack

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        with ExitStack() as stack:
            helper.stub_gates(stack, rewild=False)
            stack.enter_context(
                mock.patch.object(
                    alx.rewild_gate, "run_gate", return_value=["rewild gate refused"]
                )
            )
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue(any(line.startswith("note:") for line in out.splitlines()), out)
        self.assertIn("rewild receipt not issued", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        for prefix in alx.VERIFICATION_NOTE_PREFIX.values():
            self.assertNotIn(prefix, report)

    def test_d3_review_finish_lists_each_path_once(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        paths = []
        for line in out.splitlines():
            if not line.startswith("WARN review/content: "):
                continue
            rest = line.split("WARN review/content: ", 1)[1]
            paths.append(rest.split(":", 1)[0].split()[0])
            if "schema)" in rest:
                self.assertFalse(rest.endswith(" missing"), line)
        self.assertGreater(len(paths), 1, out)
        self.assertEqual(len(paths), len(set(paths)), paths)

    def test_d6_find_prints_one_window_for_two_keywords(self):
        self.init()
        self.fetch("https://example.org/study")
        code, out = self.run_in("find", "S1", "1,204", "documents")
        self.assertEqual(0, code, out)
        hits = [line for line in out.splitlines() if line.startswith("S1 #")]
        self.assertEqual(1, len(hits), out)

    def test_d7_status_names_pdfs_until_report_changes(self):
        from contextlib import ExitStack

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        with ExitStack() as stack:
            helper.stub_gates(stack)

            def fake_render_pdf(input_path, output_path, **kwargs):
                Path(output_path).write_bytes(extractable_pdf_bytes())
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
            code, out = self.run_in("issue")
            self.assertEqual(0, code, out)
            code, out = self.run_in("render")
            self.assertEqual(0, code, out)
            code, out = self.run_in("status")
        self.assertEqual(0, code, out)
        next_line = next(line for line in out.splitlines() if line.startswith("Next:"))
        self.assertIn("report-executive.pdf", next_line)
        self.assertIn("report-atlas.pdf", next_line)
        self.assertIn("report.md", next_line)
        self.assertNotIn("alx render", next_line)
        report = self.dir / "report.md"
        report.write_text(report.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        code, out = self.run_in("status")
        self.assertEqual(0, code, out)
        next_line = next(line for line in out.splitlines() if line.startswith("Next:"))
        self.assertTrue(
            "alx check --fix" in next_line or "alx issue" in next_line, next_line
        )
        self.assertNotIn("deliver report-", next_line)


class HardRefuseTests(AlxTestCase):
    """R33 / §X.A: HARD-refuse at issue/render; check stays non-blocking."""

    BLOCKED = "=== BLOCKED (fix, then alx issue again) ==="

    def helper(self):
        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state", "set_remaining",
            "pad_report", "set_report_words",
        ):
            setattr(issue_tests, name, getattr(self, name))
        return issue_tests

    def ready(self):
        helper = self.helper()
        helper.prepared()
        return helper

    def receipts_written(self):
        return (self.dir / "receipts" / "issue.json").exists()

    def test_quantity_warns_at_issue_and_issue_accepts(self):
        from contextlib import ExitStack

        self.ready()
        batch = self.write_json(
            "qty.json",
            [dict(CLAIM_ONE, claim_id="C9",
                  claim="The archive released 7,777 documents in March 2026.")],
        )
        self.assertEqual(0, self.run_in("claim", "add", batch)[0])
        self.run_in("check", "--fix")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        # R33 (user): the unsupported figure is a warning, never a block.
        self.assertEqual(0, code, out)
        self.assertNotIn(self.BLOCKED, out)
        self.assertIn("ledger/quantity", out)
        self.assertIn("7,777", out)
        self.assertTrue(self.receipts_written(), out)

    def test_semantic_reversal_warns_and_issue_accepts(self):
        from contextlib import ExitStack

        self.ready()
        reversal = alx.finding(
            "fidelity/semantic",
            "Semantic direction reversal in aligned claim: "
            "'sales rose' → 'sales fell'.",
            severity="warn",
        )
        overcap = alx.finding(
            "fidelity/semantic",
            "9 heuristic split-remnant exemptions exceed the limit of 8; "
            "a report with this much structural churn must be re-checked "
            "against the pre-Rewild source and re-drafted, not exempted.",
            severity="warn",
        )
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            stack.enter_context(
                mock.patch.object(alx, "_rewild_findings", return_value=[reversal])
            )
            code, out = self.run_in("issue")
        # R33 (user): a reversal is a warning naming the sentence, never a block.
        self.assertEqual(0, code, out)
        self.assertNotIn(self.BLOCKED, out)
        self.assertIn("fidelity/semantic", out)
        self.assertIn("sales rose", out)
        self.assertIn("sales fell", out)
        self.assertTrue(self.receipts_written(), out)
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            stack.enter_context(
                mock.patch.object(alx, "_rewild_findings", return_value=[overcap])
            )
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue(self.receipts_written(), out)

    def test_unfixed_critical_finding_warns_and_issue_still_accepts(self):
        from contextlib import ExitStack

        self.ready()
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["findings"] = [
            {
                "finding_id": "F1",
                "severity": "critical",
                "category": "evidence",
                "location": "Findings",
                "finding": "The conclusion is unsupported.",
                "disposition": "rejected",
                "rationale": "The reviewer left this critical finding open.",
                "report_disclosure_excerpt": "",
            }
        ]
        path.write_text(json.dumps(note), encoding="utf-8")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        # R33 (user): the unfixed critical finding is a reminder, not a block.
        self.assertEqual(0, code, out)
        self.assertNotIn(self.BLOCKED, out)
        self.assertIn("content/critical-finding", out)
        self.assertTrue(self.receipts_written(), out)

    def test_no_snapshot_refuses_issue_then_accepts_after_snapshot(self):
        from contextlib import ExitStack

        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        self.assertIsNone(alx.Workspace(self.dir).latest_snapshot())
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn(self.BLOCKED, out)
        self.assertIn("no snapshot", out)
        self.assertFalse(self.receipts_written(), out)
        self.assertFalse((self.dir / "report.pre-rewild.md").exists())
        self.run_in("snapshot")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue(self.receipts_written(), out)

    def test_length_two_thirds_boundary(self):
        from contextlib import ExitStack

        self.ready()
        self.set_report_words(4999)
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn(self.BLOCKED, out)
        self.assertIn("integrity/length", out)
        self.assertIn("never pad", out)
        self.assertFalse(self.receipts_written(), out)
        self.set_report_words(5000)
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertTrue(self.receipts_written(), out)

    def test_encoding_refuses_when_restore_fails(self):
        from contextlib import ExitStack

        self.ready()
        (self.dir / "report.md").write_bytes(b"\xff\xfe not utf-8")
        (self.dir / "report.pre-rewild.md").write_bytes(b"\xff\xfe also broken")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn(self.BLOCKED, out)
        self.assertIn("integrity/encoding", out)
        self.assertFalse(self.receipts_written(), out)

    def test_render_returns_1_when_issue_is_blocked(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        code, out = self.run_in("render")
        self.assertEqual(1, code, out)
        self.assertIn(self.BLOCKED, out)
        self.assertFalse(list(self.dir.glob("report-*.pdf")), out)

    def test_render_returns_1_on_empty_pdf_text(self):
        from contextlib import ExitStack

        from scripts import md_to_pdf, render_pdf_pages

        helper = self.ready()
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue")
            self.assertEqual(0, code, out)

            def empty_pdf(input_path, output_path, **kwargs):
                Path(output_path).write_bytes(EMPTY_PDF_BYTES)
                return Path(output_path)

            def fake_pages(pdf_path, output_dir, **kwargs):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                page = Path(output_dir) / "page-001.png"
                page.write_bytes(b"\x89PNG")
                return [page]

            stack.enter_context(
                mock.patch.object(md_to_pdf, "render_pdf", side_effect=empty_pdf)
            )
            stack.enter_context(
                mock.patch.object(
                    render_pdf_pages, "render_pages", side_effect=fake_pages
                )
            )
            code, out = self.run_in("render", "--template", "executive")
        self.assertEqual(1, code, out)
        self.assertTrue((self.dir / "report-executive.pdf").exists())
        self.assertIn("executive PDF check:", out)

    def test_issue_deletes_leftover_prose(self):
        from contextlib import ExitStack

        owner = FixRoundTests("test_leftover_prose_of_a_dropped_claim_is_reported")
        for name in (
            "root", "dir", "run_alx", "run_in", "write_json", "init", "fetch",
            "bootstrap", "draft_report", "ledger", "state",
        ):
            setattr(owner, name, getattr(self, name))
        owner.three_bound_paragraphs()
        self.run_in("claim", "drop", "C1", "--apply")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        restored = report.replace(
            "The registry logged",
            "The archive released 1,204 documents in March 2026, a release "
            "recorded in the study that the registry confirmed.\n\n"
            "The registry logged",
        )
        (self.dir / "report.md").write_text(restored, encoding="utf-8")
        self.pad_report()
        self.run_in("snapshot")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertIn("leftover prose deleted", out)
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "The archive released 1,204 documents in March 2026, a release "
            "recorded in the study that the registry confirmed.",
            report,
        )
        self.assertTrue(self.receipts_written(), out)

    def test_issue_drops_claims_on_cache_detached(self):
        from contextlib import ExitStack

        self.ready()
        meta_path = self.dir / "sources" / "S1.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["text_sha256"] = "0" * 64
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertIn("dropped C1 (fidelity/cache-detached)", out)
        self.assertNotIn("C1", {c["claim_id"] for c in self.ledger()["claims"]})
        self.assertTrue(self.receipts_written(), out)

    def test_status_names_blocked_issue(self):
        from contextlib import ExitStack

        self.ready()
        batch = self.write_json(
            "qty.json",
            [dict(CLAIM_ONE, claim_id="C9",
                  claim="The archive released 7,777 documents in March 2026.")],
        )
        self.run_in("claim", "add", batch)
        self.run_in("check", "--fix")
        for snapshot in self.dir.glob("report.pre-rewild*.md"):
            snapshot.unlink()
        with ExitStack() as stack:
            self.helper().stub_gates(stack)
            self.run_in("issue")
        code, out = self.run_in("status")
        self.assertEqual(0, code, out)
        self.assertRegex(out, r"Next: `alx issue` \(blocked: \d+ items\)")

    def test_check_prints_quantity_under_warn_and_exits_0(self):
        self.ready()
        batch = self.write_json(
            "qty.json",
            [dict(CLAIM_ONE, claim_id="C9",
                  claim="The archive released 7,777 documents in March 2026.")],
        )
        self.run_in("claim", "add", batch)
        self.run_in("check", "--fix")
        code, out = self.run_in("check")
        self.assertIn("ledger/quantity", out.split("=== WARN")[1])
        self.assertEqual(0, code, out)
