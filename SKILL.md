---
name: alexandria
description: Use when a user asks for deep research, a deep dive, investigation, full picture, sourced report, or long-form analysis of a person, organization, product, event, concept, market, industry, or phenomenon, especially when the result should be a polished PDF. Do not use for quick summaries, simple definitions, casual Q&A, or non-research writing.
---

# Alexandria

Produce a source-backed research report that is useful to a decision-maker and
pleasant to read. Deliver Markdown and one or two visually checked PDFs.

Resolve `SKILL_ROOT` to the absolute directory containing this `SKILL.md` before running bundled scripts. Never assume the current working directory is the skill directory, and never install dependencies into the user's project.

## Non-negotiable standard

An Alexandria report must:

1. Answer the user's real question, not merely describe the topic.
2. Separate verified facts, reported claims, and analysis.
3. Preserve a traceable path from consequential claims to sources.
4. Prefer evidence quality and coverage over source quotas; meet the hard length range through depth, not filler.
5. State uncertainty, conflicts, and evidence gaps plainly.
6. Test the central judgment against counterevidence, rival explanations, and decision-changing facts.
7. Pass the bundled, language-specific Rewild gate so it reads like a thoughtful human editor wrote it.
8. Pass the report-bound content quality gate before rendering.
9. Survive structural, PDF, and visual checks before delivery.

Never invent facts, quotations, sources, dates, URLs, or subjects. Verify
spellings.

## 1. Frame the assignment

Infer what is safe from context. Read `references/pdf-templates.md`, ask its
four intake questions with complete one-sentence descriptions of all eleven
templates. Begin research in the same turn.
Never wait for an answer.

Apply later answers before rendering. Without answers, use Alexandria as
prepared by, omit client, use today's date, leave confidentiality Off, and
deliver identical-content Executive and topic-adaptive PDFs. An explicit
template choice produces one PDF.

Determine:

- subject and research question;
- intended reader and decision;
- time horizon and geographic scope;
- explicit output language;
- whether the topic needs current web research.
- PDF template and optional cover image;
- prepared-by name, optional client name, and confidentiality state.

Language precedence is: explicit requested language, established conversation preference, then the prompt language. Preserve official names, quotations, code, and bibliographic titles when translating them would reduce accuracy.

Set `REPORT_LANG` to `en`, `zh-CN`, or `zh-HK` from that decision and reuse it for validation and rendering.

Choose an archetype:

- person → `references/person.md` (its Allegations, Harm, and Privacy dimension is mandatory for living subjects)
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

Deepen short drafts with history, counterevidence, alternatives, or
implications; never pad. Compress repetition without deleting decisive evidence.

## 2. Design the research

Read `references/research-protocol.md` and `references/content-quality.md`. Create:

1. a reader contract and governing question;
2. a prioritized coverage map derived from the selected archetype;
3. direct, corroborating, and disconfirming query plans;
4. a version-4 evidence ledger using `references/evidence-ledger.schema.json`;
5. an explicit list of unresolved questions and their effect on the verdict.

For parallel research, assign exclusive coverage and disjoint ID ranges. Each
agent returns ledger entries, contradictions, gaps, and synthesis. Reconcile
IDs before validation; use the same plan sequentially when needed.

Use the runtime date in time-sensitive queries. Do not hard-code a calendar year.

## 3. Research and verify

Use available search and browser capabilities. Prefer primary sources where they answer the claim directly, then add independent corroboration or criticism where it matters.

Apply freshness by claim:

- current state, price, leadership, availability, policy, and performance require the newest authoritative evidence available;
- recent events need contemporaneous reporting and later corrections where available;
- mechanisms, history, and foundational ideas may require older original sources;
- a current article does not replace an older primary document merely because it is newer.

For every consequential claim, add a ledger entry with:

- a stable claim ID;
- a precise claim;
- fact, reported claim, estimate, or analysis;
- source ID and public HTTP(S) URL;
- publication and access dates;
- `undated_reason` when a living source has no publication date;
- one faithful `source_evidence` extract or source location for every direct
  source; never reuse one source's wording as proof for another;
- evidence type, source family, role, and independence;
- importance, confidence, limitations, and decision relevance;
- the reasoning behind analysis and what would change it;
- honest triangulation status;
- reciprocal supporting or contradicting claim IDs and conflict resolution.

