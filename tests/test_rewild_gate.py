import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REWILD_ROOT = ROOT / "references" / "rewild"
PROFILES = {
    "en": ("rewild", "en"),
    "zh-CN": ("rewild-zh", "zh"),
    "zh-HK": ("rewild-hk", "hk"),
}


def run_checker(text, *, report_lang, source=None):
    profile, checker_lang = PROFILES[report_lang]
    checker = REWILD_ROOT / profile / "scripts" / "naturalness-check.py"
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        report = work / "report.md"
        report.write_text(text, encoding="utf-8")
        command = [sys.executable, str(checker), str(report), "--lang", checker_lang]
        if source is not None:
            original = work / "source.md"
            original.write_text(source, encoding="utf-8")
            command.extend(["--source", str(original)])
        return subprocess.run(command, capture_output=True, text=True, check=False)


class RewildGateTests(unittest.TestCase):
    def test_each_profile_ships_the_same_complete_checker(self):
        checkers = []
        for profile, _ in PROFILES.values():
            path = REWILD_ROOT / profile / "scripts" / "naturalness-check.py"
            checkers.append(path.read_bytes())
        self.assertEqual(1, len(set(checkers)))

    def test_english_ai_formula_is_blocked(self):
        result = run_checker(
            "In today's rapidly evolving landscape, it is worth noting that "
            "our groundbreaking platform serves as a testament to innovation. "
            "Moreover, it provides a seamless, intuitive, and powerful "
            "experience. In conclusion, the future is bright.",
            report_lang="en",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("warning", result.stdout.lower())

    def test_english_serial_enumeration_is_blocked(self):
        result = run_checker(
            "The system inspects repositories, edits files, runs commands, "
            "opens browsers, delegates work, reviews patches, writes reports, "
            "and publishes results. A short sentence changes the rhythm. "
            "The remaining prose is direct and uses ordinary words. "
            "Readers can verify each claim from the cited record.",
            report_lang="en",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Serial enumeration", result.stdout)

    def test_repeated_short_epigram_closers_are_blocked(self):
        paragraphs = []
        for index in range(5):
            paragraphs.append(
                "The evidence in this section explains the operating constraint "
                "and follows it through the decision with enough detail for a "
                f"reader to verify the reasoning in case {index}. "
                "Controls should follow the risk."
            )
        result = run_checker("\n\n".join(paragraphs), report_lang="en")
        self.assertEqual(1, result.returncode)
        self.assertIn("Paragraph closers", result.stdout)

    def test_simplified_chinese_ai_formula_is_blocked(self):
        result = run_checker(
            "近年来，随着人工智能技术的快速发展，行业经历了深刻变革。"
            "首先，我们全面赋能业务；其次，我们打造创新闭环；"
            "最后，我们将持续深耕。总的来说，未来将更加美好。",
            report_lang="zh-CN",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("warning", result.stdout.lower())

    def test_hong_kong_profile_blocks_wrong_region_vocabulary(self):
        result = run_checker(
            "我們的網路團隊正在更新軟體，專案下星期上線。",
            report_lang="zh-HK",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Taiwan vocabulary", result.stdout)

    def test_fidelity_drift_is_blocked(self):
        source = (
            "Observers cited onboarding friction as a barrier. "
            "Setup took 45 minutes."
        )
        result = run_checker(
            "Onboarding friction is the barrier. Setup took 12 minutes. "
            "We will fix it next week.",
            report_lang="en",
            source=source,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Fidelity", result.stdout)
        self.assertIn("figures not in the original", result.stdout)


class QuotationSpanPairingTests(unittest.TestCase):
    """Field test 4: straight quotes pair sequentially; a short term never flips parity."""

    SOURCE = '每日以"雪耻"开头。他写道："倭寇侮辱,非可以愤激制之"，此后转向强硬。'

    def test_editing_prose_between_quotes_is_not_a_lost_quotation(self):
        from scripts.rewild_gate import _quotation_findings

        report = self.SOURCE.replace("此后转向强硬", "从此转向强硬")
        self.assertEqual([], _quotation_findings(self.SOURCE, report))

    def test_altering_the_quoted_text_is_lost(self):
        from scripts.rewild_gate import _quotation_findings

        report = self.SOURCE.replace("愤激制之", "愤激对之")
        found = _quotation_findings(self.SOURCE, report)
        self.assertEqual(1, len(found))
        self.assertIn('"倭寇侮辱,非可以愤激制之"', found[0].message)

    def test_mask_quoted_spans_keeps_short_ascii_terms(self):
        from scripts.rewild_gate import _mask_quoted_spans

        self.assertEqual(
            'a "xy" b   c',
            _mask_quoted_spans('a "xy" b "long enough" c'),
        )


if __name__ == "__main__":
    unittest.main()


class AlignmentRobustnessTests(unittest.TestCase):
    """Regressions for false positives found on the first full report run."""

    def test_sentence_split_does_not_move_negation_or_predicates(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = (
            "The evidence is genuinely uneven — not because one vendor is "
            "weaker, but because one question could not be answered. "
            "The survey measures trial rather than commitment. "
            "Costs sat above the industry average across every plant."
        )
        # Updated: "trial, not commitment" introduces a negation the source
        # never carried, which is a real finding now that a clause is a whole
        # sentence. The punctuation edit this test is about is the first one.
        report = (
            "The evidence is genuinely uneven, not because one vendor is "
            "weaker but because one question could not be answered. "
            "The survey measures trial rather than commitment. "
            "Costs sat above the industry average across every plant."
        )
        self.assertEqual([], _semantic_fidelity_errors(source, report, "en"))

    def test_identical_clauses_pair_before_fuzzy_alignment(self):
        from scripts.rewild_gate import _aligned_clauses

        source = "The desktop app, the web client, the CLI, and the cloud runner."
        report = (
            "One new opening clause arrives first. "
            "The desktop app, the web client, the CLI, and the cloud runner."
        )
        aligned = _aligned_clauses(source, report, "en")
        for source_clause, report_clause, _ in aligned:
            if source_clause in {
                "the desktop app",
                "the web client",
                "the cli",
                "and the cloud runner",
            }:
                self.assertEqual(source_clause, report_clause)

    def test_citation_with_a_comma_does_not_desynchronize_alignment(self):
        from scripts.rewild_gate import _fidelity_prose, _semantic_fidelity_errors

        # A citation inserted at a sentence end used to cut the sentence into
        # extra clauses — its link text carries a comma — and every clause
        # after it paired with the wrong partner.
        body = (
            "Output rose through the quarter. "
            "The regulator opened an inquiry in March. "
            "Costs stayed above the plan across every plant."
        )
        cited = body.replace(
            "in March.",
            "in March, as [Output fell in March, regulator says]"
            "(https://example.com/a) reported.",
        )
        source = f"# T\n\n## Body\n\n{body}\n"
        report = f"# T\n\n## Body\n\n{cited}\n"
        self.assertEqual(
            [],
            _semantic_fidelity_errors(
                _fidelity_prose(source), _fidelity_prose(report), "en"
            ),
        )

    def test_citation_groups_are_stripped_from_fidelity_prose(self):
        from scripts.rewild_gate import _fidelity_prose

        text = (
            "# T\n\n## Body\n\nUsage grew sharply "
            "([Codex changelog](https://example.com/a); "
            "[Codex pricing](https://example.com/b)).\n\n## Sources\n\n"
            "- [Codex changelog](https://example.com/a)\n"
        )
        prose = _fidelity_prose(text)
        self.assertNotIn("https://example.com/a", prose)
        self.assertNotIn("changelog)", prose)
        self.assertIn("Usage grew sharply", prose)

    def test_quoted_spans_are_visible_in_fidelity_prose(self):
        from scripts.rewild_gate import _fidelity_prose

        # 1edb929: fidelity prose is checker prose. Quoted negation, direction
        # and causal tells stay visible to the semantic tier (WARN).
        source = (
            "# T\n\n## Body\n\nThe minister rejected the plan. "
            "Costs stayed above the forecast.\n"
        )
        report = (
            "# T\n\n## Body\n\nThe minister rejected the plan, saying "
            '"we did not move below the forecast". '
            "Costs stayed above the forecast.\n"
        )
        self.assertNotIn("did not move", _fidelity_prose(source))
        self.assertIn("did not move", _fidelity_prose(report))

    def test_true_direction_reversal_in_edited_clause_still_fails(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = "Quarterly revenue moved above the forecast in March."
        report = "Quarterly revenue moved below the forecast in March."
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(any("direction" in error for error in errors))


class FidelityNotesTests(unittest.TestCase):
    def test_matching_note_suppresses_and_is_recorded(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        errors = [
            "Semantic negation changed in aligned claim: "
            "'which is itself informative' → 'direction is not established'."
        ]
        notes = [
            {
                "source_fragment": "which is itself informative",
                "report_fragment": "direction is not established",
                "reason": "Review-mandated correction of an unsupported ordering.",
            }
        ]
        remaining, acknowledged, unused = _apply_fidelity_notes(errors, notes)
        self.assertEqual([], remaining)
        self.assertEqual([], unused)
        self.assertEqual(1, len(acknowledged))
        self.assertIn("Review-mandated", acknowledged[0]["reason"])

    def test_unmatched_note_is_reported_as_unused(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        remaining, acknowledged, unused = _apply_fidelity_notes(
            ["Semantic negation changed in aligned claim: 'a' → 'b'."],
            [
                {
                    "source_fragment": "never present",
                    "report_fragment": "also absent",
                    "reason": "This note matches nothing and must fail closed.",
                }
            ],
        )
        self.assertEqual(1, len(remaining))
        self.assertEqual([], acknowledged)
        self.assertEqual(1, len(unused))


class FidelityNoteAbuseTests(unittest.TestCase):
    """Fidelity notes are an escape hatch, not a waiver channel."""

    def test_direction_reversal_cannot_be_acknowledged(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        errors = [
            "Semantic direction reversal in aligned claim: "
            "'revenue moved above the forecast' → 'revenue moved below the forecast'."
        ]
        notes = [
            {
                "source_fragment": "revenue moved above the forecast",
                "report_fragment": "revenue moved below the forecast",
                "reason": "An attempted waiver of a genuine reversal, which must never succeed.",
            }
        ]
        remaining, acknowledged, unused = _apply_fidelity_notes(errors, notes)
        self.assertEqual(errors, remaining)
        self.assertEqual([], acknowledged)
        self.assertEqual(notes, unused)

    def test_causal_findings_cannot_be_acknowledged(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        errors = [
            "Causal claim added in aligned claim: "
            "'recovery followed the treatment' → "
            "'recovery happened because the treatment worked'.",
            "Causal substitution detected in aligned claim: "
            "'a configuration error' → 'a network attack'.",
        ]
        notes = [
            {
                "source_fragment": "recovery followed the treatment",
                "report_fragment": "recovery happened because the treatment worked",
                "reason": "An attempted waiver of an invented causal link, which must never succeed.",
            },
            {
                "source_fragment": "a configuration error",
                "report_fragment": "a network attack",
                "reason": "An attempted waiver of a swapped cause, which must never succeed.",
            },
        ]
        remaining, acknowledged, unused = _apply_fidelity_notes(errors, notes)
        self.assertEqual(errors, remaining)
        self.assertEqual([], acknowledged)
        self.assertEqual(notes, unused)

    def test_short_reasons_are_rejected_at_load(self):
        import json
        import tempfile
        from pathlib import Path

        from scripts.rewild_gate import _load_fidelity_notes

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.json"
            path.write_text(
                json.dumps(
                    {
                        "fidelity_notes": [
                            {
                                "source_fragment": "a",
                                "report_fragment": "b",
                                "reason": "too short",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], notes)
            self.assertTrue(
                any("'reason' of 9 characters" in error for error in errors),
                errors,
            )

    def test_tiny_generic_fragments_are_rejected_at_load(self):
        import json
        import tempfile
        from pathlib import Path

        from scripts.rewild_gate import _load_fidelity_notes

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.json"
            path.write_text(
                json.dumps(
                    {
                        "fidelity_notes": [
                            {
                                "source_fragment": "the",
                                "report_fragment": "a",
                                "reason": "Generic fragments would substring-match every finding at once.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], notes)
            self.assertTrue(
                any(
                    "'source_fragment' of 3 characters" in error
                    for error in errors
                ),
                errors,
            )

    def test_one_broad_note_acknowledges_only_its_first_clause_pair(self):
        from scripts.rewild_gate import MAX_FIDELITY_NOTES, _apply_fidelity_notes

        note = {
            "source_fragment": "the metric moved in one direction",
            "report_fragment": "the metric moved the other way",
            "reason": "A single broad note matching many findings must not sweep them all.",
        }
        errors = [
            "Semantic negation changed in aligned claim: "
            f"'the metric moved in one direction {i}' → "
            f"'the metric moved the other way {i}'."
            for i in range(MAX_FIDELITY_NOTES + 3)
        ]
        remaining, acknowledged, unused = _apply_fidelity_notes(errors, [note])
        self.assertEqual(1, len(acknowledged))
        self.assertEqual(len(errors) - 1, len(remaining))
        self.assertEqual([], unused)

    def test_one_note_is_bound_to_a_single_clause_pair(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        note = {
            "source_fragment": "the shared fragment appears here",
            "report_fragment": "the shared replacement appears here",
            "reason": "One documented edit must not acknowledge a second unrelated clause pair.",
        }
        same_pair_negation = (
            "Semantic negation changed in aligned claim: "
            "'the shared fragment appears here in clause one' → "
            "'the shared replacement appears here in clause one'."
        )
        same_pair_association = (
            "Semantic predicate association moved to another claim: "
            "'the shared fragment appears here in clause one' → "
            "'the shared replacement appears here in clause one'."
        )
        other_pair = (
            "Semantic negation changed in aligned claim: "
            "'the shared fragment appears here in a different clause' → "
            "'the shared replacement appears here in a different clause'."
        )
        remaining, acknowledged, unused = _apply_fidelity_notes(
            [same_pair_negation, same_pair_association, other_pair], [note]
        )
        self.assertEqual([other_pair], remaining)
        self.assertEqual(2, len(acknowledged))
        self.assertEqual([], unused)

    def test_duplicate_findings_from_repeated_clauses_are_not_swept(self):
        from scripts.rewild_gate import _apply_fidelity_notes

        note = {
            "source_fragment": "the repeated clause reads one way",
            "report_fragment": "the repeated clause reads another way",
            "reason": "One note covers one edit; an identical edit elsewhere is a second edit.",
        }
        duplicate = (
            "Semantic negation changed in aligned claim: "
            "'the repeated clause reads one way' → "
            "'the repeated clause reads another way'."
        )
        remaining, acknowledged, unused = _apply_fidelity_notes(
            [duplicate, duplicate], [note]
        )
        self.assertEqual([duplicate], remaining)
        self.assertEqual(1, len(acknowledged))
        self.assertEqual([], unused)


class HeuristicExemptionAuditTests(unittest.TestCase):
    """Split remnants use a period cut; comma splits already align the halves."""

    def test_split_exemptions_are_reported_not_silent(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = (
            "The evidence is genuinely uneven not because one vendor is "
            "weaker."
        )
        report = (
            "The evidence is genuinely uneven. Not because one vendor is "
            "weaker."
        )
        exemptions = []
        errors = _semantic_fidelity_errors(source, report, "en", exemptions=exemptions)
        self.assertEqual([], errors)
        self.assertTrue(
            any("split remnant" in entry for entry in exemptions),
            exemptions,
        )

    def test_token_identical_negation_swap_is_not_excused(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = "The costs were not above the benefits this quarter."
        report = (
            "The costs were above the benefits this quarter. "
            "The benefits were not above the costs this quarter."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("negation" in error.lower() for error in errors), errors
        )

    def test_affirmative_rewrite_with_new_content_is_not_excused(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = "The migration path is not safe for production workloads."
        report = (
            "The migration path is safe and recommended for production "
            "workloads. It is not safe."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("negation" in error.lower() for error in errors), errors
        )

    def test_inner_cut_stranding_a_leading_negation_is_not_excused(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = "Not every regression test failed during the release window."
        report = (
            "Every regression test failed during the release window. "
            "Not every regression test."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("negation" in error.lower() for error in errors), errors
        )

    def test_remnant_placed_before_the_prefix_is_not_excused(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        source = "The rollout was approved for every region not for the pilot."
        report = (
            "Not for the pilot. The rollout was approved for every region."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("negation" in error.lower() for error in errors), errors
        )

    def test_ordering_is_enforced_even_when_prefix_and_residual_both_match(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        # The aligned clause IS the source prefix and the negated residual
        # appears verbatim in the report — but before the prefix, not after
        # it. Only the reading-order rule rejects this; a window or
        # substring test would excuse it.
        source = (
            "The fix was verified by the review board this cycle not by the "
            "vendor."
        )
        report = (
            "Not by the vendor. The fix was verified by the review board this "
            "cycle."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("negation" in error.lower() for error in errors), errors
        )


class AssociationExemptionRigorTests(unittest.TestCase):
    """The association exemption must be as strict as the negation one."""

    SOURCE = (
        "The deployment pipeline validates artifacts before publishing. "
        "The registry stores artifacts."
    )

    def _run(self, report):
        from scripts.rewild_gate import _semantic_fidelity_errors

        exemptions = []
        errors = _semantic_fidelity_errors(
            self.SOURCE, report, "en", exemptions=exemptions
        )
        return errors, exemptions

    def test_adjacent_split_remnant_is_still_excused(self):
        # Updated for sentence-level clauses: the remnant is its own sentence.
        errors, exemptions = self._run(
            "The deployment pipeline validates artifacts. Before publishing. "
            "The registry stores artifacts."
        )
        self.assertEqual([], errors)
        self.assertTrue(
            any("Association excused" in entry for entry in exemptions),
            exemptions,
        )

    def test_remnant_that_is_not_the_next_clause_is_rejected(self):
        # The report clause is still a substring of the source clause, so the
        # old containment-only rule excused this; the trimmed tail landed two
        # clauses away, which is a move, not a split.
        errors, exemptions = self._run(
            "The deployment pipeline validates artifacts. "
            "The registry stores artifacts. Before publishing."
        )
        self.assertEqual([], exemptions)
        self.assertTrue(
            any("association moved" in error.lower() for error in errors),
            errors,
        )

    def test_remnant_reattached_to_another_carrier_is_rejected(self):
        errors, exemptions = self._run(
            "The deployment pipeline validates artifacts. The registry "
            "retains them before publishing."
        )
        self.assertEqual([], exemptions)
        self.assertTrue(
            any("association moved" in error.lower() for error in errors),
            errors,
        )

    def test_reworded_residual_is_rejected(self):
        errors, exemptions = self._run(
            "The deployment pipeline validates artifacts. Prior to publishing. "
            "The registry stores artifacts."
        )
        self.assertEqual([], exemptions)
        self.assertTrue(
            any("association moved" in error.lower() for error in errors),
            errors,
        )


class DocumentFallbackCoverageTests(unittest.TestCase):
    def test_rhetorical_no_doubt_does_not_negate_a_direction_reversal(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        stable = " ".join(
            f"Stable operating statement number {index}." for index in range(1, 10)
        )
        source = stable + " Vermilion aqueduct metrics increased."
        report = (
            stable
            + " There is no doubt that Peregrine sundial tallies decreased."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("Unmatched directional claim" in error for error in errors),
            errors,
        )

    def test_aligned_causal_effect_cannot_be_substituted(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        cases = (
            (
                "Regulator intervention caused the outage.",
                "Regulator intervention caused a price collapse.",
            ),
            (
                "The outage happened because the regulator intervened.",
                "A failure happened because the regulator intervened.",
            ),
            (
                "Revenue increased because demand rose.",
                "Costs increased because demand rose.",
            ),
        )
        for source, report in cases:
            with self.subTest(report=report):
                errors = _semantic_fidelity_errors(
                    source, report, "en"
                )
                self.assertTrue(
                    any("Causal" in error for error in errors),
                    errors,
                )

    def test_high_alignment_cannot_hide_an_unmatched_directional_replacement(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        stable = " ".join(
            f"Stable operating statement number {index}." for index in range(1, 10)
        )
        source = stable + " Vermilion aqueduct metrics increased."
        report = stable + " Peregrine sundial tallies decreased."
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("Unmatched directional claim" in error for error in errors),
            errors,
        )

    def test_reused_cause_cannot_be_attached_to_a_new_unmatched_effect(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        stable = " ".join(
            f"Stable operating statement number {index}." for index in range(1, 9)
        )
        source = (
            stable
            + " Delays occurred because the regulator intervened. "
            + "The closing observation concerns staffing."
        )
        report = (
            stable
            + " Delays occurred because the regulator intervened. "
            + "Profits collapsed because the regulator intervened."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("Causal claim added in unmatched claim" in error for error in errors),
            errors,
        )

    def test_one_unmatched_causal_clause_cannot_hide_behind_broad_alignment(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        stable = " ".join(
            f"Stable operating statement number {index}." for index in range(1, 10)
        )
        source = stable + " Vermilion aqueduct metrics changed during the quarter."
        report = (
            stable
            + " Peregrine sundial tallies changed because the regulator intervened."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any("Causal claim added" in error for error in errors),
            errors,
        )

    def test_one_surviving_clause_does_not_disable_the_fallback(self):
        from scripts.rewild_gate import _aligned_clauses, _semantic_fidelity_errors

        source = (
            "Constant boilerplate clause. "
            "Vermilion aqueduct metrics increased. "
            "Basalt kestrel ledger. Juniper falcon tally. Cobalt lantern index."
        )
        report = (
            "Constant boilerplate clause. "
            "Peregrine sundial tallies decreased. "
            "Marmalade obelisk figure. Sorrel harrier count. Thistle beacon gauge."
        )
        # One clause survives byte-identically, which used to make the
        # document-level backstop unreachable.
        self.assertEqual(1, len(_aligned_clauses(source, report, "en")))
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertTrue(
            any(
                error.startswith("Semantic direction reversal: source uses")
                for error in errors
            ),
            errors,
        )

    def test_broadly_aligned_documents_skip_the_fallback(self):
        from scripts.rewild_gate import _semantic_fidelity_errors

        # Updated for sentence-level clauses: the contrast sentence is its own
        # sentence, because one clause carrying both direction terms now reads
        # as a reversal.
        source = (
            "Costs are above the average across every plant we reviewed. "
            "None fell below it."
        )
        report = (
            "Across every plant we reviewed, costs remain above the average. "
            "None fell below it."
        )
        self.assertEqual([], _semantic_fidelity_errors(source, report, "en"))


class CitationStripperTests(unittest.TestCase):
    def test_balanced_parentheses_in_a_url_leave_no_artifact(self):
        from scripts.rewild_gate import _fidelity_prose

        text = (
            "# T\n\n## Body\n\nUsage grew sharply "
            "([Wikipedia entry](https://en.wikipedia.org/wiki/Foo_(bar))).\n\n"
            "## Sources\n\n"
            "- [Wikipedia entry](https://en.wikipedia.org/wiki/Foo_(bar))\n"
        )
        prose = _fidelity_prose(text)
        self.assertIn("Usage grew sharply.", prose)
        self.assertNotIn("wikipedia.org", prose)
        self.assertNotIn("Wikipedia entry", prose)
        self.assertNotIn("(bar)", prose)

    def test_balanced_parentheses_survive_an_inline_link(self):
        from scripts.rewild_gate import _fidelity_prose

        text = (
            "# T\n\n## Body\n\nThe "
            "[Foo (bar) release](https://en.wikipedia.org/wiki/Foo_(bar)) "
            "shipped late.\n\n## Sources\n\n"
            "- [Foo (bar) release](https://en.wikipedia.org/wiki/Foo_(bar))\n"
        )
        prose = _fidelity_prose(text)
        self.assertIn("The Foo (bar) release shipped late.", prose)
        self.assertNotIn("wikipedia.org", prose)

    def test_multi_citation_group_with_parenthesised_urls_is_stripped(self):
        from scripts.rewild_gate import _fidelity_prose

        text = (
            "# T\n\n## Body\n\nAdoption doubled "
            "([One](https://example.com/a_(x)); "
            "[Two](https://example.com/b_(y))).\n\n## Sources\n\n"
            "- [One](https://example.com/a_(x))\n"
        )
        prose = _fidelity_prose(text)
        self.assertIn("Adoption doubled.", prose)
        self.assertNotIn("example.com", prose)

    def test_crlf_and_empty_body_sections_are_handled(self):
        from scripts.rewild_gate import _fidelity_prose

        crlf = (
            "# T\r\n\r\n## Body\r\n\r\nUsage grew sharply "
            "([Source](https://example.com/a)).\r\n\r\n"
            "## Sources\r\n\r\n- [Source](https://example.com/a)\r\n"
        )
        prose = _fidelity_prose(crlf)
        self.assertIn("Usage grew sharply", prose)
        self.assertNotIn("example.com", prose)

        empty_body = "# T\n\n## Body\n\n## Sources\n\n- [S](https://example.com/a)\n"
        empty_prose = _fidelity_prose(empty_body)
        self.assertNotIn("example.com", empty_prose)
        self.assertEqual(["T", "Body"], empty_prose.split())


class LoaderDiagnosticsTests(unittest.TestCase):
    """A rejected note or waiver must say which entry broke which rule."""

    def _write(self, directory, payload):
        import json

        path = Path(directory) / "entries.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_note_diagnostics_name_the_entry_and_the_rule(self):
        from scripts.rewild_gate import _load_fidelity_notes

        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                {
                    "fidelity_notes": [
                        {
                            "source_fragment": "a properly quoted source fragment",
                            "report_fragment": "a properly quoted report fragment",
                            "reason": "x" * 38,
                        },
                        "not an object",
                    ]
                },
            )
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], notes)
            joined = " ".join(errors)
            self.assertIn(
                "Fidelity note 1 has a 'reason' of 38 characters", joined
            )
            self.assertIn("the minimum is 40", joined)
            self.assertIn("Fidelity note 2 must be a JSON object.", joined)

    def test_note_file_shape_is_diagnosed(self):
        from scripts.rewild_gate import _load_fidelity_notes

        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, {"fidelity_notes": {}})
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], notes)
            self.assertIn("'fidelity_notes' array", " ".join(errors))

    def test_notes_file_is_validated_against_the_bundled_schema(self):
        from scripts.rewild_gate import (
            FIDELITY_NOTES_SCHEMA,
            _load_fidelity_notes,
        )

        self.assertTrue(FIDELITY_NOTES_SCHEMA.is_file())
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                {
                    "fidelity_notes": [
                        {
                            "source_fragment": "a properly quoted source fragment",
                            "report_fragment": "a properly quoted report fragment",
                            "reason": "A reason long enough to satisfy the documented minimum length.",
                            "waiver": "an unrecognised field that must not be accepted",
                        }
                    ]
                },
            )
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], notes)
            self.assertTrue(
                any(
                    FIDELITY_NOTES_SCHEMA.name in error for error in errors
                ),
                errors,
            )

    def test_valid_notes_load_cleanly(self):
        from scripts.rewild_gate import _load_fidelity_notes

        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                {
                    "fidelity_notes": [
                        {
                            "source_fragment": "a properly quoted source fragment",
                            "report_fragment": "a properly quoted report fragment",
                            "reason": "A reason long enough to satisfy the documented minimum length.",
                        }
                    ]
                },
            )
            notes, errors = _load_fidelity_notes(path)
            self.assertEqual([], errors)
            self.assertEqual(1, len(notes))

    def test_waiver_diagnostics_name_the_entry_and_the_rule(self):
        from scripts.rewild_gate import _load_style_waivers

        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                {
                    "style_waivers": [
                        {
                            "section": "Rhythm (statistical)",
                            "message": "",
                            "reason": "A long enough reason.",
                        },
                        {
                            "section": "Rhythm (statistical)",
                            "message": "Sentence lengths cluster",
                            "reason": "too short",
                        },
                    ]
                },
            )
            waivers, errors = _load_style_waivers(path)
            self.assertEqual({}, waivers)
            joined = " ".join(errors)
            self.assertIn("Style waiver 1 needs the checker's exact 'message'", joined)
            self.assertIn("Style waiver 2 has a 'reason' of 9 characters", joined)


class ConsoleEncodingTests(unittest.TestCase):
    class _LegacyStream:
        encoding = "cp1252"

    def test_arrow_findings_survive_a_legacy_windows_console(self):
        from scripts.rewild_gate import _console_safe

        message = (
            "[FAIL] Semantic negation changed in aligned claim: "
            "'a claim' → 'another claim'."
        )
        safe = _console_safe(message, self._LegacyStream())
        safe.encode("cp1252")
        self.assertIn("->", safe)
        self.assertNotIn("→", safe)

    def test_utf8_streams_keep_the_original_text(self):
        from scripts.rewild_gate import _console_safe

        class _Utf8Stream:
            encoding = "utf-8"

        message = "'系统' → 'system'"
        self.assertEqual(message, _console_safe(message, _Utf8Stream()))

    def test_unencodable_text_never_raises(self):
        from scripts.rewild_gate import _console_safe

        safe = _console_safe("报告 → report", self._LegacyStream())
        safe.encode("cp1252")


class StyleMaskingTests(unittest.TestCase):
    """1edb929: checker prose is unmasked; quoted and linked words are scored."""

    def test_quoted_semicolons_and_halfwidth_punctuation_are_counted(self):
        body = "本节说明制度如何运作以及资金怎样流动。" * 8
        quoted = "「原文写道:数据由三家机构提供;结论并未改变,亦无补充说明。」"
        result = run_checker(body + quoted, report_lang="zh-CN")
        self.assertIn("half-width mark(s) inside Chinese text", result.stdout)

    def test_ai_vocabulary_inside_a_quotation_is_charged_to_the_writer(self):
        quoted = (
            '"This groundbreaking and seamless platform is a testament to '
            'our comprehensive, cutting-edge vision."'
        )
        plain = (
            "The committee published the record in March. "
            "Two members dissented and filed a separate note. "
            "The vote was recorded in the minutes. "
        )
        flagged = run_checker(plain + quoted.strip('"'), report_lang="en")
        masked = run_checker(plain + quoted, report_lang="en")
        self.assertIn("catalog hits", flagged.stdout)
        self.assertIn("catalog hits", masked.stdout)

    def test_blockquotes_and_link_text_keep_their_prose(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "naturalness_check",
            REWILD_ROOT / "rewild" / "scripts" / "naturalness-check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text, stats = module.strip_markdown(
            "## A groundbreaking heading\n\n"
            "> A seamless quoted paragraph.\n\n"
            "The committee met and voted, see "
            "[the comprehensive record](https://example.com/a).\n"
        )
        self.assertNotIn("groundbreaking", text)
        self.assertIn("seamless", text)
        self.assertIn("comprehensive", text)
        self.assertIn("The committee met and voted", text)
        self.assertEqual(1, stats["heading"])
        self.assertNotIn("quote", stats)
        self.assertNotIn("link", stats)


class VerificationNoteMaskTests(unittest.TestCase):
    """The machine-written note (spec §6.9) is never scored as the writer's prose."""

    NOTE = (
        "核查说明：C3、C7 的在线核验未通过，涉及 12.5% 的数值差异；"
        "S4 在核验时无法访问。"
    )

    def _run(self, paragraph):
        from scripts.rewild_gate import run_check

        base = (ROOT / "tests" / "fixtures" / "golden" / "zh-CN" / "report.md").read_text(
            encoding="utf-8"
        )
        offset = base.rfind("\n## ")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            source.write_text(base, encoding="utf-8")
            report.write_text(
                f"{base[:offset]}\n\n{paragraph}\n{base[offset:]}", encoding="utf-8"
            )
            return run_check(report, source, lang="zh-CN")

    def test_prefixes_cover_every_report_language(self):
        from scripts.report_blocks import VERIFICATION_NOTE_PREFIXES

        self.assertEqual({"en", "zh-CN", "zh-HK"}, set(VERIFICATION_NOTE_PREFIXES))
        self.assertEqual("核查说明：", VERIFICATION_NOTE_PREFIXES["zh-CN"])

    def test_note_paragraph_is_masked_from_every_tier(self):
        unprefixed = self.NOTE.split("：", 1)[1]
        self.assertTrue(
            any(
                "figures not in the original" in finding.message
                for finding in self._run(unprefixed)
            )
        )
        self.assertEqual([], self._run(self.NOTE))


class SeverityTableTests(unittest.TestCase):
    """R28: fabrication and evidence integrity block; everything else warns."""

    def test_every_downgraded_family_is_warn_and_never_blocks(self):
        from scripts.gate_severity import hard_errors
        from scripts.rewild_gate import _finding

        for family in (
            "rewild/region",
            "rewild/ai-vocabulary",
            "rewild/style",
            "rewild/length",
            "rewild/checker",
            "fidelity/semantic",
            "review/rewild",
        ):
            with self.subTest(family=family):
                item = _finding(family, "message")
                self.assertEqual("warn", item.severity)
                self.assertEqual("A", item.klass)
                self.assertEqual("", item.remove)
                self.assertEqual([], hard_errors([item]))

    def test_fabrication_and_integrity_stay_hard(self):
        from scripts.gate_severity import hard_errors
        from scripts.rewild_gate import _finding

        for family in (
            "fidelity/rewild",
            "fidelity/quotation-lost",
            "integrity/control-chars",
        ):
            with self.subTest(family=family):
                item = _finding(family, "message")
                self.assertEqual("hard", item.severity)
                self.assertEqual("F", item.klass)
                self.assertEqual([item], hard_errors([item]))
