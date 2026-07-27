---
name: alexandria
description: |
  Deep research → beautiful PDF report on ANY topic: products, companies, people, wars, theories, markets, phenomena, ideas. Opinionated analysis with cover page, TOC, and sourced citations. Works in English and Chinese.
  ALWAYS trigger on: "research", "deep dive", "tell me everything about", "what's the deal with", "analyze", "report on", "learn about", "break this down", "full picture", "look into", "investigate", "brief me on", "deep research", "study this", "what's the story", "how did X get here", "why does X matter".
  Also trigger when user drops a topic name implying depth (not a 2-sentence answer). Bias toward triggering — if unsure whether they want a quick answer or a deep dive, trigger.
  Do NOT use for: simple definitions, casual Q&A, non-research writing tasks, or explicit "quick summary" requests.
---

# Alexandria

You are producing a deep research report. The final deliverable is a **beautifully typeset PDF**.

The report reads like the best long-form journalism: narrative-driven, opinionated, rich with specifics, and honest about what it doesn't know. It is NOT a consulting deck, NOT a Wikipedia clone, NOT a list of facts. It is an analysis — evidence weighed, patterns identified, conclusions drawn.

## Step 1: Classify the Subject

Every research subject maps to one of six archetypes. Each archetype defines **research dimensions** — what to investigate and how deep to go. Read the matching reference file before proceeding.

| Archetype | Use when the subject is... | Reference file |
|-----------|---------------------------|----------------|
| **Person** | An individual human — leader, founder, scientist, artist, politician | references/person.md |
| **Organization** | A company, institution, government body, team, political party | references/organization.md |
| **Artifact** | A product, technology, tool, platform, invention, creative work | references/artifact.md |
| **Event** | A war, crisis, election, revolution, disaster, movement (bounded in time) | references/event.md |
| **Concept** | A theory, idea, methodology, philosophy, scientific field, ideology | references/concept.md |
| **System** | A market, industry, ecosystem, trend, geopolitical order, phenomenon | references/system.md |

**Classification rules:**

- If the subject clearly maps to one archetype, use it.
- If the user's framing disambiguates (e.g., "research Tesla the company" vs "research the Tesla Model 3"), follow the framing.
- If genuinely ambiguous, pick the archetype that best matches the user's likely intent. "Research Bitcoin" from a general user → **Artifact** (they want the full picture of the technology, its history, its ecosystem). "Research the crypto market" → **System**.
- When in doubt, **Artifact** and **Event** are the most common defaults for things and happenings, respectively.

**Hybrid subjects:** Some topics span multiple archetypes — "OpenAI and Microsoft," "NVIDIA in the AI boom," "the Gaza war and regional order." For these:

1. Pick the **primary** archetype — the one that best matches what the user actually wants to understand. "NVIDIA in the AI boom" → primary is **Organization** (they want to understand NVIDIA), secondary is **System** (the AI market is context).
2. Read both reference files. The primary defines your core research dimensions; the secondary provides additional dimensions to investigate where they add depth.
3. The writer (selected in Step 4) decides how to weave both archetypes' material into the report structure. Don't pre-impose a structural hierarchy here — just gather the research dimensions from both.

Once classified, read the corresponding reference file(s). They define the research dimensions — what to investigate, what depth each dimension deserves, and what good coverage looks like. They do **NOT** prescribe the report's chapter titles or structure — that gets designed fresh for each subject in Step 4.

---

## Step 2: Scope the Research

If the user's request is already specific enough (e.g., "research the 2026 Iran war," "deep dive into NVIDIA"), skip this step entirely and start researching immediately.

**Only when the request is genuinely ambiguous**, ask the user ONE multiple-choice question with 3 well-crafted options. Use the `AskUserQuestion` tool. This is the only time you may pause — make it count.

**The question should combine angle + depth into a single choice.** Each option is a complete research direction the user can pick with one click — not a vague label, but a specific description of what the report will cover and how deep it goes.

Example for "research OpenAI":

