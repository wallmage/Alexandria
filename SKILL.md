---
name: alexandria
description: Use when a user asks for deep research, a deep dive, investigation, full picture, sourced report, or long-form analysis of a person, organization, product, event, concept, market, industry, or phenomenon, especially when the result should be a polished PDF. Do not use for quick summaries, simple definitions, casual Q&A, or non-research writing.
---

# Alexandria

Produce a source-backed research report that is useful to a decision-maker and pleasant to read. The normal deliverables are one Markdown source file and one visually checked PDF.

Resolve `SKILL_ROOT` to the absolute directory containing this `SKILL.md` before running bundled scripts. Never assume the current working directory is the skill directory, and never install dependencies into the user's project.

## Non-negotiable standard

An Alexandria report must:

1. Answer the user's real question, not merely describe the topic.
2. Separate verified facts, reported claims, and analysis.
3. Preserve a traceable path from consequential claims to sources.
4. Prefer evidence quality and coverage over source quotas; meet the hard length range through depth, not filler.
5. State uncertainty, conflicts, and evidence gaps plainly.
6. Read like a thoughtful human editor wrote it.
7. Survive structural, PDF, and visual checks before delivery.

Never invent a fact, quotation, source, date, URL, or subject. Verify unfamiliar names and spellings before building the report around them.

## 1. Frame the assignment

Infer what you safely can from the request and conversation. Ask one concise question only when a missing choice would materially change the result. Otherwise, proceed with reasonable assumptions and state the important ones in the report.

Determine:

- subject and research question;
- intended reader and decision;
- time horizon and geographic scope;
- explicit output language;
- useful depth;
- whether the topic needs current web research.

Language precedence is: explicit requested language, established conversation preference, then the prompt language. Preserve official names, quotations, code, and bibliographic titles when translating them would reduce accuracy.

Set `REPORT_LANG` to `en`, `zh-CN`, or `zh-HK` from that decision and reuse it for validation and rendering.

Choose an archetype:

- person → `references/person.md`
- organization, company, project, institution → `references/organization.md`
- artifact, product, work, technology → `references/artifact.md`
- event, controversy, movement, conflict → `references/event.md`
- concept, theory, method, phenomenon → `references/concept.md`
- market, industry, ecosystem, infrastructure → `references/system.md`
- hybrid → combine only the relevant dimensions from two archetypes

Load only the chosen archetype and the reference files needed for the current stage.

### Depth

Alexandria is deliberately long-form. The delivery bounds are hard:

- **English:** 7,500–15,000 words.
- **Simplified or Traditional Chinese:** 5,000–10,000 non-whitespace characters.
- **Production target:** roughly ten or more finished PDF pages, depending on language, tables, and layout.

Adapt the outline and research depth within those limits. A narrower subject belongs near the lower bound; a complex, well-documented subject belongs near the upper bound. If the first draft is short, deepen the explanation, history, counterevidence, alternatives, or implications through additional research. Do not pad with repetition. If it is long, compress background and repetition without deleting decisive evidence.

## 2. Design the research

Read `references/research-protocol.md`. Create:

1. a coverage map derived from the selected archetype;
2. a query plan for each coverage area;
3. an evidence ledger using `references/evidence-ledger.schema.json`;
4. an explicit list of unresolved questions.

If parallel research is available and appropriate, divide coverage areas among research agents. Give each agent exclusive primary ownership and a disjoint numeric ID range—for example, `S1000–S1999` and `C1000–C1999`—while allowing it to flag cross-cutting evidence. Each returns ledger entries, contradictions, gaps, and a short synthesis—not a detached pile of URLs. The primary agent deduplicates sources and rewrites IDs and relationships before validation.

If parallel research is unavailable, run the same coverage plan sequentially. The quality contract does not depend on a particular tool, model, or agent count.

Use the runtime date in time-sensitive queries. Do not hard-code a calendar year.

## 3. Research and verify

Use available search and browser capabilities. Prefer primary sources where they answer the claim directly, then add independent corroboration or criticism where it matters.

Freshness applies to claims, not to the entire bibliography:

- current state, price, leadership, availability, policy, and performance require the newest authoritative evidence available;
- recent events need contemporaneous reporting and later corrections where available;
- mechanisms, history, and foundational ideas may require older original sources;
- a current article does not replace an older primary document merely because it is newer.

For every consequential claim, add a ledger entry with:

- a stable claim ID;
- a precise claim;
- fact, reported claim, estimate, or analysis;
- source ID and URL;
- publication and access dates;
- faithful extract or source location;
- evidence type and independence;
- confidence and limitations;
- supporting or contradicting claim IDs.

Mark `include_in_report: true` for every ledger claim used in the draft. After drafting, copy a distinctive sentence of at least 40 characters from each claim-bearing paragraph into that claim's `report_excerpts`. This keeps the internal claim map in the ledger—not the delivered Markdown—and lets the validator locate every used claim in the report.

Treat promotional claims, filings, preprints, peer-reviewed studies, independent tests, and reporting as different evidence types. Authority and independence are separate axes. An official source may be best for what an organization says and poor evidence that the claim is true.

Before drafting:

- save the merged ledger for deterministic validation in Step 7;
- deduplicate syndicated or copied stories into one source family;
- reconcile conflicts or present them explicitly;
- verify quotations against the original source;
- verify current facts close to delivery;
- mark unsupported coverage areas as gaps rather than filling them with inference.

