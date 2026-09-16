# Rewild gate operation

Operational detail for Step 6 of `SKILL.md`. Read this when running the gate,
not while drafting. Lifecycle: `alx snapshot` then humanize; `alx review start rewild`
→ fill note → `alx review finish rewild`. Quotation-lost / control-chars →
`alx snapshot --restore`.

## Snapshot discipline

`alx snapshot` writes `report.pre-rewild.md` once. Never overwrite it. A second
`alx snapshot` writes `report.pre-rewild.iterN.md`.
`alx snapshot --restore` overwrites `report.md` with the latest snapshot.

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
invalid. Record what you changed.

Semantic reversals (direction, negation, causality) are warnings that `alx issue` repeats as reminders; fix the sentence.
Fabricated figures restore the snapshot (as today).

The gate separately caps automatic split-remnant exemptions at eight. More
structural churn than that must be re-checked against the source and re-drafted
rather than absorbed by the heuristic channel.

## Receipt invalidation

Any change to report text after the receipt is written invalidates it. Review the
changed report against the original snapshot, then `alx review start rewild --iter`
and a new receipt. Mechanical deltas (Sources regen, excerpts, whitespace) do
not require `--iter`.

## Blind-review note

`alx review start rewild` writes `reviews/rewild.json` with metadata filled.
Edit it in place. Fill `fidelity_checks` (four booleans) and `findings[]`
(`category` style|region|fidelity, `finding`, `disposition` resolved|rejected,
`reason`). Then `alx review finish rewild`.

```json
{
  "fidelity_checks": {
    "facts_and_figures": true,
    "attribution_and_uncertainty": true,
    "direction_and_negation": true,
    "causality": true
  },
  "findings": [
    {
      "category": "style",
      "finding": "example",
      "disposition": "resolved",
      "reason": "example"
    }
  ]
}
```
