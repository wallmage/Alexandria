# Content quality

Use this reference while planning research, building the argument, and reviewing the exact final report. The aim is not to make every report look alike. It is to make every long report repay the reader’s time.

## 1. Write the reader contract

Before searching, state:

- **Reader:** Who will use the report, and what do they already know?
- **Decision or use:** What should the report help them decide, explain, compare, teach, or anticipate?
- **Governing question:** What single question must the report answer?
- **Scope:** What time period, geography, subjects, and comparison basis belong inside the work?
- **Exclusions:** What tempting adjacent questions will the report leave out?
- **Decision-changing questions:** Which unknowns could reverse the conclusion?

For biography, history, or explanatory work, “decision” may mean the judgment or understanding the reader should leave with. Do not force a business recommendation onto a subject that calls for interpretation.

Record the contract in the version-4 evidence ledger. Revisit it when new evidence changes the assignment.

## 2. Build a question architecture

Turn the governing question into three layers.

### Orientation questions

Establish identity, boundaries, definitions, chronology, and current state. These prevent confusion but rarely deserve most of the report.

### Explanatory questions

Reveal mechanisms, causes, incentives, trade-offs, changes over time, and differences between alternatives. These create understanding.

### Decision-changing questions

Test the claims most likely to alter the verdict, recommendation, or interpretation. Give these high priority in the coverage map.

Each coverage item needs:

- a precise question;
- its relevance to the reader;
- the evidence most capable of answering it;
- a completion criterion;
- a priority;
- claim IDs or an explicit gap;
- the effect of that gap on the conclusion.

## 3. Search for disconfirmation

Do not let ordinary search results define the argument. For each plausible conclusion, run at least one query from every relevant family:

| Query family | Purpose |
|---|---|
| Direct evidence | Find the best primary record, dataset, test, or original work |
| Independent corroboration | Check whether a separate source family reaches the same result |
| Failure and limitation | Find breakdowns, boundary conditions, adverse results, and implementation costs |
| Alternative explanation | Test whether another mechanism explains the same observation |
| Stakeholder experience | Discover effects hidden by official or aggregate accounts |
| Correction and update | Find retractions, revisions, later data, version changes, and changed policy |

Search in the original language when it improves recall. For current subjects, include the runtime date, version, jurisdiction, and relevant time window.

Write down the strongest rival explanation before drafting. Record the
hypothesis, test, evidence, outcome, and effect on the conclusion in
`synthesis.adversarial_tests`. If no evidence could change the conclusion, the
conclusion is not being tested.

## 4. Build the right source portfolio

Source count is not quality. Match evidence to the claim.

### Source roles

Use the ledger’s source roles:

- `subject_official`: what the subject says, publishes, or is legally accountable for;
- `counterparty_official`: the comparable or opposing party’s record;
- `independent_analysis`: reporting or analysis independent of the subject;
- `empirical_data`: a dataset, experiment, test, benchmark, measurement, or direct observation;
- `affected_stakeholder`: documented user, worker, customer, community, or participant experience;
- `expert_interpretation`: a qualified interpretation of difficult evidence;
- `historical_record`: a contemporaneous or archival record.

Not every report needs every role. The portfolio must, however, represent the perspectives necessary to answer the governing question.

### Triangulation

For each key judgment:

- **Met:** at least two genuinely independent source families converge.
- **Limited:** the best available evidence comes from one family or one interested side. Reduce confidence and disclose the limitation.
- **Not applicable:** a single accountable record directly establishes a narrow fact, such as a filed figure or published rule. This status is unavailable for key analysis.

Do not inflate independence by counting syndicated stories, copied press releases, several pages from one organization, or studies that reuse the same dataset as separate families.

## 5. Maintain an evidence and reasoning graph

The ledger distinguishes:

- **Fact:** directly verifiable.
- **Reported claim:** attributed to a person or organization.
- **Estimate:** calculated or forecast with assumptions.
- **Analysis:** a conclusion derived from other claims or sources.