No source minimum is mandatory. Use enough independent evidence to support the claims and perspectives the report actually contains.

## 4. Build the argument

Use the archetype as a coverage guide, not a rigid chapter template. Find the report's governing question and answer it early.

A strong structure usually includes:

1. title and report date;
2. executive summary with the central judgment;
3. context and definitions;
4. the mechanism, process, or history that explains the subject;
5. evidence, alternatives, and trade-offs;
6. implications and outlook;
7. conclusion;
8. Sources as the final H2 section.

Outline around reader questions and causal relationships. Combine weak or repetitive sections. Give more space to decisive evidence and less to background the intended reader is likely to know.

## 5. Draft with citations

The primary agent writes and owns the final argument. Use `references/editorial-en.md` for English or `references/editorial-zh.md` for Chinese, plus `references/editorial-modes.md` when a specific register would help.

Requirements:

- Put the conclusion before its supporting detail.
- Use concrete nouns and verbs.
- Explain specialist terms on first use.
- Keep paragraphs focused on one movement of thought.
- Use tables only for real comparisons.
- Use Markdown links for citations and the Sources list: `[source title](URL)`.
- Place citations next to the claims they support.
- Cite direct evidence, not a search result or an article that merely links to it.
- Qualify estimates and contested claims.
- Label original analysis as analysis and show the reasoning.
- Preserve important counterevidence.

Do not expose internal prompts, tool names, agent notes, claim IDs, validation messages, or workflow scaffolding in the final report.

## 6. Evidence-safe edit

Edit for clarity and natural rhythm without changing the evidentiary meaning.

Lock these elements during the edit:

- numbers, dates, names, quotations, and units;
- citations and their claim placement;
- uncertainty and attribution;
- distinctions between fact and analysis;
- the central conclusion unless new evidence requires a change.

When a separate reviewer is available, give it the draft and the editorial checklist. Ask for a patch or a list of changed passages, not an untraceable replacement. The primary agent reviews every material change against the evidence ledger.

If the user explicitly asks to remove AI-like writing, use the dedicated `rewild` or `rewild-zh` skill when available. Alexandria's default edit is evidence-safe copyediting, not unrestricted rewriting.

## 7. Validate the Markdown

Save a cross-platform-safe filename:

1. normalize whitespace;
2. keep only Unicode letters and numbers, ASCII `-`, and `_`;
3. replace every other run—including spaces and shell metacharacters—with `-`;
4. collapse repeated separators, trim them, and limit the basename to 100 characters;
5. fall back to `Alexandria-Report` if nothing remains.

Pass paths as argument-array values where possible. In a shell, quote every path and variable.

Before the first bundled command, create a task-owned environment outside the user's project and install the pinned dependencies. Set `ALEXANDRIA_PYTHON` to `bin/python` on POSIX or `Scripts/python.exe` on Windows. On POSIX:

```bash
ALEXANDRIA_ENV="$(mktemp -d)/venv"
python3 -m venv "$ALEXANDRIA_ENV"
ALEXANDRIA_PYTHON="$ALEXANDRIA_ENV/bin/python"
"$ALEXANDRIA_PYTHON" -m pip install -r "$SKILL_ROOT/requirements.txt"
```

Then run:

```bash
# All languages
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_ledger.py" "$LEDGER_JSON"

# English
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --expected-lang en \
  --min-words 7500 --max-words 15000 --min-sections 3 --min-sources 1

# Simplified or Traditional Chinese
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --expected-lang zh-CN \
  --min-chars 5000 --max-chars 10000 --min-sections 3 --min-sources 1
```

Use `--expected-lang zh-HK` instead for Hong Kong Traditional Chinese. Then manually verify:

- every important factual claim maps to the ledger;
- citations support the exact nearby claim;
- Sources is the final H2 section;
- links open and point to the intended page;
- dates and “as of” statements are clear;
- the conclusion reflects the evidence, including uncertainty;
- the requested language and scope were followed.

## 8. Render and inspect the PDF

Read `references/pdf-production.md`. Use the supplied scripts and pinned dependencies. In brief:

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/md_to_pdf.py" \
  "$REPORT_MD" "$REPORT_PDF" --lang "$REPORT_LANG"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" \
  "$REPORT_MD" --ledger "$LEDGER_JSON" --pdf "$REPORT_PDF" \
  --min-pages 10 --min-text-chars 5000 --min-links 1
```

Reuse the Step 7 environment. The PDF converter refuses to replace an existing output unless `--force` is explicitly supplied; prefer a versioned filename to overwriting a prior report.

Render the PDF to images and inspect every page or a complete contact sheet. Check the cover, contents, headings, tables, code, images, links, page numbers, long URLs, CJK glyphs, overflow, blank pages, and clipped content. Fix and rerender until clean.

Do not use file size as a content or quality signal.

## 9. Deliver

Provide clickable links to the PDF and Markdown source. Summarize the central conclusion in one or two sentences and note any material evidence limitation. Do not paste the whole report into chat unless the user asks.

The task is complete only when:

- the research question is answered;
- the evidence ledger and report agree;
- deterministic checks pass;
- the final PDF was reopened and visually inspected;
- both deliverables exist at the reported paths.
