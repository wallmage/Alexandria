"""R38 W11a: one test per ruling this worker owns."""

import json
import tempfile
import unittest

from scripts import content_gate, validate_ledger
from tests.test_validate_ledger import fact_claim, valid_quality_ledger


def _fixes(data, *, family=None, needle=""):
    return [
        item
        for item in validate_ledger.collect_findings(data)
        if (family is None or item.family == family)
        and (not needle or needle in item.message)
    ]


class R38_1ReferenceFixPerRuleTests(unittest.TestCase):
    def test_each_reference_rule_carries_its_own_fix(self):
        absent = valid_quality_ledger()
        absent["claims"][0]["claim"] = "No official record exists of the payment."
        [item] = _fixes(absent, needle="records no evidence_of_absence")
        self.assertEqual("ledger/reference", item.family)
        self.assertEqual(
            "set field evidence_of_absence in claims/<file>, then alx claim add claims/<file>",
            item.fix,
        )

        unknown = valid_quality_ledger()
        unknown["claims"][0]["source_ids"] = ["S1", "S2", "S99"]
        unknown["claims"][0]["source_evidence"].append(
            {"source_id": "S99", "extract_or_location": "Missing page."}
        )
        [item] = _fixes(unknown, needle="unknown source S99")
        self.assertEqual("remove S99 from source_ids", item.fix)

        dangling = valid_quality_ledger()
        dangling["claims"][0]["supports"] = ["C99"]
        [item] = _fixes(dangling, needle="unknown claim C99")
        self.assertEqual("remove C99 from supports", item.fix)

        drift = valid_quality_ledger()
        drift["claims"][0]["as_of"] = "2026-08-10"
        drift["claims"][0]["verified_at"] = "2026-07-28"
        [item] = _fixes(drift, needle="as_of 2026-08-10")
        self.assertEqual(
            "set field as_of in claims/<file>, then alx claim add claims/<file>",
            item.fix,
        )

        estimate = valid_quality_ledger()
        estimate["claims"][0]["kind"] = "estimate"
        estimate["claims"][0]["assumptions"] = []
        [item] = _fixes(estimate, needle="must record its assumptions")
        self.assertEqual(
            "set field assumptions in claims/<file>, then alx claim add claims/<file>",
            item.fix,
        )

        cycle = valid_quality_ledger()
        cycle["claims"][0]["supports"] = ["C2"]
        cycle["claims"].append(fact_claim(claim_id="C2", supports=["C1"]))
        [item] = _fixes(cycle, needle="circular support")
        self.assertEqual("remove C1 from supports", item.fix)

        priority = valid_quality_ledger()
        priority["claims"].append(
            fact_claim(claim_id="C2", importance="key", include_in_report=True)
        )
        priority["synthesis"]["central_judgment_claim_ids"] = ["C1", "C2"]
        [item] = _fixes(priority, needle="high-priority research area")
        self.assertEqual("ledger/reference", item.family)
        self.assertIn("C2", item.message)
        self.assertEqual(
            "set coverage[i].claim_ids to include C2 on a high-priority item "
            "in a patch file, then alx ledger merge <patch>",
            item.fix,
        )


class R38_2SourceClassificationFixesTests(unittest.TestCase):
    def test_classification_fix_names_the_flag_and_what_to_write(self):
        key = valid_quality_ledger()
        key["claims"][0]["source_ids"] = ["S1"]
        key["claims"][0]["source_evidence"] = [
            key["claims"][0]["source_evidence"][0]
        ]
        [item] = _fixes(key, family="ledger/key-claim", needle="interested")
        self.assertEqual(
            'fetch an independent page for C1, add it to source_evidence and '
            'alx claim add; or set field importance "supporting" and re-add',
            item.fix,
        )

        family = valid_quality_ledger()
        family["sources"][1]["url"] = "https://records.example.org/other"
        family["sources"][1]["source_family"] = "records-lab"
        [item] = _fixes(family, family="ledger/source-family")
        self.assertEqual(
            "write ≥40 characters on why these pages are one party into "
            "family-justification.txt, then alx source set S1 "
            "--family-justification family-justification.txt",
            item.fix,
        )

        host = valid_quality_ledger()
        host["sources"][1]["url"] = "https://records.example.org/other"
        host["sources"][1]["source_family"] = "example.org"
        [item] = _fixes(host, family="ledger/host-conflict")
        self.assertEqual(
            "write ≥40 characters on why these pages are two parties into "
            "family-justification.txt, then alx source set S1 "
            "--family-justification family-justification.txt",
            item.fix,
        )

        undated = valid_quality_ledger()
        undated["claims"][0]["time_sensitive"] = True
        undated["claims"][0]["as_of"] = "2026-07-28"
        undated["sources"][0]["published"] = None
        undated["sources"][0]["undated_reason"] = "no date shown on the page"
        [item] = _fixes(undated, family="ledger/undated-reason")
        self.assertEqual(
            "write why the page is continuously updated into undated-reason.txt, "
            "then alx source set S1 --undated-reason undated-reason.txt",
            item.fix,
        )

        portfolio = valid_quality_ledger()
        portfolio["sources"][1]["provenance"] = "unverified"
        [item] = _fixes(portfolio, family="ledger/portfolio")
        self.assertEqual(
            "alx source set S1 --provenance primary_independent only if the "
            "page truly is; otherwise fetch an independent one",
            item.fix,
        )

        provenance = valid_quality_ledger()
        provenance["claims"][0]["source_ids"] = ["S1"]
        provenance["claims"][0]["source_evidence"] = [
            provenance["claims"][0]["source_evidence"][0]
        ]
        [item] = _fixes(provenance, family="ledger/provenance", needle="interested")
        self.assertEqual(
            "alx source set S1 --provenance primary_independent only if the "
            "page truly is; otherwise fetch an independent one",
            item.fix,
        )


