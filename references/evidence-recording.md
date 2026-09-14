# Evidence recording

For every consequential claim, add a ledger entry with:

- a stable claim ID;
- a precise claim;
- fact, reported claim, estimate, or analysis;
- source ID and public HTTP(S) URL;
- publication and access dates;
- `undated_reason` when a living source has no publication date;
- one faithful `source_evidence` extract or source location for every direct
  source; never reuse one source's wording as proof for another;
- evidence type, source family, role, and independence;
- importance, confidence, limitations, and decision relevance;
- the reasoning behind analysis and what would change it;
- honest triangulation status;
- reciprocal supporting or contradicting claim IDs and conflict resolution.

A claim may not assert more than its per-source evidence carries. Figures,
dates, versions, scores, directions, and statuses must be traceable to
`source_evidence`, `derived_assertions`, or — for original arithmetic —
`kind: estimate` with `assumptions`. Record
`verified_at`, the date you re-read the source, separately from `as_of`, the date
the fact was true. `supports` points downward only, to the evidence a claim rests
on; cycles are rejected.

For reports centered on people or sensitive personal claims, inventory known
people through `people` and `person_ids`. Classify every person-linked claim with
`person_claim_role` and a substantive `person_claim_assessment`; do not rely
on supplied IDs alone to decide whether a claim is harmful. Harmful claims
about a living, recently
deceased, or unknown-status person require
`human_harm_review`: exact legal stage, accountable corroboration (or a limited
single-source exception), attribution, resolution search, right of reply, and
privacy relevance. A response must reciprocally name the harmful claim in
`responds_to_claim_ids` and use subject-origin evidence; a resolution must use
`resolves_claim_ids`. Carry either in the same report paragraph.

Mark changing claims such as price, availability, leadership, policy, and
current product behavior as `time_sensitive`, and record a non-null `as_of`
date. The validator treats evidence older than 30 days at delivery as stale
unless the claim is no longer time-sensitive.

Negative existence claims such as “no independent benchmark was found” need
an `evidence_of_absence` record with the queries run, the locations where the
evidence should have appeared, and the search date. Do not turn a search limit
into a factual conclusion.

Mark `include_in_report: true` for every ledger claim used in the draft. After drafting, copy a distinctive sentence of at least 10 characters from each claim-bearing paragraph into that claim's `report_excerpts`. This keeps the internal claim map in the ledger—not the delivered Markdown—and lets the validator locate every used claim in the report.

