# Alexandria Content Quality System

## Purpose

Alexandria already checks citations, report length, PDF integrity, and naturalness. The next release must also prove that a long report answers the reader’s question, tests its own argument, uses evidence with appropriate independence, and converts research into useful judgment.

The existing length limits remain unchanged:

- English: 7,500–15,000 words.
- Simplified Chinese or Hong Kong Traditional Chinese: 5,000–10,000 non-whitespace characters.
- Production target: roughly ten or more finished PDF pages.

The system will deepen weak sections instead of shortening the report or padding it.

## Quality model

The upgrade has four layers.

### 1. Decision-led research brief

Every evidence ledger records the intended reader, the decision or use the report should support, the time and geographic scope, exclusions, and the questions most likely to change the conclusion. Coverage items carry a priority, completion criterion, decision relevance, and the effect of any unresolved gap.

This prevents a broad topic survey from displacing the user’s actual question.

### 2. Evidence and reasoning graph

The ledger distinguishes key judgments from supporting and contextual claims. Key judgments record:

- the reasoning from evidence to conclusion;
- the decision relevance;
- the evidence that would weaken or reverse the judgment;
- whether triangulation is met, limited, or not applicable;
- source-family independence;
- contradictions and their resolution.

A synthesis record binds the central judgment, counterevidence, implications, practical takeaways, scenarios, limitations, and the reason research stopped.

### 3. Report-bound content gate

After Rewild, a fresh-eyes reviewer evaluates the exact final report and ledger. The reviewer scores:

- question answered;
- evidence strength;
- evidence coverage;
- reasoning integrity;
- counterevidence;
- explanatory depth;
- decision value;
- writing clarity.

Every dimension must score at least 4 out of 5. Critical findings must be fixed. A major unresolved evidence limitation may pass only when the final report states it plainly. The gate binds the report, ledger, review note, and schema by hash, so later edits invalidate the receipt.

### 4. Value-density editorial pass

The drafting reference will require each substantial section to perform a clear job: answer a reader question, explain the evidence or mechanism, test a credible alternative, and state why the result matters. The editor will remove duplicate explanation, strengthen weak transitions, and add concrete cases, comparisons, or decision tools where evidence supports them.

The pass will not force identical chapter templates. Biography, history, technical explanation, market analysis, and investigative work retain their appropriate forms.

## Evidence rules

1. High-priority coverage must end as supported, disputed, or an explicit gap.
2. A gap must state how it limits the report’s conclusion.
3. Key analytical judgments need at least two independent source families unless triangulation is marked limited and confidence is reduced.
4. A single-source fact may mark triangulation not applicable when the source is the authoritative record for that fact.
5. Disputed claims must link to contrary claims, and contradiction links must be reciprocal.
6. Every key judgment used in the report must appear in the synthesis and in a high-priority coverage area.
7. Recommendations and implications must cite the judgments that justify them and name trade-offs, success signals, and failure signals.
8. Forecasts must state conditions, leading indicators, and disconfirming evidence. The report must not invent probabilities.

## Content review contract

The review note is an internal production artifact. It contains:

- exact report, ledger, language, and file hashes;
- eight quality scores with concise rationales;
- required boolean checks;
- findings with severity, location, disposition, and rationale;
- disclosed evidence limitations;
- a completion note.

The gate rejects:

- a score below 4;
- a missing or stale hash;
- an unresolved critical finding;
- a major accepted limitation that is not disclosed in the final report;
- a report or ledger that fails the existing structural and evidence checks.

## Compatibility

The evidence ledger moves to schema version 2. Old ledgers remain readable as historical artifacts but must be upgraded before producing a new Alexandria report. The PDF renderer and template portfolio remain unchanged.

## Verification

Tests will prove:

- incomplete priority coverage fails;
- unsupported or weakly triangulated key judgments fail;
- asymmetric contradictions fail;
- disputed claims without a resolution fail;
- synthesis references and recommendation foundations are valid;
- stale or low-scoring content reviews fail;
- disclosed limitations can pass when the review and report agree;
- the full English and Chinese fixture pipeline still renders and validates;
- the installed skill behaves identically to the repository copy.