It also distinguishes:

- **Key:** changes the central judgment or reader action.
- **Supporting:** explains or substantiates a key judgment.
- **Context:** orients the reader without carrying the verdict.

A key judgment records:

1. the evidence or supported claims beneath it;
2. the reasoning that connects them;
3. why the judgment matters to the reader;
4. what evidence would weaken or reverse it;
5. triangulation status;
6. confidence and limitations;
7. contradictions and their resolution.

Do not hide inference inside factual prose. A transparent reasoning chain is more useful than an unexplained confident sentence.

Use these confidence anchors consistently:

- **High:** direct accountable evidence or converging independent foundations,
  with no unresolved conflict capable of reversing the claim.
- **Medium:** credible but limited evidence, a material inference, or an
  unresolved limitation that narrows the conclusion.
- **Low:** sparse, indirect, disputed, stale, or interested-only evidence.

An analysis or inference supported only by interested sources cannot be high
confidence.

## 6. Resolve contradictions

When sources disagree:

1. compare dates, definitions, samples, methods, incentives, and scope;
2. decide whether the claims truly conflict;
3. link the claims reciprocally in the ledger;
4. state which account is stronger and why;
5. preserve the disagreement when it cannot be resolved;
6. show how the uncertainty affects the conclusion.

Never manufacture balance between evidence of radically different quality. Never erase a material conflict because it complicates the narrative.

## 7. Know when research is complete

Stop when all are true:

- every high-priority coverage item is supported, disputed, or an explicit gap;
- key judgments have an honest triangulation status;
- the strongest counterargument has been tested;
- another search pass is producing repetition rather than a decision-changing source;
- current facts have been checked near the report date;
- remaining uncertainty is identified and its impact is understood.

Record the stop reason. “The report is long enough” is never a valid reason.

## 8. Synthesize before drafting

Build the argument in this order:

1. **Observation:** What does the evidence establish?
2. **Interpretation:** What pattern or mechanism best explains it?
3. **Judgment:** What conclusion follows, at what confidence?
4. **Implication:** What changes for the reader or subject?
5. **Action or takeaway:** What should the reader do, watch, or understand differently?

Test the chain in reverse. If the action lacks a judgment, or the judgment lacks evidence, repair the reasoning before writing prose.

The synthesis record identifies:

- central judgment claim IDs;
- material counterevidence;
- the adversarial tests used to challenge the central judgment;
- implications and their foundations;
- decisions or takeaways, including trade-offs and success and failure signals;
- conditional scenarios when the subject needs an outlook;
- limitations;
- why research stopped.

Every implication, takeaway, and scenario must cite at least one central
judgment directly. Supporting evidence may also be cited, but the decision
logic must never become detached from the report's actual conclusion.

## 9. Design a report worth 30 minutes

Allocate space by decision value, not by the order in which sources were found.

### Executive opening

Give the reader:

- the central judgment;
- the two to four reasons it holds;
- the most important limitation;
- the practical consequence;
- the evidence or event most likely to change the view.

Do not make the reader wait several pages for the answer.

### Section contract

Every substantial section should:

1. answer a reader question;
2. explain the evidence, mechanism, or history;
3. test a credible alternative, limit, or trade-off when material;
4. state why the answer matters to the report’s governing question.

The final content review records those four answers for every non-Sources H2
section. The gate rejects missing, duplicate, extra, or unfinished section
reviews; a section survives only when its final disposition is `keep`.

#### The contract is satisfied across the section, never inside each paragraph

This is a reasoning contract, not a paragraph template, and the distinction decides whether a report reads as written or as generated. Narrative passages may establish the evidence through a documented scene; technical passages may need a worked example; comparisons may need a table.