class R38_3QuantityFixTests(unittest.TestCase):
    def test_quantity_fix_pastes_the_find_window_or_rewords(self):
        data = valid_quality_ledger()
        data["claims"][0]["claim"] = "The registry recorded 53 deaths."
        data["claims"][0]["source_evidence"][0]["extract_or_location"] = (
            "The registry recorded the accountable result."
        )
        data["claims"][0]["source_evidence"][1]["extract_or_location"] = (
            "The independent test reproduces the result."
        )
        [item] = _fixes(data, family="ledger/quantity", needle="'53'")
        self.assertEqual(
            "alx find S1 53 — paste that window into extract_or_location "
            "and alx claim add, or reword the claim",
            item.fix,
        )


class R38_4PatchFileFixesTests(unittest.TestCase):
    def test_coverage_and_synthesis_name_an_anonymous_patch(self):
        coverage = valid_quality_ledger()
        coverage["coverage"][0]["claim_ids"] = ["C2"]
        coverage["claims"].append(fact_claim(status="inference"))
        [item] = _fixes(coverage, family="ledger/coverage", needle="no supported claim")
        self.assertEqual(
            "set coverage[i].claim_ids to supported claim ids in a patch file, "
            "then alx ledger merge <patch>",
            item.fix,
        )
        self.assertNotIn("coverage.json", item.fix)
        self.assertNotIn("alx check --fix", item.fix)

        synthesis = valid_quality_ledger()
        synthesis["synthesis"]["central_judgment_claim_ids"] = []
        [item] = _fixes(
            synthesis,
            family="ledger/synthesis",
            needle="central_judgment_claim_ids",
        )
        self.assertEqual(
            "put C1 in synthesis.central_judgment_claim_ids in a patch file, "
            "then alx ledger merge <patch>",
            item.fix,
        )
        self.assertNotIn("ledger-patch.json", item.fix)
        self.assertNotIn("synthesis.json", item.fix)

        notes = valid_quality_ledger()
        notes["coverage"].append({"area": "faith", "status": "supported"})
        [item] = _fixes(notes, family="ledger/coverage", needle="no claim_ids")
        self.assertEqual(
            "set coverage[i].claim_ids to supported claim ids in a patch file, "
            "then alx ledger merge <patch>",
            item.fix,
        )


class R38_5ContentGateFixAndLanguageTests(unittest.TestCase):
    def test_quality_fixes_and_absent_language_is_dropped(self):
        from tests.test_content_gate import ContentGateTests

        helper = ContentGateTests("test_every_content_family_is_warn_and_the_gate_still_issues")
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, *_ = helper.make_case(directory)
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["brief"].pop("report_language", None)
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            note = json.loads(review.read_text(encoding="utf-8"))
            note["scores"]["writing_clarity"]["score"] = 3
            note["checks"]["counterevidence_tested"] = False
            note["section_reviews"] = []
            note["completion_note"] = ""
            note["findings"] = [
                {
                    "finding_id": "F1",
                    "severity": "critical",
                    "disposition": "rejected",
                },
                {
                    "finding_id": "F2",
                    "severity": "major",
                    "disposition": "accepted_limitation",
                    "report_disclosure_excerpt": "too short",
                },
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            findings = content_gate.run_check(report, ledger, review)
            by_family = {}
            for item in findings:
                if item.family.startswith("content/"):
                    by_family.setdefault(item.family, []).append(item)
            self.assertNotIn("content/language", by_family)
            self.assertEqual(
                "edit reviews/content.json (raise the score), then alx review finish content",
                by_family["content/score"][0].fix,
            )
            check_fixes = {item.message: item.fix for item in by_family["content/check"]}
            self.assertEqual(
                "edit reviews/content.json (set checks true), then alx review finish content",
                check_fixes["checks false: counterevidence_tested"],
            )
            self.assertEqual(
                "edit reviews/content.json (fill sections), then alx review finish content",
                check_fixes["section_reviews empty"],
            )
            self.assertEqual(
                "edit reviews/content.json (fill sections), then alx review finish content",
                check_fixes["completion_note empty"],
            )
            self.assertEqual(
                "edit reviews/content.json (disposition fixed), then alx review finish content",
                by_family["content/critical-finding"][0].fix,
            )
            self.assertEqual(
                "edit reviews/content.json (excerpt ≥40 chars from report.md), "
                "then alx review finish content",
                by_family["content/disclosure"][0].fix,
            )

            payload["brief"]["report_language"] = "zh-CN"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            [lang] = [
                item
                for item in content_gate.run_check(report, ledger, review)
                if item.family == "content/language"
            ]
            self.assertEqual(
                'set brief.report_language "en" in a patch file, then alx ledger merge <patch>',
                lang.fix,
            )


class R38_6SchemaRemedyTests(unittest.TestCase):
    def test_schema_remedy_does_not_append_the_required_name_twice(self):
        self.assertEqual(
            "set field claims.0.claim_id in claims/*.json, then alx claim add claims/*.json",
            validate_ledger.schema_remedy(
                "claims.0.claim_id", "'claim_id' is a required property"
            ),
        )
        self.assertEqual(
            "set field claims.0.claim_id in claims/*.json, then alx claim add claims/*.json",
            validate_ledger.schema_remedy(
                "claims.0", "'claim_id' is a required property"
            ),
        )


class R38_9HttpsFixTests(unittest.TestCase):
    def test_https_fix_is_source_set_url(self):
        data = valid_quality_ledger()
        data["sources"][0]["url"] = "http://records.example.org/result"
        [item] = _fixes(data, family="ledger/https")
        self.assertEqual(
            "alx source set S1 --url https://records.example.org/result",
            item.fix,
        )
