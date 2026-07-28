# Rewild gate operation

Operational detail for Step 6 of `SKILL.md`. Read this when running the gate,
not while drafting.

## Snapshot discipline

`REPORT_PRE_REWILD_MD` is the draft as it stood before the **first** Rewild
pass. Write it once and never overwrite it. Later iterations — a content-review
fix, a fidelity correction, a re-run after new evidence — write a fresh
per-iteration snapshot instead, for example `<report>.pre-rewild.iter2.md`, and
pass that to `--source` for the iteration's own fidelity diff.

This matters because the delivered `*.pre-rewild.md` is the only public evidence
that humanization happened at all. If each iteration refreshes it, the shipped
file ends up being the draft from just before the last small fix, its diff
against the final report shows a handful of unrelated edits, and the review note
narrates a transformation no artifact corroborates. Keep the original and the
diff stays meaningful.

If the final report is byte-identical to the original snapshot, the review
cannot claim a resolved finding. Record no change, or make the edit.

## Non-rewrite zones

Mark these before editing and leave them alone:

- numbers, dates, names, quotations, units, and official titles;
- citations and their claim placement;
- uncertainty, attribution, severity, and causal limits;
- distinctions between verified fact, reported claim, estimate, and analysis;
- the central conclusion unless new evidence requires a change.

## Blind review

Give the reviewer only the edited report and the selected profile's
quick-reference checklist — never the pre-edit draft, the user request, the
evidence ledger, or drafting notes. The reviewer flags problems and does not
rewrite. Without a separate reviewer, run the profile's fresh-eyes fallback in a
context-isolated pass; never skip the second pass.

The primary agent then applies justified fixes, rejects style changes that would
create a new formula, and checks every material edit against the pre-edit draft
and the evidence ledger. Record findings, dispositions, and the primary fidelity
verification in `REWILD_REVIEW_NOTE` using `references/rewild-review.schema.json`,
bound to the exact report, source, language, and profile by hash. A stale note is
invalid. All four fidelity checks must be true. Region and fidelity findings must
be resolved; they cannot be rejected.

## Style waivers

To keep a retainable statistical style warning, supply a JSON file with
`style_waivers` entries carrying the checker's exact `section`, its exact
`message`, and a specific `reason`, then add `--style-waivers`.

AI-vocabulary, fidelity, region, and Hong Kong register warnings cannot be
waived. The gate classifies every checker warning whose section begins with
`Fidelity` as hard and excludes it from the waiver pool entirely.

## Fidelity notes

Clause-level fidelity findings are deterministic backstops; the bound blind
review remains authoritative for semantic equivalence. When a resolved review
finding legitimately changes meaning against the source, document each edit in a
JSON file matching `references/rewild-fidelity-notes.schema.json` and add
`--fidelity-notes`.

Each entry quotes `source_fragment` and `report_fragment` verbatim from the
source and the final report — matching ignores letter case and nothing else —
with a substantive `reason`. Fragments need at least 15 characters, reasons at
least 40. A note suppresses only findings quoting both fragments, requires a
resolved fidelity finding in the review note, fails closed when unmatched, and is
recorded in the receipt.

Direction reversals, added causal claims, and causal substitutions can never be
acknowledged. Each note covers one clause pair, and at most eight are accepted.
Needing more means the draft should be rewritten, not annotated.

The gate separately caps automatic split-remnant exemptions at eight. More
structural churn than that must be re-checked against the source and re-drafted
rather than absorbed by the heuristic channel.

## Receipt invalidation

Any change to report text after the receipt is written invalidates it. Review the
changed report against the original snapshot, then issue a new receipt.