- The four answers may appear **in any order**, and a section satisfies the contract when its whole span delivers them. The limit may be established before the mechanism. The consequence may already be clear from the executive opening and need only a clause.
- One answer may be **carried by a neighbouring section**. If the previous section tested the trade-off honestly, this one does not repeat the exercise to fill a slot.
- An answer may be **one sentence, a table cell, or a scene**. Weight follows the evidence, not the checklist.
- The contract is **not a rhythm**. If a reader can predict the shape of every paragraph's final sentence, the contract has degraded into a template, and the report has manufactured exactly the uniformity the Rewild gate then has to strip out. Diagnose it directly: read only the last sentence of every paragraph in sequence. If they sound like a list of verdicts, the section is over-contracted, and the fix is to delete most of them rather than to reword them.

Nothing here relaxes coverage. A section that never answers a reader question, or never says why it matters, is still a failed section. The requirement is that the four answers be present, not that they be evenly distributed, separately visible, or delivered in the same order twice.

#### Vary section shape deliberately

Across a report, sections should not all be built the same way. Choose a shape from the evidence rather than from habit:

- **Claim first.** Judgment, then the evidence beneath it, then the boundary. Suits a section whose answer is contested.
- **Investigation.** Follow the question the way the research followed it, including the answer that did not hold. Suits a section where the surprise is the point.
- **Case then generalization.** One worked example in detail, then what it does and does not prove elsewhere.
- **Comparison.** A table carries the parallel criteria; the prose carries only the judgment the table cannot express.
- **Chronology.** Only where sequence itself is the explanation.
- **Anatomy.** Take the mechanism apart component by component, and stop when the parts are described.

A long report should use at least three distinct shapes. Sections also vary legitimately in length. A decisive section may run four pages and a bounding section half a page; forcing them to the same size flattens the argument's own priorities.

### Concrete evidence

Use specific cases, numbers, mechanisms, quotations, timelines, or comparisons when they materially improve understanding. A case must be representative, decisive, or revealing—not merely colorful.

Avoid long stretches of abstraction. After a difficult idea, show the reader how it works in a real or carefully bounded example.

#### Cut prose that restates a table

Prose that walks the reader through rows they can already read is the most common filler in a long report. Where a table carries the comparison, the surrounding prose keeps only what the table cannot hold: which differences are decisive, which are cosmetic, where comparability breaks, and what a particular reader should do about it. Feature enumeration in sentence form is a table waiting to be built. If deleting a paragraph would lose nothing except a spoken version of the table above it, delete it and spend the space on mechanism, counterevidence, or a case.

#### Carry named human specifics

Numbers and mechanisms are the easy half of concrete evidence. Reports routinely arrive full of both and empty of people, and the passage a reader remembers a week later is almost always the one with a named human in it.

A long report needs, at minimum, one of the following per roughly 2,000 words of English or 1,500 non-whitespace characters of Chinese, and never fewer than three in total:

- a **named practitioner, participant, or affected party** whose documented experience tests the argument;
- a **direct quotation** from an identified person or accountable document, quoted accurately and cited;
- a **dated incident**: what happened, on what date, to whom, with what outcome;
- a **worked failure case**: a specific deployment, decision, study, or product that did not work, and the traceable reason.

These must come from the evidence ledger. Do not invent a representative user, compose a plausible quotation, or turn an aggregate into an anecdote about a person. If the evidence genuinely contains no named human specifics, that is a finding about the source base: record it as a coverage gap with its effect on the conclusion rather than papering over it with more abstraction.

### Comparisons

Compare alternatives on consistent criteria that matter to the reader. State:

- why each criterion matters;
- what evidence answers it;
- where comparability breaks;
- which differences are decisive and which are cosmetic.

Do not create a score when the underlying evidence cannot support one.

## 10. Make recommendations usable

When the report calls for action, each recommendation should name:

- **Actor:** who acts;
- **Move:** what they should do;
- **Timing:** when or in what sequence;
- **Evidence:** which judgments justify it;
- **Trade-off:** what the move costs or gives up;
- **Success signal:** what would show it is working;
- **Failure signal:** what would trigger revision or reversal.

