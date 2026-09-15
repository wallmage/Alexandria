# Artifact Archetype

Research framework for products, technologies, tools, platforms, inventions, protocols, creative works, or any human-made thing that serves a function.

## When to Use

The subject is a specific created thing — a software product, a technology, a protocol, a device, a framework, a drug, a weapon system, a piece of infrastructure. The user wants to understand what it is, how it works, how it got here, what competes with it, and where it's going.

This is the most common archetype for tech-related research. "Research Bitcoin", "Research Cursor", "Research CRISPR", "Research the F-35" all map here.

## Research Dimensions

These dimensions define what to investigate and ensure adequate coverage of. They are **not** chapter headings — the report's TOC should be crafted fresh for each subject with unique, compelling titles. A dimension can span multiple chapters, be woven into other sections, or be combined with another dimension. The goal is coverage, not section-matching.

### One-Line Definition

What is this thing, in one paragraph? What does it do, who uses it, and why does it matter? Written for someone who has never heard of it.

### How It Works

Start with the mechanics. Before the reader cares about the history or the competition, they need to understand what this thing actually *is*.

Cover:
- **Core mechanism**: How does it actually work? Explain the fundamental approach, architecture, or principle. Go as deep as the subject warrants — if it's a technical product, explain the technology. If it's a creative work, explain the structure and craft.
- **Key components**: What are the main parts or features? How do they fit together?
- **User experience**: What does it feel like to actually use/interact with this thing? What's the workflow?
- **Technical choices**: What are the important design decisions? What tradeoffs do they encode?
- **Limitations**: What can't it do? Where does it break down? What are the known weaknesses?

Write for a smart generalist, not a specialist. Use analogies where they help, but don't dumb it down. The reader should finish this section feeling like they genuinely understand the thing.

### Origin Story

How and why this thing came to exist.

- **The problem**: What pain point, gap, or opportunity motivated its creation?
- **The creators**: Who built it? What was their background and what drove them?
- **The moment**: When was it first released/deployed/published? What was the initial reaction?
- **Early form**: How different was the v1 from what exists now?

### Evolution

How the artifact changed from its creation to the present. Organized as narrative, not changelog.

- **Major versions/iterations**: What were the significant leaps? What changed and why?
- **Pivots**: Did the artifact change its core purpose, audience, or approach at any point?
- **Growth trajectory**: How did adoption/usage/impact change over time?
- **Technical evolution**: How did the underlying approach evolve?
- **Community and ecosystem**: If applicable — what grew up around it? Plugins, extensions, forks, integrations?
- **Key inflection points**: What moments fundamentally changed the trajectory? New funding? A competitor entering? A breakthrough feature? A crisis?

### Competitive Landscape

What else exists in this space, and how does the subject compare?

- **Direct alternatives**: Products/technologies that solve the same problem for the same audience. For each: what it does differently, who prefers it and why, relative strengths and weaknesses.
- **Indirect alternatives**: Different approaches to the same underlying problem. Why might someone choose a fundamentally different path?
- **User perspective**: What do real users say? Pull from forums, reviews, GitHub issues, social media. What are the genuine praises and genuine complaints?
- **Positioning**: Where does each player sit? What does each optimize for? What's the tradeoff space?
- **Market dynamics**: Is the space consolidating or fragmenting? Who has momentum?

### State of Play

Where this artifact stands right now, today.

- Current version and recent changes
- Adoption metrics (users, revenue, downloads — whatever applies)
- Current momentum — growing, plateauing, declining?
- Latest developments (last 3-6 months)
- Active controversies or issues
- What the team/creator is focused on next

### Verdict

Analytical synthesis.

- **What it gets right**: The genuine, durable strengths. Not marketing claims — things that hold up under scrutiny.
- **What it gets wrong**: The real weaknesses, limitations, or missing pieces. Be specific.
- **Who it's for (and who it's not for)**: Clear guidance on when this artifact is the right choice and when it isn't.
- **The strategic position**: Given the competitive landscape and the evolution trajectory, where does this artifact sit? Is its position strengthening or weakening?
- **Future outlook**: Where is this heading? What are the key risks and opportunities? What would change the game?
- **The bottom line**: The reader's key takeaway — the thing they should understand about this artifact that isn't obvious from the marketing page.

## Evidence scaffold

One row per dimension, matching the coverage-map pattern in `research-protocol.md`. **Best evidence** names the record that would actually settle the question. **Source role** uses the ledger's role vocabulary. **Disconfirming query** is the search to run before believing your own answer; run it even when the dimension looks settled.

This archetype fails in one predictable way: the vendor's documentation is well written, complete, and free, so the report quietly becomes a summary of it. Documentation establishes what the maker claims and intends. It cannot establish that the thing works, that it works at the stated scale, that users like it, or that it beats an alternative. Any row below naming an independent, empirical, or stakeholder role needs a source the maker did not write. A comparison table built from every vendor's own feature list is not a comparison; it is eleven marketing pages in a grid, and it is worse than no table because it looks like evidence.

| Dimension | Best evidence | Source role | Disconfirming query |
|---|---|---|---|
| One-Line Definition | Independent technical writing or a standards body's description of the category | `independent_analysis` | What does this thing not do that its name and positioning imply it does? |
| How It Works | Source code, specification, protocol document, patent, teardown, or reproducible technical analysis | `empirical_data`, `expert_interpretation` | Which documented capability has no independent demonstration behind it? |
| Origin Story | First release notes, initial commits, launch coverage, the original paper or announcement | `historical_record` | How did informed observers actually react at launch, as opposed to how the origin story is told now? |
| Evolution | Changelogs, version archives, deprecation notices, adoption data over time | `historical_record`, `empirical_data` | Which capability was quietly removed, deprecated, or repriced, and who complained? |
| Competitive Landscape | Independent benchmarks run on the same workload, plus migration write-ups from teams that switched in either direction | `empirical_data`, `counterparty_official`, `affected_stakeholder` | Who evaluated this and chose a rival, and what was their stated reason? |
| State of Play | Current version records, dated pricing, incident and status history, issue trackers, adoption metrics | `subject_official`, `empirical_data` | What are the most-upvoted unresolved complaints, outages, or open issues right now? |
| Verdict | Documented outcomes from real deployments, including abandonments and post-mortems | `affected_stakeholder`, `empirical_data` | Which specific reader profile would be actively worse off choosing this, and what evidence shows it? |

Pricing, limits, model versions, and availability are time-sensitive. Date them, cite the page you read, and mark the claims `time_sensitive` in the ledger.

## Coverage priority

Spend the most space on the evidence that explains the subject and changes the reader’s judgment. Assign research ownership dynamically from the coverage map; do not force a fixed agent split.

## Coverage ledger mapping

Turn every relevant dimension above into one or more ledger coverage items with
an explicit priority, decision relevance, completion criterion, and evidence
target. If a dimension is relevant but cannot be resolved, keep it in the
ledger as `status: gap` with a concrete `gap_impact`; never omit it silently.
