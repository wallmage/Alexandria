# Person Archetype

Research framework for individual human beings — leaders, founders, scientists, artists, politicians, historical figures, athletes, activists, or anyone whose life and decisions are the subject of study.

## When to Use

The subject is a specific, named individual. The user wants to understand who this person is, what they did, why it matters, and what to make of them.

## Research Dimensions

These dimensions define what to investigate and ensure adequate coverage of. They are **not** chapter headings — the report's TOC should be crafted fresh for each subject with unique, compelling titles. A dimension can span multiple chapters, be woven into other sections, or be combined with another dimension. The goal is coverage, not section-matching.

### One-Line Definition

Who is this person, in one paragraph? Not a biography — a positioning statement. What are they known for, and why do they matter right now?

### Origin Story

This is the backbone of a person report. People are shaped by where they come from.

Cover:
- **Background**: Where and when born, family context, socioeconomic environment, formative culture. Not a dry CV — paint the world they grew up in.
- **Formation**: Education, early influences, mentors, pivotal early experiences. What shaped their worldview before they became known?
- **Inflection points, if any**: Test whether a particular moment, opportunity, or decision changed their path. Some careers have several; others emerge gradually. Do not manufacture a single origin scene.
- **Early moves**: First ventures, first roles, first publications, first failures. What did they do before they became "them"?

The goal is to explain which parts of the person's background genuinely help account for later choices, without treating biography as destiny.

### Arc of Decisions

This replaces a chronological biography. Instead of listing events in order, organize around the **major decisions** this person made — the ones that defined their trajectory.

For each major decision or turning point:
- What was the situation and the options?
- What did they choose, and what did they give up?
- What were the consequences — immediate and long-term?
- What does this decision reveal about how they think?

Structure this as a narrative with causation and tension, not a timeline. The reader should feel the logic chain: "because they did X, they faced Y, which forced them to choose Z."

Include:
- **Successes and failures** — both are essential. A person profile that only covers wins is propaganda, not analysis.
- **Evolution of thinking** — how did their views, strategies, or priorities change over time? Where did they reverse course?
- **Relationships and rivalries** — key collaborators, adversaries, and how those dynamics shaped outcomes.

### How They Operate

What is distinctive about this person's *method*? This isn't biography — it's analysis of their operating style.

Depending on the person, this might cover:
- Decision-making style (data-driven? intuitive? consultative? impulsive?)
- Leadership or communication approach
- Intellectual framework or methodology
- Signature techniques or strategies
- Recurring patterns in how they handle adversity, opportunity, conflict

### State of Play

Where is this person right now? What are they currently doing, building, saying, or facing?

- Current role, projects, or focus
- Recent developments (last 6-12 months)
- Public perception — how are they viewed right now? Has it shifted recently?
- Active controversies or ongoing situations

### Allegations, Harm, and Privacy

This dimension is mandatory whenever the subject is living, recently deceased, or the report will touch wrongdoing, controversy, or reputational damage. A person report is the archetype most capable of harming a real human being, and getting this wrong is not a style defect.

**Never collapse the legal ladder.** Each rung is a different factual claim and must be labelled as what it is:

- *reported*, *alleged*, or *accused* — someone asserted it;
- *investigated* — an authority opened a proceeding, which establishes nothing about the outcome;
- *charged* or *indicted* — a prosecutor filed, which is still an accusation;
- *settled* — resolved without an admission, unless the settlement records one;
- *found liable* — a civil standard of proof;
- *convicted* — a criminal standard;
- *overturned*, *acquitted*, *expunged*, or *retracted* — and this rung must travel with the original claim every time it is mentioned, not once in a footnote.

Write the rung the evidence supports and no higher. "Faced allegations of X" and "did X" are different reports.

**Sourcing floor for living subjects.** Any claim of wrongdoing, misconduct, or personal failing about a living person requires at least two genuinely independent source families, one of which is an accountable record: a court filing, a regulatory action, a named-source investigation by an independent outlet, or the subject's own admission. A single anonymous or single-outlet allegation may appear only as an attributed allegation, with its sourcing weakness stated in the sentence that carries it, and it may never support a key judgment. Aggregation is not corroboration: twenty articles tracing to one original report are one source.

**Right of reply.** Find and include the subject's strongest documented response, not a token denial. If they have not responded publicly, say so and say where you looked. If a documented response contradicts the allegation, that contradiction is evidence and belongs in the ledger.

**Classify before checking.** Every claim that names a registered person must
link that `person_id` and declare `person_claim_role`. This classification,
plus a substantive `person_claim_assessment`, not a finite list of alarming
words, activates the harm and privacy review.
A response claim must use `responds_to_claim_ids`, cite subject-origin
evidence, and travel with the harmful claim in the report. A resolution claim
must use `resolves_claim_ids`; an unrelated fact about the same person is
neither a response nor a resolution.