For interpretive work, replace recommendations with evidence-backed implications or takeaways. Do not bolt a consulting action plan onto every topic.

## 11. Write conditional outlooks

Forecast only when it helps the reader.

Each scenario needs:

- the conditions that make it plausible;
- leading indicators;
- evidence that would disconfirm it;
- the implication if it occurs;
- supporting claim IDs.

Use probabilities only when a defensible method supports them. Otherwise rank scenarios qualitatively and explain why.

## 12. Run the value-density edit

Review section by section.

Ask:

- What new understanding does this section create?
- Does it advance the governing question?
- Is the evidence stronger than the prose implies, or weaker?
- Is another section making the same point?
- Does the reader need a concrete example, mechanism, comparison, or decision tool here?
- Does the ending state the consequence rather than trail off into detail?

Keep necessary depth, evidence, and context. Remove duplicate explanation, throat-clearing, generic transitions, and background the intended reader already knows. Use the freed space to deepen mechanisms, counterevidence, cases, or implications. Maintain the hard length range through substance.

## 13. Run the final content review

After Rewild, review the exact final report and ledger with no access to drafting rationalizations. Use an independent reviewer when available; otherwise begin a context-isolated fresh-eyes pass.

Score each dimension from 1 to 5:

| Dimension | A score of 4 means |
|---|---|
| Question answered | The governing question receives a clear, bounded answer |
| Evidence strength | Consequential claims use evidence suited to the claim |
| Evidence coverage | Priority questions and material perspectives are covered or disclosed as gaps |
| Reasoning integrity | The path from evidence to judgment is explicit and valid |
| Counterevidence | Strong alternatives and contradictions receive fair tests |
| Explanatory depth | The reader can understand mechanisms, context, and limits |
| Decision value | The report changes what the reader can decide, do, watch, or explain |
| Writing clarity | The long report remains coherent, specific, and readable, **and its sections differ in shape, weight, and rhythm as their evidence requires** |

A 5 is exceptional. It requires unusually strong evidence, synthesis, and execution; do not award it as a courtesy. Every dimension must reach 4 before production.

### The rubric scores substance, not conformity

Uniform compliance is not a strong result. A report in which every section marches through the same purpose, evidence, limitation, consequence beat has satisfied §9 mechanically and failed it in substance, and the reviewer should say so rather than scoring it well because nothing is missing.

Writing clarity therefore cannot be scored on sentence-level readability alone. Run three structural counts on the exact final report:

1. **Closing-sentence census.** Read the last sentence of every body paragraph in order, ignoring the rest. Count how many end on an evaluative verdict rather than on a fact, figure, source, or mechanical explanation. Above roughly 20%, writing clarity cannot reach 4. The editorial reference for the report language names the specific closer templates to search for.
2. **Section-shape census.** Name the shape of each section from the menu in §9. Fewer than three distinct shapes across a long report caps writing clarity at 3.
3. **Section-length spread.** If every section lands within a narrow band of the same length, the report is allocating space by symmetry rather than by decision value. Check that against the §12 finding of which sections carry the verdict.

Record each failure as a finding with `category: structure`, locating the specific sections or paragraphs, and repair it by deleting and rebuilding passages rather than by adding a section for balance.

This test and the §9 Section Contract can appear to pull against each other. They do not. The contract sets what each section must establish; this test confirms it was not established the same way twelve times running. When a reviewer must choose, coverage of the four answers is mandatory and their uniform presentation is a defect.

The required checks and finding fields live in `content-review.schema.json`. Critical findings must be fixed. A major evidence limitation may remain only when the report discloses it in clear language and the review records the exact disclosure excerpt.

Run `scripts/source_fidelity.py --online` first and issue its receipt, then run
`scripts/content_gate.py` after the review with that receipt. Any later change
to the report, ledger, source-fidelity receipt, review note, verifier, or
bundled schemas invalidates the content receipt.
