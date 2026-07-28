# Event Archetype

Research framework for wars, crises, elections, revolutions, disasters, incidents, movements, treaties, breakthroughs, or anything that happened (or is happening) within a bounded timeframe.

## When to Use

The subject is something that *occurred* — it has a beginning, a progression, and either an end or an ongoing current state. A current conflict, the 2008 financial crisis, the French Revolution, the Fukushima disaster, the Arab Spring, and the moon landing all map here.

Key distinction from System: events are bounded in time even if their consequences are ongoing. The 2008 crisis is an event; "the global financial system" is a system.

## Research Dimensions

These dimensions define what to investigate and ensure adequate coverage of. They are **not** chapter headings — the report's TOC should be crafted fresh for each subject with unique, compelling titles. A dimension can span multiple chapters, be woven into other sections, or be combined with another dimension. The goal is coverage, not section-matching.

### One-Line Definition

What happened, in one paragraph? When, where, who was involved, and why it mattered. Written so someone who knows nothing about it can orient themselves.

### Causal Chain

This is the most important section for events. Events don't happen in a vacuum — they are the product of causes that compound over time. The reader must understand *why* this happened, not just *that* it happened.

Structure as a narrative that works backward from the event to its roots:

- **Proximate cause**: What directly triggered it? The assassination, the vote, the market collapse, the declaration — the immediate spark.
- **Enabling conditions**: What made the trigger possible? What had to be true for the spark to catch? This is usually a set of conditions that built up over months or years.
- **Deep roots**: What are the structural, historical, or systemic factors that created the enabling conditions? This is where you go back years or decades.
- **Path dependencies**: Which earlier decisions or events changed the odds? Where were the off-ramps, and how plausible were they at the time?

The goal is to explain the strongest causal account while preserving contingency. Test rival explanations and avoid turning the outcome into something that only looks inevitable in hindsight.

**Do not write this as a simple chronology.** The causal chain is an analytical structure — it explains *why*, organized by causal depth, not by date.

### What Happened

The chronological narrative of the event itself. This is where timeline matters.

- **Phases**: Break the event into distinct phases. Each phase gets a narrative subsection.
- **Key moments**: Within each phase, what were the critical turning points, decisions, or developments?
- **Multiple perspectives**: Show the event from different vantage points — different actors, different stakes, different experiences.
- **Specifics**: Dates, numbers, names, locations. This section should be rich with concrete detail.
- **The human element**: What did it feel like on the ground? What were people experiencing? Use specific accounts, quotes, or reported details — not fabricated color.

### Key Players

Who were the decisive actors, and what drove them?

For each key player (individuals or groups):
- Who are they and what was their role?
- What did they want? What were their motivations and constraints?
- What did they actually do? What decisions did they make?
- How did their actions shape the outcome?

This is not a bio section. It's an analysis of agency — who had power, how they used it, and why.

Include:
- **Decision-makers**: The people who made the calls
- **Affected populations**: Who bore the consequences
- **External actors**: Third parties whose involvement (or non-involvement) mattered

### Consequences and Impact

What happened as a result of this event?

- **Immediate aftermath**: What changed in the days and weeks following?
- **Medium-term impact**: What shifted over months and years?
- **Ripple effects**: How did this event affect things beyond its immediate scope? Economic, political, social, technological, cultural consequences.
- **What didn't change**: Sometimes the most interesting analysis is about what *didn't* change despite expectations.

### State of Play

Where things stand now, as of the report date.

- For ongoing events: current situation, latest developments, active dynamics
- For concluded events: lasting legacy, what has endured, what has faded
- Current relevance: why does this event still matter today?

### Context (Reference Points)

Historical parallels or comparisons — **only when they make a specific analytical point.**

Good use: "Unlike Lehman Brothers in 2008, this crisis had a credible backstop from day one, which is why panic stayed contained." (The comparison explains a specific difference in outcome.)

Bad use: "Let us now compare this event to three similar historical events across multiple dimensions." (Forced framework with no point.)

**Rule**: Reference points are footnotes to the analysis, not standalone sections. Work them into the narrative where they add insight. If no comparison adds anything, skip this section entirely.

### Verdict

Analytical synthesis — the "so what?"

- **Why it matters**: Beyond the obvious. What does this event reveal about deeper dynamics?
- **Lessons**: What generalizable insights emerge? Be specific — "this shows that X tends to produce Y" rather than vague "lessons of history."
- **Counterfactuals**: What could have gone differently? Where were the hinge points where a different choice would have led to a different outcome?
- **Future implications**: What does this event set in motion? What should we watch for next?
- **Unresolved questions**: What do we still not know? What will only become clear with time?

## Coverage priority

Spend the most space on the evidence that explains the subject and changes the reader’s judgment. Assign research ownership dynamically from the coverage map; do not force a fixed agent split.

## Coverage ledger mapping

Turn every relevant dimension above into one or more ledger coverage items with
an explicit priority, decision relevance, completion criterion, and evidence
target. If a dimension is relevant but cannot be resolved, keep it in the
ledger as `status: gap` with a concrete `gap_impact`; never omit it silently.