**Privacy boundary.** Default to excluding health conditions, sexuality, religion, family members, minor children, romantic history, addiction, home address, and non-public financial detail. Include an item only when the subject has made it public themselves, or a court or regulator has made it a matter of record, **and** it materially changes the answer to the report's governing question. "Interesting" and "widely discussed" are not qualifying reasons. Private individuals adjacent to the subject — relatives, former partners, staff, victims — get more protection than the subject, not the same amount, and are usually described by role rather than named.

**Proportionality and staleness.** Weight material by its bearing on the governing question and by how much the subject's public role justifies scrutiny. A sitting official's decades-old conduct in office is fair; a private figure's youthful incident usually is not. Date every allegation and say whether anything has resolved it since. Do not assemble scattered public fragments into a portrait no single source supports, and do not use the report's neutral register to launder an accusation into an established fact.

For historical subjects, the legal-ladder and proportionality rules still hold; the sourcing floor becomes a question of contemporaneous versus later record, and the privacy boundary loosens as living interests recede.

### Context

Reference points — but only where they sharpen understanding.

- **Contemporaries**: Who else operates in the same space? How does this person compare? Only draw comparisons that illuminate something about the subject.
- **Influence**: Who did they influence, and who influenced them?
- **Unique positioning**: What makes them distinct from others in their field?

Do NOT write a section comparing the subject to 3-5 peers across multiple dimensions. That's the organization/product framework leaking in. For people, comparisons are surgical: make a point, move on.

### Verdict

The analytical payoff. This is where you earn the reader's time.

- **Legacy assessment**: What has this person's net impact been? Be specific and honest — including negative impacts.
- **Strengths and blind spots**: What are they genuinely great at, and where are their consistent weaknesses?
- **The contradiction**: Most interesting people have a core tension or contradiction. Name it.
- **Trajectory**: Where are they heading? What are the plausible scenarios for what comes next?
- **The takeaway**: After reading this entire report, what should the reader walk away understanding about this person that they didn't before?

## Evidence scaffold

One row per dimension, matching the coverage-map pattern in `research-protocol.md`. **Best evidence** names the record that would actually settle the question. **Source role** uses the ledger's role vocabulary. **Disconfirming query** is the search to run before believing your own answer; run it even when the dimension looks settled.

Adapt rows to the subject. Where a row names an independent role, the subject's own account, an authorized biography, or a company bio cannot satisfy it.

| Dimension | Best evidence | Source role | Disconfirming query |
|---|---|---|---|
| One-Line Definition | Independent profile or reference entry written without the subject's approval | `independent_analysis` | Who describes this person's significance as overstated, and on what basis? |
| Origin Story | Contemporaneous records: registries, school and employment records, period reporting, archived early work | `historical_record` | Which parts of the origin narrative appear only in the subject's own retellings? |
| Arc of Decisions | Primary artifacts of the decision — filings, memos, interviews given at the time, minutes, the products or papers themselves | `historical_record`, `subject_official` | Who else claims credit for this decision, or says the subject opposed it at the time? |
| How They Operate | Accounts from people who worked directly with the subject, plus observable decision patterns across cases | `affected_stakeholder`, `expert_interpretation` | Where did this signature method fail, and who documented that failure? |
| State of Play | Dated primary records from the last 6–12 months: filings, appointments, published work, direct statements | `subject_official`, `independent_analysis` | What has changed or been retracted since the most recent source I have? |
| Allegations, Harm, and Privacy | Court filings, regulatory actions, named-source investigations, the subject's own documented response | `historical_record`, `independent_analysis`, `subject_official` | Was this allegation resolved, withdrawn, settled, or overturned, and do all my sources trace to one original report? |
| Context | Comparable figures' records on the same measure, evaluated on the same basis | `counterparty_official`, `independent_analysis` | Does the comparison survive if I use the peer's strongest case rather than their weakest? |
| Verdict | Documented outcomes attributable to the subject, including the ones that went badly | `empirical_data`, `independent_analysis` | What is the strongest case that this person's net impact is the opposite of my conclusion? |

## Coverage priority

Spend the most space on the evidence that explains the subject and changes the reader’s judgment. Assign research ownership dynamically from the coverage map; do not force a fixed agent split.

## Coverage ledger mapping

Turn every relevant dimension above into one or more ledger coverage items with
an explicit priority, decision relevance, completion criterion, and evidence
target. If a dimension is relevant but cannot be resolved, keep it in the
ledger as `status: gap` with a concrete `gap_impact`; never omit it silently.
