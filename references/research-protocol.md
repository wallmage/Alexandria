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

The validator normalizes family names and source URLs before counting them. A
key judgment may declare triangulation `met` only when at least two normalized
families converge and at least one foundation is independent of the subject.
An evidence portfolio with no independent source cannot support the governing
judgment. Record the affected coverage as a gap; do not redefine the search
scope so that interested sources appear sufficient.

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
need their own ledger entry. Record the queries run, the repositories or
authorities checked, the date of the search, and where the evidence would
normally appear. Phrase the report as a bounded search result, not proof that
the thing cannot exist.

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