A claim may not assert more than its per-source evidence carries. Figures,
dates, versions, scores, directions, and statuses must be traceable to
`source_evidence`, `derived_assertions`, or — for original arithmetic —
`kind: estimate` with `assumptions`. Record
`verified_at`, the date you re-read the source, separately from `as_of`, the date
the fact was true. `supports` points downward only, to the evidence a claim rests
on; cycles are rejected.

For reports centered on people or sensitive personal claims, inventory known
people through `people` and `person_ids`. Classify every person-linked claim with
`person_claim_role` and a substantive `person_claim_assessment`; do not rely
on supplied IDs alone to decide whether a claim is harmful. Harmful claims
about a living, recently
deceased, or unknown-status person require
`human_harm_review`: exact legal stage, accountable corroboration (or a limited
single-source exception), attribution, resolution search, right of reply, and
privacy relevance. A response must reciprocally name the harmful claim in
`responds_to_claim_ids` and use subject-origin evidence; a resolution must use
`resolves_claim_ids`. Carry either in the same report paragraph.

Mark changing claims such as price, availability, leadership, policy, and
current product behavior as `time_sensitive`, and record a non-null `as_of`
date. The validator treats evidence older than 30 days at delivery as stale
unless the claim is no longer time-sensitive.

Negative existence claims such as “no independent benchmark was found” need
an `evidence_of_absence` record with the queries run, the locations where the
evidence should have appeared, and the search date. Do not turn a search limit
into a factual conclusion.

Mark `include_in_report: true` for every ledger claim used in the draft. After drafting, copy a distinctive sentence of at least 40 characters from each claim-bearing paragraph into that claim's `report_excerpts`. This keeps the internal claim map in the ledger—not the delivered Markdown—and lets the validator locate every used claim in the report.

Treat promotional claims, filings, preprints, peer-reviewed studies, independent tests, and reporting as different evidence types. Authority and independence are separate axes. An official source may be best for what an organization says and poor evidence that the claim is true.

For judgments beyond a narrow accountable record, require independent
evidence. If none exists, mark a gap and reduce confidence; never narrow the
source set to make interested evidence sufficient.

Before drafting:

- save the merged version-4 ledger for deterministic validation in Step 7;
- deduplicate syndicated or copied stories into one source family;
- reconcile conflicts or present them explicitly;
- verify quotations against the original source;
- verify current facts close to delivery;
- mark unsupported coverage areas as gaps rather than filling them with inference.
- record and test the strongest rival explanation and material counterevidence
  in `synthesis.adversarial_tests`;
- record the central judgments, implications, usable takeaways or scenarios, limitations, and research stop reason in `synthesis`.

No source minimum is mandatory. Use enough independent evidence to support the claims and perspectives the report actually contains.

## 4. Build the argument

Use the archetype as a coverage guide, not a rigid chapter template. Find the report's governing question and answer it early. Build the argument through observation, interpretation, judgment, implication, then action or takeaway; repair any missing link before drafting.

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

The primary agent writes and owns the final argument. Use `references/editorial-en.md` for English or `references/editorial-zh.md` for Chinese, plus `references/editorial-modes.md` when a specific register would help. Read the visual-component section of `references/pdf-templates.md` before drafting; use metric, insight, and takeaway blocks only for content that deserves that visual weight. Apply the section contract and value-density edit in `references/content-quality.md`. The section contract is satisfied across a section's whole span and must not become a repeated paragraph rhythm; vary section shape across the report.

Requirements:

- Put the conclusion before its supporting detail.
- Use concrete nouns and verbs.
- Explain specialist terms on first use.
- Keep paragraphs focused on one movement of thought.
- Most paragraphs end on their last fact; reserve evaluative closers for section ends.
- Observe the measurable caps in the editorial reference for the report language, and count them on the finished draft.
- Place caveats at the front of the sentence so the paragraph lands on substance.
- Carry named human specifics: practitioners, quotations, dated incidents, or worked failure cases, drawn only from the ledger.
- Use tables only for real comparisons.
- Use Markdown links for citations and the Sources list: `[source title](URL)`.
- Place citations next to the claims they support.
- Cite direct evidence, not a search result or an article that merely links to it.
- Qualify estimates and contested claims.
- Label original analysis as analysis and show the reasoning.
- Preserve important counterevidence.

Do not expose internal prompts, tool names, agent notes, claim IDs, validation messages, or workflow scaffolding in the final report.

## 6. Rewild hard gate

