# Organization Archetype

Research framework for companies, institutions, government bodies, NGOs, political parties, teams, agencies, or any collective entity with strategy, structure, and stakeholders.

## When to Use

The subject is a named organization. The user wants to understand what it does, how it got here, how it competes, and where it's heading.

## Research Dimensions

These dimensions define what to investigate and ensure adequate coverage of. They are **not** chapter headings — the report's TOC should be crafted fresh for each subject with unique, compelling titles. A dimension can span multiple chapters, be woven into other sections, or be combined with another dimension. The goal is coverage, not section-matching.

### One-Line Definition

What is this organization, in one paragraph? What does it do, for whom, and why does it matter?

### Origin Story

How and why this organization came to exist.

Cover:
- **Founding context**: What was the market, political, or social environment that made this organization possible or necessary? What gap did it fill?
- **Founders**: Who started it, and what was their background? What experiences or beliefs drove the founding? Why were *these people* the ones to do it?
- **Initial vision vs. reality**: What did the founders originally set out to build? How different was the early version from what the organization became?
- **Early survival**: The first years are usually the hardest. What were the early existential threats? What critical decisions or lucky breaks kept it alive?

### Evolution

The full story from founding to present, organized as a narrative — not a timeline.

Structure around **phases**, not dates. Each phase should have:
- A defining characteristic ("the growth phase", "the pivot", "the crisis")
- The core tension or challenge of that phase
- The key decisions made and their consequences
- How one phase led to the next

Cover throughout:
- **Strategic shifts**: When and why did the organization change direction?
- **Key hires/departures**: People who fundamentally changed the trajectory
- **Funding/resource milestones**: Funding rounds, revenue milestones, budget changes, whatever applies
- **Crises and how they were handled**: Controversies, failures, near-death experiences
- **Path dependencies**: Which early decisions locked in later constraints?

### How It Works

The operating model — how this organization actually functions.

Depending on the type of organization:
- **Business model**: How does it make money (or sustain itself)? Revenue streams, cost structure, unit economics if available.
- **Organizational structure**: How is it set up? What's distinctive about its structure?
- **Core capabilities**: What is this organization genuinely better at than others?
- **Culture and values**: Not the PR version — the real operating culture as evidenced by decisions and behavior.
- **Technology/methodology**: If relevant, what's the underlying technical or methodological approach?

### Competitive Landscape

This is where competitive analysis is genuinely valuable — and where the Organization archetype earns its distinct structure.

- **The field**: Which competitors, peers, or alternatives actually clarify the subject's position? Use as many as the evidence requires; skip a peer set when none is meaningful.
- **Positioning map**: Where does each player sit? What does each one optimize for?
- **Differentiation**: What genuinely sets the subject apart? Not marketing claims — real, evidenced differences.
- **User/customer perspective**: What do actual users/customers/stakeholders say? Real sentiment from forums, reviews, discussions. What are the common praises and complaints for each player?
- **Market dynamics**: Is the market growing, consolidating, fragmenting? Who has momentum?

For non-commercial organizations (government bodies, NGOs, parties), adapt: "competitors" become peer institutions, alternative approaches, or political rivals. The analytical frame is the same — what's the landscape, and where does this organization sit in it?

### State of Play

Where the organization stands right now.

- Current strategic focus and priorities
- Recent developments (last 6-12 months)
- Financial health or resource position
- Leadership and any recent changes
- Active challenges or opportunities
- Public perception and momentum

### Verdict

Analytical synthesis and forward look.

- **Strengths and vulnerabilities**: What are the real, durable advantages? What are the structural weaknesses?
- **Strategic logic**: Does the current strategy make sense given the competitive landscape and the organization's history?
- **Historical patterns**: What does the evolution tell us about how this organization responds to challenges? Are there recurring patterns?
- **Future scenarios**: Develop only distinct, evidence-based paths. Name their assumptions, warning signs, and what would make each more or less likely.
- **The bottom line**: What should the reader understand about this organization that isn't obvious from the surface?

## Evidence scaffold

One row per dimension, matching the coverage-map pattern in `research-protocol.md`. **Best evidence** names the record that would actually settle the question. **Source role** uses the ledger's role vocabulary. **Disconfirming query** is the search to run before believing your own answer; run it even when the dimension looks settled.

Adapt rows to the subject. Where a row names an independent role, the organization's own site, press releases, investor deck, or annual report cannot satisfy it. Those establish what the organization says, which is a different claim from what is true.

| Dimension | Best evidence | Source role | Disconfirming query |
|---|---|---|---|
| One-Line Definition | Independent sector analysis or a regulatory classification of what the entity actually does | `independent_analysis` | Which parts of the self-description does no outside source repeat? |
| Origin Story | Incorporation records, early filings, contemporaneous reporting, founders' interviews given at the time | `historical_record` | Which founding-myth elements first appear only in later retellings, and who disputes the founding account? |
| Evolution | Filings, funding records, product archives, and reporting from each phase as it happened | `historical_record`, `subject_official` | Which phase transition looks planned in hindsight but was actually forced, and by whom? |
| How It Works | Audited financials, regulatory filings, unit economics, plus accounts from current and former staff | `empirical_data`, `affected_stakeholder` | Where does the stated business model diverge from where the revenue and costs actually sit? |
| Competitive Landscape | Comparable data measured the same way for every player, plus documented customer and stakeholder experience | `counterparty_official`, `affected_stakeholder`, `empirical_data` | On which criteria does a rival genuinely win, and what would the subject's toughest competitor say about this positioning? |
| State of Play | Dated filings, headcount and financial records, leadership announcements from the last 6–12 months | `subject_official`, `independent_analysis` | What negative development in this period is absent from my sources because only the organization publicizes its own news? |
| Verdict | Measured outcomes over time: retention, share, margin, mission results, or the sector's own metrics | `empirical_data`, `independent_analysis` | What is the strongest evidenced case that the durable advantage I identified is temporary or borrowed? |

## Coverage priority

Spend the most space on the evidence that explains the subject and changes the reader’s judgment. Assign research ownership dynamically from the coverage map; do not force a fixed agent split.

## Coverage ledger mapping

Turn every relevant dimension above into one or more ledger coverage items with
an explicit priority, decision relevance, completion criterion, and evidence
target. If a dimension is relevant but cannot be resolved, keep it in the
ledger as `status: gap` with a concrete `gap_impact`; never omit it silently.