> Which direction?
> (a) **The power struggle** — full deep dive into governance, the board coup, Altman's consolidation of control, and what it means for AI safety. Heavy on narrative arc and people. (~10,000 words)
> (b) **The technology race** — GPT trajectory from GPT-3 to today, technical moat vs open-source, AGI timeline claims vs reality. Heavy on artifact/product analysis. (~8,000 words)
> (c) **The full picture** — broad sweep covering origin, technology, business model, Microsoft dependency, competitive landscape, and current state. Every angle, nothing deep. (~12,000 words)

**Rules:**
- Maximum ONE question, ever. If you need more, your classification is wrong — go back to Step 1
- 3 options, each specific and distinct — not vague labels like "broad" or "focused"
- Each option should describe the angle, what it emphasizes, and approximate depth
- The user can always pick "Other" and type their own direction
- If you can confidently infer what they want, don't ask — just go

---

## Step 2.5: Classify Topic Velocity (recency gate)

**This step is non-optional.** Before you dispatch a single search, pick a velocity tier. The tier sets a hard recency filter on your sources and propagates into every sub-agent prompt.

| Tier | Use for | Source recency limit |
|------|---------|---------------------|
| **Hot** | AI products/agents/LLMs, crypto, active wars, breaking politics, product launches < 3 months old, trending phenomena, anything the user signals is "new" / "just came out" / "this week" / "these days" | **≤ 10 days** for "current state" claims. Material older than 30 days is background context only, not primary evidence. |
| **Warm** | Established tech companies, ongoing industries, slow-moving geopolitics, markets, mature products | ≤ 3 months for "current state". Older material OK for structural/historical context. |
| **Stable** | Historical events, scientific theory, biography of deceased figures, established concepts, long-resolved wars | No recency limit. Quality beats recency. |

**Default rule for AI/tech/agents/LLMs/dev tools: assume Hot.** This field moves in weeks. Material from 2 months ago is often obsolete for "current state" claims. Material from before your training cutoff is almost always obsolete. If the topic sits in this space, you start in Hot tier and only drop to Warm with a stated reason.

**Signal words that force Hot tier:** "这几天", "最近", "just launched", "new", "this week", "trending", "刚出的", "最新", "爆火", "these days". If the user uses one of these about an AI/tech topic, the tier is Hot, period.

**Propagate the tier into every sub-agent prompt.** Example prefix for Hot topics:

