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

Record the contract in the version-3 evidence ledger. Revisit it when new evidence changes the assignment.

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

This is a reasoning contract, not a mandatory paragraph template. Narrative passages may establish the evidence through a documented scene; technical passages may need a worked example; comparisons may need a table.

### Concrete evidence

Use specific cases, numbers, mechanisms, quotations, timelines, or comparisons when they materially improve understanding. A case must be representative, decisive, or revealing—not merely colorful.

Avoid long stretches of abstraction. After a difficult idea, show the reader how it works in a real or carefully bounded example.

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
| Writing clarity | The long report remains coherent, specific, and readable |

A 5 is exceptional. It requires unusually strong evidence, synthesis, and execution; do not award it as a courtesy. Every dimension must reach 4 before production.

The required checks and finding fields live in `content-review.schema.json`. Critical findings must be fixed. A major evidence limitation may remain only when the report discloses it in clear language and the review records the exact disclosure excerpt.

Run `scripts/content_gate.py` after the review. Any later change to the report, ledger, review note, or bundled schemas invalidates the receipt.