Every report must pass this gate, whether or not the user asked for humanization. Alexandria's mandatory use overrides only the bundled profiles' standalone trigger condition; their preservation, genre, regional, review, fidelity, and checker rules still apply in full.

Choose the bundled profile from `REPORT_LANG`, then read its `SKILL.md`. Open its pattern catalog as directed during diagnosis:

| `REPORT_LANG` | Profile | Checker language |
|---|---|---|
| `en` | `references/rewild/rewild/SKILL.md` | `en` |
| `zh-CN` | `references/rewild/rewild-zh/SKILL.md` | `zh` |
| `zh-HK` | `references/rewild/rewild-hk/SKILL.md` | `hk` |

Read `references/rewild-gate.md` before running this step. It carries the
non-rewrite zones, the blind-review protocol, and the waiver and fidelity-note
rules.

Preserve the draft as `REPORT_PRE_REWILD_MD` before the **first** Rewild pass and
never overwrite it; later iterations write their own per-iteration snapshot. The
original is the only evidence that humanization happened, so a refreshed snapshot
destroys the very diff the receipt certifies.

Run the selected profile over the complete report. Inspect first. Leave clean passages alone, edit isolated tells in place, and re-say dense passages only where the profile permits it. Match the report genre: professional research must remain professional, not become chatty. For `zh-HK`, regional identity and Hong Kong written-Chinese register are hard requirements.

Then run a blind review and record it in `REWILD_REVIEW_NOTE` using `references/rewild-review.schema.json`, bound by hash to the exact report, source, language, and profile.

Run the bundled gate with both report versions. Use the Step 7 Python when
available. It combines the report-bound review with deterministic style,
regional, direction, negation, and causality checks, then binds the report,
source, checker, and review note into a receipt. The review remains
authoritative for semantic equivalence.

```bash
ALEXANDRIA_REWILD_PYTHON="${ALEXANDRIA_PYTHON:-python3}"
"$ALEXANDRIA_REWILD_PYTHON" \
  "$SKILL_ROOT/scripts/rewild_gate.py" "$REPORT_MD" \
  --source "$REPORT_PRE_REWILD_MD" --lang "$REPORT_LANG" \
  --review-note "$REWILD_REVIEW_NOTE" --receipt "$REWILD_RECEIPT"
```

The checker can run under `python3` before Step 7. AI-vocabulary, fidelity,
regional, and Hong Kong register failures cannot be waived; direction reversals
and causal corruption cannot be acknowledged.

Pass only after resolving fidelity and regional failures, disposing of every
blind-review finding, and restoring any lost length with substantive content.

Every gate reports two tiers. Fabrication, unsupported quantities, citations,
source fidelity, person safety, and schema findings block delivery. Style and
formatting findings print as `WARNING:` and do not, though they still deserve an
editorial answer. Waive one only to record in the receipt why it stays.

If Rewild takes the report below the minimum length, deepen the research, analysis, counterevidence, or implications, then repeat this gate. Never restore filler or dilute the edit to hit the count. Do not proceed to Step 7 until the Rewild hard gate passes.

Any change to report text after the receipt is written invalidates it. Return to this step, review the changed report against the preserved original snapshot, and issue a new receipt. Do not refresh `REPORT_PRE_REWILD_MD`.

## 7. Source fidelity and content quality hard gates

Re-read the weighted source sample online. Offline, empty, unreachable, or
partial runs cannot issue a receipt:

```bash
ALEXANDRIA_ENV="$(mktemp -d)/venv"
python3 -m venv "$ALEXANDRIA_ENV"
ALEXANDRIA_PYTHON="$ALEXANDRIA_ENV/bin/python"
"$ALEXANDRIA_PYTHON" -m pip install -r "$SKILL_ROOT/requirements.txt"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/source_fidelity.py" "$LEDGER_JSON" \
  --online --receipt "$SOURCE_FIDELITY_RECEIPT"
```

Rendering and final validation verify the receipt without fetching the same
sources again.

Review the exact post-Rewild report and final ledger using Section 13 of `references/content-quality.md`. Include the three structural counts in Section 13: the closing-sentence census, the section-shape census, and the section-length spread. Record structural uniformity as a `structure` finding. Use an independent reviewer when available; otherwise use a context-isolated fresh-eyes pass. Record the review in `CONTENT_REVIEW_NOTE` using `references/content-review.schema.json`.