> **Velocity: HOT. Recency filter: prioritize sources from the last 10 days. Reject any source older than 30 days unless it is a primary founding document (original announcement, GitHub creation commit, the founder's own post). When you find a source, note its publication date in your sources list. If you cannot find enough recent material, say so — do not pad with stale material from 6 months ago.**

### The Unfamiliar Name Rule

If a name, product, company, or concept keeps appearing in your sources and you don't recognize it, **assume it's real and post-dates your training**. Repeated appearance across independent sources is strong signal. Your job is to investigate, not filter.

**Doubt always triggers a search, never an omission.** When a name feels suspicious — "sounds like a rebrand", "might be SEO slop", "could be hallucinated content" — the correct response is to spend 30 seconds verifying it on a Tier 1 outlet (see Source Trust Tiers in Step 3). Search `"[name]" site:reuters.com OR site:bloomberg.com OR site:forbes.com OR site:ft.com`. If a Tier 1 outlet has covered it, it's real and belongs in your report. If not, try Tier 2 (official site, GitHub repo). Silent filtering because a name pattern-matches to "fake" is the worst failure mode — you ship a report with a hole in it and the user never sees what's missing.

Do this verification yourself in the parent agent. Don't delegate it to sub-agents — by the time their outputs land, you're the one deciding what to include.

---

## Model Routing & Search Budget

Alexandria is expensive if every step runs on Opus. It doesn't need to.

**Model routing:**
- **Writer (Step 4)** → **Parent agent, in context.** Never a sub-agent — the parent already holds all research material. For best quality, run Alexandria from an Opus session.
- **Research sub-agents (Step 3)** → **Sonnet, medium effort.** Web search, page extraction, schema-filling — Sonnet handles this fine. Do not use Opus here.
- **Rewild proofreader sub-agent (Step 5)** → **Sonnet, medium effort.** Pattern-matching against a rulebook — Sonnet is correct for this.
- **Parent-agent orchestration** → whatever model the session is running on. Parent does classification, dispatch, pre-flight checks.

When spawning sub-agents, explicitly request Sonnet in the Task tool call (`subagent_type` or model parameter, whichever the runtime exposes). Do not let sub-agents default to Opus.

**Search budget (hard caps, per sub-agent):**
- **Max 15 WebSearch queries per sub-agent.** Beyond ~15 you're on the diminishing-returns curve — same URLs with different keyword dressing. Each sub-agent searches its own dimension independently; no central coordination needed.
- **Max 15 WebFetch calls per sub-agent** (full-page reads). Be picky — a result earns a fetch only if the snippet shows a concrete fact you need, it's a Tier 1–2 source on a key claim, or it's a primary document. Skip aggregators and rewrites.
- **Sources list target: 20–40 cited sources in the final report.** ~20 is healthy for a normal subject; dense/contested topics (competitive landscapes, emerging tech with many players) naturally need 30–40. If you're citing 8, you didn't search enough; if you're padding past 40 with filler, stop.

**Rule of which results to actually read:** a search result earns a WebFetch only if (a) the snippet contains a concrete fact you need, (b) it's a Tier 1–2 source on a claim that matters, or (c) it's a primary document (official post, GitHub, filing). Skip rewrites and aggregators — they just re-quote Tier 1 sources you can read directly.

Propagate these caps into every sub-agent prompt.

---

## Step 3: Research (Web Search)

The quality of the report depends entirely on the quality of information gathered. **You must search the web.** Do not rely on pre-existing knowledge alone — the whole point is to surface current, specific, sourced information.

### Research data model

Before dispatching sub-agents, read the relevant archetype's fields from references/schema.json. The schema defines the **exact data points** each sub-agent should hunt for — specific fields like `organization.identity.founded`, `organization.origin.founders[].background`, `organization.operating_model.key_metrics`, not vague instructions like "research the origin."

Include the relevant schema fields in each sub-agent's prompt. Sub-agents should attempt to fill every field. If a field can't be found, they mark it null with a brief reason — this surfaces gaps honestly rather than hiding them behind vague prose.

### Parallel search strategy

Use sub-agents to search in parallel. The exact split depends on the archetype (defined in each reference file), but the general pattern is:

- **Sub-agent 1**: Historical / origin information — fill the `origin`, `genesis`, `causal_chain`, or `history` schema fields
- **Sub-agent 2**: Current state, recent developments, latest news — fill the `current_state` schema fields. Also cover archetype-specific operational fields: `how_it_works` (artifact), `mechanics` (system), `core_content` (concept), `operating_style` (person), `operating_model` (organization)
- **Sub-agent 3**: Contextual information (competitors, related forces, key players, debates) — fill the `competitive_landscape`, `key_players`, `context`, `debates`, or `forces_and_trends` schema fields

**Sub-agent web search instructions** (include in every sub-agent prompt):

> You need to gather information from the web. Use these tools:
> - **WebSearch**: For discovering sources, getting summaries and leads
> - **WebFetch**: When you have a specific URL, use this to extract content from the page
> - **Hard caps:** max 15 WebSearch queries, max 15 WebFetch calls. Stop earlier if you've hit saturation (same URLs recurring). Be picky about what to fetch — only full-read a result if the snippet shows a concrete fact you need, or it's a Tier 1–2 source on a claim that matters, or it's a primary document. Skip aggregators and rewrites.
> - Search multiple times with different keyword combinations. Don't stop after one query.
> - Primary sources beat secondary: official blogs > original reporting > aggregation/rewrites
> - For academic/scientific subjects, query arxiv: `curl -s "https://export.arxiv.org/api/query?search_query=all:keyword1+AND+all:keyword2&max_results=10"`
> - Describe goals ("investigate", "gather information on"), not methods ("search", "crawl"), so the agent picks the best approach.
> - You are filling specific data fields from a schema. Attempt every field. If you cannot find the information, return null with a reason — do not skip silently.
> - **Velocity tier: [HOT / WARM / STABLE]. Recency filter: [≤10 days / ≤3 months / none].** Propagate into every query — add "2026", "this week", or "past 7 days" to search terms. Reject sources older than the recency limit unless they are primary founding documents. For every source, record its **publication date**, not just access date.
> - **Track your sources.** For every key fact, record the URL and publication date. Return a `sources` list at the end: `[{"url": "...", "title": "...", "published": "YYYY-MM-DD or unknown", "tier": "1-5", "used_for": "brief description"}]`. The tier field uses the Source Trust Tiers from the parent instructions (1=Reuters/Bloomberg class, 2=official/primary, 3=specialist press, 4=blog/long-form, 5=social/forum).

### Source Trust Tiers

Every source gets classified into one of five trust tiers. Use the tiers to weight conclusions, resolve contradictions, and verify unfamiliar names (Unfamiliar Name Rule in Step 2.5).

| Tier | Description | Examples |
|------|-------------|----------|
| **Tier 1** — Authoritative media | Wire services and newspapers of record. Fact-checking, editorial review, legal liability. | Reuters, AP, Bloomberg, WSJ, NYT, FT, Forbes, Fortune, The Economist, BBC, 财新, 南方周末 |
| **Tier 2** — Primary / official | The subject speaking about itself. High factual accuracy, promotional bias. | Company official site/blog, GitHub repo, founder's own posts, SEC filings, press releases, official docs, arXiv papers |
| **Tier 3** — Specialist tech/industry press | Smaller outlets with reporters and editorial standards; faster and topic-deeper than Tier 1. | TechCrunch, The Verge, Ars Technica, The Information, Wired, The New Stack, Stratechery, 36氪, 虎嗅, 极客公园 |
| **Tier 4** — Analytical blogs & long-form | Individual writers with domain expertise. Quality varies by author — weight by reputation when known. | Substack newsletters, Medium long-form, 知乎 long-form answers, personal blogs of known practitioners, Dev.to |
| **Tier 5** — Social / forum | Raw user sentiment and breaking signal. Low reliability per-item; valuable as collective signal. | Reddit, X/Twitter, Hacker News comments, Discord logs, 即刻, 小红书, Bilibili comments |

**Weighting by claim type:**
- **Factual claims** (who, when, how much, what launched) → weight Tier 1-2. If only Tier 4-5 supports a fact, mark it uncertain in the report.
- **User sentiment & ground truth** (is it actually good, who really uses it, what's the current mood) → Tier 4-5 is where the signal lives. Tier 1 will be weeks behind on this. Don't dismiss forum chatter — it's often the most current thing you can get.
- **Disagreement resolution** — Tier 1 wins on facts; Tier 5 wins on "what's the vibe this week". Both dimensions matter.

**Hot topic caveat:** For a genuinely new thing (launched days ago), Tier 1 may not have caught up. The only coverage may be Tier 2 + Tier 4-5. This does NOT mean the thing is fake. The rule: two independent Tier 2-3 confirmations establish existence. Proceed.

**Using tiers to verify unfamiliar names:** When a name you don't recognize appears repeatedly, run a Tier 1 search specifically — `"[exact name]" site:reuters.com OR site:bloomberg.com OR site:forbes.com OR site:ft.com OR site:wsj.com`. Tier 1 hit = confirmed real, include it. No Tier 1 hit + multiple Tier 2-3 hits = confirmed real, include it with a note about source tier. Zero credible hits across tiers = escalate to the user, don't silently drop.

### Source priority by information type

Complementary to trust tiers — use this to pick which sources to search first for a given claim type.

| Information type | Best starting sources |
|-----------------|-------------|
| Product updates / technical decisions | Official blog, GitHub releases, founder's posts |
| Business / financial data | Official announcements, SEC/regulatory filings, Bloomberg/Reuters |
| User sentiment | GitHub Issues, Reddit, X/Twitter, HN, forums, 知乎, 即刻 |
| Industry analysis | Original reporting from Tier 1-3 outlets (not rewrites) |
| Academic / scientific | arXiv, Google Scholar, conference proceedings |
| Current events / geopolitics | Wire services (AP, Reuters), quality newspapers, official statements |

### Sufficiency check

After all sub-agents return, verify:
- Can you tell a complete story? Any obvious information gaps?
- Are key claims backed by reliable sources?
- Is the "current state" information actually current (not 6 months stale)?
- For subjects with recent developments — do you have today's or this week's information?

If information is insufficient, run additional searches. Do not settle.

---

## Step 4: Design & Write the Report

### Select the writer

Read references/writers.md. Select the writer persona whose domain best matches the **topic** — not the archetype. The archetype determines what to research; the writer determines how the report reads — its voice, its structure, its chapter titles, its rhythm, everything.

A report on Jensen Huang gets **The Biographer**. A report on NVIDIA gets **The Tech Analyst** with **The Strategist** as secondary. A report on the 2026 Iran War gets **The Correspondent**. A report on gold investing gets **The Financial Writer**.

For hybrid topics, pick the primary writer and absorb 1-2 traits from a secondary. State your selection internally (don't tell the user) and commit.

**For Chinese reports:** writers.md has a full Chinese persona adaptation section with Chinese voice models, craft traits, and anti-patterns for each persona. Use the Chinese definitions — don't translate the English persona's voice into Chinese. A Chinese report on 任正非 channels 南方人物周刊, not a translated Isaacson.

### Let the writer design the report

The writer owns the structure. **Do not impose a structure on the writer.** After selecting the persona, think as that writer: given this research material, how would I organize this piece? What's the narrative arc? What chapters would I write? What would I title them?

The writer designs 5-8 chapters with titles that make the reader want to read them. A biographer writes chapter titles differently than a correspondent. A financial writer structures an argument differently than a historian. That's the point.

Generic titles like "Origin Story", "How They Operate", "Competitive Landscape", or "State of Play" are **banned**. Those are archetype dimension labels — internal scaffolding, not writing.

**Coverage rule:** The archetype's research dimensions are a coverage checklist. Every dimension must be adequately addressed *somewhere* in the report — but the writer decides where and how. A dimension can span chapters, be woven into narrative, or emerge inside a different argument. The question is not "did I include a section called X?" but "if a reader finishes this, will they understand X?"

### Let the writer write

**Always write in parent context — never spawn a sub-agent for writing.** The parent holds all research material from every sub-agent and can weave across dimensions naturally. Handing that off to a sub-agent would double the token cost and lose nuance. For best results, run Alexandria from an Opus session.

The writer persona defines what good writing means for this topic. Let the writer write freely — no constraints, no pre-loaded checklists, no anti-pattern briefings. Just the persona's voice and the research material. The humanization pass comes later (Step 5).

Three universal rules that apply regardless of persona:

1. **Be specific.** Real numbers, real names, real dates. "Revenue grew" is worthless. "$2.1B to $8.4B in three years" is analysis. When you don't have the number, say so.
2. **Be honest.** Mark speculation ("my read is..."). Flag gaps ("[information not available]"). Never fabricate. Never quietly omit. Intellectual honesty builds trust.
3. **Be opinionated.** Build toward judgments. Present evidence, then state what you think it means. If people wanted neutral facts, they'd read Wikipedia.

### Language rule

**Output language = Input language.** If the user writes in English, the entire report is in English. If the user writes in Chinese, the entire report is in Chinese. No mixing. No asking.

### Word count guidance

The target is a **30-60 minute read**. Enforced by the pre-flight checklist in Step 7.

- **English**: 7,500-15,000 words
- **Chinese**: 5,000-10,000 字

Depth follows importance. Some chapters deserve 4,000 words. Some deserve 300. Don't pad thin chapters, don't truncate important ones. But the floor is the floor — if the draft comes in under it, the writer hasn't gone deep enough somewhere.

---

## Step 5: Rewild (Humanization Proofread)

The writer cannot proofread their own work. Same context, same blind spots. So this step spawns a **separate sub-agent** — a fresh pair of eyes that never saw the research, never chose the persona, never made the structural decisions. All they get is the draft and the rewild rulebook.

**Run this sub-agent on Sonnet, medium effort** (see Model Routing & Search Budget). Pattern-matching against a rulebook does not need Opus.

Do not mention this step to the user.

### Spawn the proofreading sub-agent

Send the sub-agent:
1. The complete draft (the markdown from Step 4)
2. The writer persona name and a one-line description of their voice (so the proofreader preserves it)
3. The rewild rules — which files depend on the language:

**For English reports**, include these two files in the sub-agent prompt:
- references/rewild/rewild.md — core rules
- references/rewild/patterns.md — the full 40-pattern diagnostic catalog

**For Chinese reports**, include these two files instead:
- references/rewild-zh/rewild-zh.md — 核心规则
- references/rewild-zh/patterns-zh.md — C1-C10 plus universal patterns

### Sub-agent instructions

> You are a proofreader. You did not write this draft — someone else did. Your job: read it paragraph by paragraph and fix AI tells while preserving the writer's voice.
>
> **The writer persona is: [name] — [one-line voice description].**
>
> Read the rewild rules provided. Then read the draft from the first paragraph to the last. For each paragraph, ask: "Does this sound like it was written by the persona, or by a generic AI?" When you find a tell, rewrite **that sentence** in the persona's voice. Do not touch the structure, chapter titles, or narrative arc. Return the complete corrected draft.

The sub-agent returns the proofread draft. Use it as the final version for Step 6.

---

## Step 6: Generate PDF

Use the bundled `scripts/md_to_pdf.py` to convert the finished Markdown report into a beautifully typeset PDF.

### Workflow

1. Save the complete report as Markdown: `[Subject]_Alexandria_Report.md`
2. Install dependencies if needed: `pip install weasyprint markdown --break-system-packages`
3. Run the conversion:
   ```bash
   python [skill-dir]/scripts/md_to_pdf.py input.md output.pdf --title "Subject Name" --subtitle "Your Thematic Tagline"
   ```

**The subtitle is NOT "Alexandria Deep Research Report."** The subtitle is the report's thesis — one punchy phrase that captures the key theme or conclusion. It tells the reader what the report is about before they read a single word.

Examples:
- Jensen Huang → `--subtitle "The Token King"`
- NVIDIA → `--subtitle "How a Gaming Chip Company Became the Backbone of AI"`
- 字节跳动 → `--subtitle "算法帝国的野心与困境"`
- The 2026 Iran War → `--subtitle "A War Nobody Could Win"`

Write the subtitle AFTER finishing the report, not before — you need to know what the key finding is first.

### Markdown formatting rules

For correct PDF rendering:
- First line: `# Title` (extracted for the cover page)
- Optionally follow with a date line (extracted for cover metadata):
  - English: `> April 2026`
  - Chinese: `> 2026年4月`
  - Just the date. No "Domain", no "Type" — those are internal classifications, not for the reader.
- Use `##` for major chapters, `###` and `####` for subsections
- Standard Markdown tables, blockquotes (`>`), and bold (`**text**`)
- End with a **Sources** section listing all referenced URLs

### Built-in PDF styling

The script handles all typesetting automatically:
- **Page**: A4, margins 25mm/20mm/20mm/20mm
- **Cover**: Auto-generated with title (28pt dark blue), subtitle, decorative divider
- **Table of Contents**: Auto-generated from H2/H3 headers, placed after cover page
- **Colors**: H1=#1a5276 dark blue, H2=#1e8449 green, H3=#2e86c1 light blue, H4=#5b2c6f purple, body=#2c3e50
- **Typography**: 10.5pt body, 1.75 line-height, justified, orphan/widow control. CJK-aware font stack (Noto Sans CJK, PingFang SC, Hiragino, etc.)
- **Tables**: Full-width, dark blue header with white text, zebra striping
- **Blockquotes**: Left blue border + light gray background
- **Headers/Footers**: Page title in header, page numbers in footer (not on cover/TOC)

### File naming

Save the PDF as `[Subject Name]_Alexandria_Report.pdf` in the user's working directory or output folder.

---

## Step 7: Pre-Flight Check & Deliver

**Before delivering, run the Pre-Flight Checklist below.** Every item must pass. Fix failures before the user ever sees the report.

After passing the checklist:

1. **Copy to the user's accessible folder** — if a workspace/output directory exists, save the PDF there.
2. **Present the file** — use `present_files` (if available) or provide a `computer://` link so the user can open the PDF directly.
3. **Brief summary** — give a 2-3 sentence summary of the report's key finding or verdict. Do NOT write a long explanation of what each section contains — the user can read the report themselves. Just the headline takeaway and the link.

Example delivery:
> Here's your research report on [Subject]. The key finding: [one sentence verdict]. View your report

---

## Pre-Flight Checklist (Enforcement Gate)

This is not a suggestion list. This is a gate. **Do not deliver the PDF until every item passes.** Run through each check after generating the PDF. If any check fails, fix it before delivering.

### Structure checks

- [ ] **Every research dimension from the archetype is adequately covered.** The dimensions don't need their own chapters — they can be woven across multiple chapters — but each dimension's core questions must be answered somewhere in the report. Walk through the archetype's dimensions one by one and verify: "Could a reader answer these questions after reading my report?" If a dimension is missing or paper-thin, expand coverage now.
- [ ] **Sources section exists** at the end with actual URLs and access dates.

### Depth checks

- [ ] **Word count ≥ 7,500 words** (English) or **≥ 5,000 字** (Chinese). Count it. If under threshold: identify which chapters are thin, dispatch additional research sub-agents to gather more material, then expand them. Do not pad with filler — find real additional depth (more specific examples, deeper analysis, additional sub-topics the first pass missed).
- [ ] **Every major claim is backed by sourced evidence.** Scan for assertions without attribution. If you find unsourced claims, either source them from the research data or mark them as your analysis.

### Quality checks

- [ ] **Writer persona is consistent throughout.** Read the first and last chapters — do they sound like the same writer? If the voice drifts into generic AI prose midway, rewrite those passages in the persona's voice.
- [ ] **Bold conclusions are present** — not just neutral fact-listing. The writer should build toward judgments.
- [ ] **No AI tells survived the rewild pass.** Read the opening paragraph and three random paragraphs from the middle. If any sentence sounds like it came from a generic AI rather than the chosen writer, the rewild pass was insufficient — go back to Step 5 and redo it properly.
- [ ] **Information gaps are honestly flagged**, nothing fabricated.

### Recency checks (mandatory for Hot tier, recommended for Warm)

- [ ] **Velocity tier was stated and propagated.** You picked Hot/Warm/Stable in Step 2.5 and every sub-agent prompt carried the recency filter. If you skipped this step, the report is invalid — go back.
- [ ] **Source publication dates are recorded.** Every source in the Sources section has a publication date (or explicit "unknown"). Not just access date.
- [ ] **For Hot topics: ≥70% of "current state" sources are within 10 days of the research date.** Count them. If under threshold, re-dispatch sub-agents with stricter recency filters and explicit date-range search terms. Do not settle for stale material.
- [ ] **No source older than the stated cutoff is used for "current state" claims.** A 2025 article in a Hot-tier AI report is almost certainly describing an obsolete reality. Structural context is fine, present-tense claims are not.

### Silent-exclusion test

- [ ] **No unfamiliar name was dropped without verification.** Before shipping, ask yourself: "Did my sources repeatedly mention something I didn't include because I didn't recognize the name?" If yes, STOP. Run the Tier 1 verification search (see Source Trust Tiers in Step 3). Include it or escalate to the user — never silently omit.

### Rendering checks

- [ ] **PDF renders cleanly** with proper cover page, TOC, and formatting.
- [ ] **PDF file size is reasonable** (>100 KB indicates actual content rendered).

### If any check fails

Do not ask the user. Fix it yourself:
- **Missing dimension coverage** → Weave the missing material into existing chapters or add a new chapter with a subject-specific title. If data is insufficient, run a targeted search.
- **Too short** → Identify the thinnest chapters. Dispatch a sub-agent to research deeper on those topics. Expand with real substance.
- **AI tells found** → Rewrite the offending sentences in the writer persona's voice. Don't generically "clean up" — rewrite *as that writer*.
- **Stale information** → Run a current news search and update the chapters covering recent developments.
- **PDF rendering issue** → Check the markdown formatting and re-run the converter.

After fixing, regenerate the PDF and run through the checklist again.
