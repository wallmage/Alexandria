# Research protocol

## Coverage map

Read `content-quality.md`. Start from the selected archetype and reader contract. Turn each relevant dimension into a concrete question, priority, decision relevance, owner, evidence target, and completion criterion. Skip irrelevant dimensions. Add cross-cutting questions for incentives, alternatives, risks, and what would change the conclusion.

Example:

| Priority | Area | Question | Best evidence | Complete when |
|---|---|---|---|---|
| High | Current state | What is true as of the report date? | Accountable record plus independent confirmation | Material facts are current and corroborated |
| High | Mechanism | How does it actually work? | Technical record, direct observation, expert analysis | Causal steps, assumptions, and limits are explained |
| High | Outcomes | What happened or is likely to happen? | Measurements, studies, filings, datasets | Main estimates include uncertainty and alternatives |
| Medium | Context | Which history changes the interpretation? | Original and later historical sources | The reader can understand the present without a chronology dump |

## Query design

Use several query families:

- exact subject name and verified aliases;
- domain terms and primary-source repositories;
- criticism, failure, controversy, limitation, and alternative;
- dates, versions, jurisdictions, or geographies that matter;
- source-specific searches for filings, papers, standards, court records, or public data.
- disconfirming searches for failure, criticism, adverse outcomes, boundary conditions, and alternative explanations;
- stakeholder searches for documented user, worker, customer, community, or participant experience;
- correction searches for later revisions, retractions, changed versions, and updated policy.

Use the current runtime date. Search in the source language when it improves recall.

For every provisional key judgment, write the strongest rival explanation and the evidence that would distinguish between them. Search for that evidence before confirming the judgment.

## Source evaluation

Judge sources on two separate axes.

### Provenance and independence

- primary and independent;
- primary but interested or promotional;
- secondary and independent;
- secondary and dependent on another report;
- anonymous, unverifiable, or copied.

### Evidentiary status

- audited or legally accountable record;
- peer-reviewed synthesis or study;
- preprint or working paper;
- official documentation or direct observation;
- independent test or dataset;
- reported interview or contemporaneous reporting;
- opinion, forecast, marketing, or anecdote.

The right source depends on the claim. A filing may establish reported revenue, not product quality. A company announcement may establish its stated plan, not the plan's feasibility. A preprint can be useful but must remain a preprint in the report.

Assign each source a family and one or more roles. Several pages from one publisher, syndicated stories, and studies built on the same underlying dataset do not create independent triangulation.

`source_family` defaults to the source URL's registrable domain, or that
domain's leading label. Any other family name needs a
`family_justification` of at least 40 characters saying why this source is
genuinely independent of the others that share its domain. A declared family
can only ever be coarser than the evidence: the validator merges sources that
share a registrable domain or a publisher whatever they are called, and merges
sources that declare the same family across domains. Two pages on one host may
not carry different independence classes — one marketing, one "independent" —
without that same justification. This is what stops `acme.example.com/pricing`
and `acme.example.com/blog` from triangulating each other.

A key judgment may declare triangulation `met` only when at least two of those
merged families converge and at least one foundation is independent of the
subject. Triangulation counts a claim's direct sources plus at most one
declared level of `supports`; a claim may not inherit a foundation through a
chain.

An evidence portfolio with no independent source cannot support the governing
judgment. Record the affected coverage as a gap; do not redefine the search
scope so that interested sources appear sufficient.

### Support links point downward

`supports` is strictly downward. Listing B in A's `supports` means B is part of
the evidence for A, never the reverse. Mutual pairs and longer cycles are
rejected outright: a cycle collapses the source graph and lets a thinly
sourced claim inherit the whole portfolio.

### Key judgments need a source outside the subject

There is no source minimum. But a key claim whose every direct source carries
only the `subject_official` role is a claim the subject wrote about itself,
and no count of such pages changes that. A key claim needs at least one
foundation source in another role: independent analysis, empirical data, an
affected stakeholder, expert interpretation, or a historical record. When none
exists, that is the finding — record the area as a gap and say so.

### Confidence anchors

- **High:** direct accountable evidence or converging independent foundations;
  no unresolved conflict that could reverse the claim.
- **Medium:** credible but limited evidence, a material inference, or an
  unresolved limitation that narrows the conclusion.
- **Low:** sparse, indirect, disputed, stale, or interested-only evidence.

An analytical inference founded only on interested sources cannot be high
confidence.

## Conflict handling

When reliable sources disagree:

