# Evidence recording

`claim add` validates four things, and only these:

- a unique `claim_id`;
- non-empty claim text;
- a `source_id` that names a fetched source;
- one faithful `source_evidence` extract or source location for that source;
  never reuse one source's wording as proof for another.

Every other field is optional and the gate never asks for it: `kind` (fact,
reported claim, estimate, analysis), importance, confidence, limitations,
`decision_relevance`, `reasoning`, `what_would_change`, `assumptions`,
confirmation status, and supporting or contradicting claim IDs.
Record them when they help the reader; never to satisfy a checker.

A claim may not assert more than its per-source evidence carries. Figures,
dates, versions, scores, directions, and statuses must be traceable to
`source_evidence`, or to a `derived_assertions` entry that says what was
computed. Record
`verified_at`, the date you re-read the source, separately from `as_of`, the date
the fact was true. `supports` points downward only, to the evidence a claim rests
on; cycles are rejected.

What holds a claim about a person is the same thing that holds every other
claim — an extract that carries it, and the exact legal stage where a legal
stage is asserted.

Mark changing claims such as price, availability, leadership, policy, and
current product behavior as `time_sensitive`, and record a non-null `as_of`
date. The validator treats evidence older than 30 days at delivery as stale
unless the claim is no longer time-sensitive.

Negative existence claims such as “no independent benchmark was found” need
an `evidence_of_absence` record with the queries run, the locations where the
evidence should have appeared, and the search date. Do not turn a search limit
into a factual conclusion.

Mark `include_in_report: true` for every ledger claim used in the draft. After drafting, `alx check --fix` writes the first 60 characters of each mapped paragraph into `report_excerpts` (minimum distinctive excerpt: at least 10 characters). Do not hand-edit excerpts. This keeps the internal claim map in the ledger—not the delivered Markdown—and lets the validator locate every used claim in the report.