Every dimension must score at least 4. Fix critical findings. A major evidence limitation may remain only when the report clearly discloses it and the review records the exact disclosure. Then issue a receipt:

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/content_gate.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --review-note "$CONTENT_REVIEW_NOTE" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --receipt "$CONTENT_RECEIPT"
```

The gate binds the exact report, ledger, review note, language, and bundled schemas. Any later change to one of them invalidates the receipt; repeat the review and gate. Do not render without a current receipt.

## 8. Validate the Markdown

Save a cross-platform-safe filename:

1. normalize whitespace;
2. keep only Unicode letters and numbers, ASCII `-`, and `_`;
3. replace every other run—including spaces and shell metacharacters—with `-`;
4. collapse repeated separators, trim them, and limit the basename to 100 characters;
5. fall back to `Alexandria-Report` if nothing remains.

Pass paths as argument-array values where possible. In a shell, quote every path and variable.

Reuse the task-owned environment from Step 7. On Windows, set `ALEXANDRIA_PYTHON` to the environment's `Scripts/python.exe`. Then run:

```bash
# All languages
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_ledger.py" "$LEDGER_JSON"

# English
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT" --expected-lang en \
  --min-words 7500 --max-words 15000 --min-sections 3 --min-sources 1

# Simplified or Traditional Chinese
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT" --expected-lang zh-CN \
  --min-chars 5000 --max-chars 10000 --min-sections 3 --min-sources 1
```

Use `--expected-lang zh-HK` instead for Hong Kong Traditional Chinese. Then manually verify:

- every important factual claim maps to the ledger;
- every recommendation, winner, preference, or claimed advantage maps to a
  ledger claim or carries a nearby citation;
- every negative existence claim carries its search record;
- citations support the exact nearby claim;
- exactly one Sources heading exists and it is the final H2 section;
- links open and point to the intended page;
- dates and “as of” statements are clear;
- the conclusion reflects the evidence, including uncertainty;
- the requested language and scope were followed.

## 9. Render and inspect the PDF

Read `references/pdf-production.md`. Use the supplied scripts and pinned dependencies. In brief:

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/md_to_pdf.py" \
  "$REPORT_MD" "$REPORT_PDF" --lang "$REPORT_LANG" \
  --template "$REPORT_TEMPLATE" --prepared-by "$PREPARED_BY" \
  --ledger "$LEDGER_JSON" --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" \
  "$REPORT_MD" --ledger "$LEDGER_JSON" \
  --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT" \
  --pdf "$REPORT_PDF" \
  --expected-lang "$REPORT_LANG" \
  --min-pages 10 --min-text-chars 5000 --min-links 1
```

Reuse the Step 7 environment. Existing output requires `--force`; prefer a
versioned filename. PDF validation reopens the file and checks page count,
extractable text, clickable links, metadata, accessibility tags, document
language, page geometry, bookmarks, and mechanical page-quality findings.

Repeat the language-specific hard length flags from Step 7 in the PDF validation command: `--min-words 7500 --max-words 15000` for English, or `--min-chars 5000 --max-chars 10000` for either Chinese variant. The converter independently rejects a missing, stale, wrong-language, or short-report receipt before loading the render engine.

Put custom client/preparer labels in typed H1 metadata before gating. Render only exact gated labels. Add confidentiality only when On; all custom images need approved path/hash visual reviews.

Put a concise standfirst in the first blockquote immediately after the H1,
followed by the report date. The renderer uses that standfirst on the cover and
removes the metadata blockquote from the body.

Without a template choice, render Executive and the result of
`select_adaptive_companion()` using identical Markdown and receipts. Do not
redraft for the second layout; skip it only when rendering cannot complete.

Render the PDF to images and inspect every page or a complete contact sheet. Check the cover, contents, headings, tables, code, images, links, page numbers, long URLs, CJK glyphs, overflow, blank pages, and clipped content. Fix and rerender until clean.

Do not use file size as a content or quality signal.

## 10. Deliver

Provide clickable links to every final PDF and the Markdown source. Summarize the central conclusion in one or two sentences and note any material evidence limitation. Do not paste the whole report into chat unless the user asks.

The task is complete only when:

- the research question is answered;
- the evidence ledger and report agree;
- the current Rewild and content quality receipts pass;
- deterministic checks pass;
- the final PDF was reopened and visually inspected;
- every promised deliverable exists at the reported paths.