1. check dates, definitions, samples, and incentives;
2. look for a primary record or correction;
3. preserve the disagreement in the ledger;
4. explain which account is stronger and why;
5. lower confidence when the conflict cannot be resolved.

Never average incompatible estimates without a defensible method.

Make contradiction links reciprocal in the ledger. A disputed claim records the disagreement, the resolution or remaining uncertainty, and the effect on the conclusion.

### Evidence of absence

Claims that no equivalent, correction, benchmark, policy, or record was found
need their own ledger entry. Fill `evidence_of_absence.queries`,
`expected_locations`, and `searched_at` with the searches run, the repositories
or authorities checked, and where the evidence would normally appear. Phrase
the report as a bounded search result, not proof that the thing cannot exist.

The validator reads the `claim` text for negative existence — "no published
source measures it", "none was located", "no public equivalent appears to
exist", "we found no third-party audit" — and requires the record whenever it
finds one. Absence decays faster than presence, so `searched_at` must fall
inside the freshness window: a search from last year says nothing about today.

### Claim text may not outrun per-source evidence

Each direct source's `source_evidence.extract_or_location` is authoritative;
the claim-level summary cannot replace it. Every quantity in `claim` must
preserve sign, comparator, magnitude, scale, currency, and measurement
dimension in that evidence, including Arabic and Chinese numerals. The extract
must also name the same complete metric carrier: a bare `20 ms` cannot
substantiate `latency was 20 ms`, and a regional or other qualifier cannot be
dropped. Prefix and postfix comparators must match. Preserve the complete unit
expression, including Unicode temperature symbols, superscripts, and symbolic
or worded compound units. Each `source_evidence` record must carry these
elements independently; values and carriers are never assembled across
sources. Dates,
scores, versions, and every status assertion must likewise match:
patched, deprecated,
discontinued, recalled, retracted, approved, acquired, certified, open source.
The failure this prevents is specific and real: a faithful quote covering the
figures, with an unevidenced clause ("all since patched") appended to the
claim string.

Two narrow exits exist. `derived_assertions` records a computed or inferred
expression with a stated derivation of at least 40 characters; the expression
must appear in the claim, must not already appear in the extract, and must
actually excuse something. A claim carrying more than two is a claim that
should be split. Original arithmetic belongs in `kind: estimate`, whose
`assumptions` state the inputs and the steps; the numbers an estimate derives
are checked against those assumptions.

### Verification is not re-dating

`as_of` is the date the claim was true. `verified_at` is the date its extract
was last re-read against the live source. They are different facts, and moving
`as_of` forward at delivery is not verification. A time-sensitive claim
requires `verified_at` inside the freshness window, and `verified_at` may not
be later than the most recent access date among the claim's own sources.

### Re-reading the source

`scripts/source_fidelity.py` re-fetches a weighted sample of cited pages —
central judgments and key claims first — and checks that each source's own
`source_evidence` still appears in that source. It is the only pass
that checks the ledger against the world rather than the report against the
ledger. Run it with `--online` before delivery. Without `--online` it reports
a visible skip, which is not a pass; an unreachable page is recorded as
unverified, never as verified. Production requires
`--receipt "$SOURCE_FIDELITY_RECEIPT"`; content review rejects a missing or
stale receipt, and final validation verifies that receipt without fetching the
same sources again.

### Freshness records

Mark claims whose truth can change during the report cycle as
`time_sensitive: true`. They require a current `as_of` date and a current
`verified_at`. The validator treats an `as_of` date more than 30 days before
the report date as stale; use a shorter window when the subject moves faster.

The evidence must be as current as the claim, not merely dated. Every
foundation source of a time-sensitive claim must have been `accessed` inside
the freshness window, and must be either published inside it or carry an
`undated_reason` that says the page is continuously updated — "living pricing
page updated in place", not "no date shown". A living page read eight months
ago supports nothing about today.

## Evidence coverage gate

Before drafting, classify each planned conclusion:

- supported by direct evidence;
- supported by converging indirect evidence;
- disputed;
- inference;
- unknown.

Remove or soften conclusions that outrun their evidence. A report may be inconclusive; it may not be falsely certain.

## Research stop

Stop only when:

- every high-priority area is supported, disputed, or an explicit gap;
- key analysis has met triangulation or carries a reduced-confidence limitation;
- the strongest counterevidence and rival explanation have been tested;
- the adversarial test and its effect on the conclusion are recorded;
- current facts have been checked near the report date;
- another search pass is repeating known evidence rather than changing the decision;
- unresolved questions and their effect on the verdict are recorded.

Record the stop reason in the ledger synthesis. Length is never a stopping criterion.
