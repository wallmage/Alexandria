# Gate errors

Family → class → rule → fix → remove → example. One section per family the code emits, grouped by the module that emits it. Class F never waived; Class A only via `alx issue --deliver`.

Commands: `"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/alx.py" …`.

Legacy and spec spellings map to the emitted family in [Aliases](#aliases).

Remedy rules `alx check` applies to every line it prints: the producing module's own fix/remove wins and is printed once; `alx` adds a generic remedy only when the finding carries none; the same remedy is never printed twice in one line; `Fix: alx check --fix` appears only for the mechanical repairs of spec §6.7 — `ledger/source-ids`, `ledger/person`, `ledger/source-family`, `ledger/freshness`, `binding/excerpt-missing`, `binding/sources-section`, `integrity/date-line` — whichever module wrote the remedy (ruling R10), and a bare `Fix: alx check` is never printed at all; a Class A finding never carries a `Remove:` remedy, and one whose only honest repair is editing the prose prints `Fix: (edit prose; waivable by alx issue --deliver)` (ruling R8); no printed line exceeds 300 characters (the quoted window is truncated with `…`, never the remedy).

## Ledger (`check` b / `validate_ledger`)

### `ledger/quantity` — F
- **rule:** claim quantity uncovered or contradicted by extracts. Date fragments cover themselves; `n:` never covered by date parts. R14: a month-day (or day) fragment covers the claim's full date when the omitted year — and the month, for a day fragment — appears elsewhere in that source's cached text, title or `published`; without a cache the rule is unchanged.
- **fix:** `alx find S<n> TOKEN` then extend quote, or reword claim to dated form.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C8 asserts `n:1918`; S16 offers `d:1918-01` only.

### `ledger/status` — F
- **rule:** status assertion (patched, discontinued, approved, …) not in extracts.
- **fix:** quote a sentence carrying the status via `alx find`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** claim says "all since patched"; extract has figures only.

### `ledger/direction` — F
- **rule:** increased/decreased (and numeric/legal carriers) must appear in extracts. Bare `under|below|settled` without a carrier is not a trigger.
- **fix:** quote the directional sentence or drop the clause.
- **remove:** `alx claim drop C<n> --apply`
- **example:** "increased 12%" vs extract "12% in 2024".

### `ledger/derived` — F/W
- **rule:** `derived_assertions` must be covered by the extracts; hard when the derivation asserts what no source offers, warn when it only excuses a gap.
- **fix:** `alx find S<n> KEYWORD` then extend the quote in claims/<file>.
- **remove:** `alx claim drop C<n> --apply`
- **example:** derived "therefore the fleet doubled"; no extract carries the base.

### `ledger/date-granularity` — W
- **rule:** bare year asserted where extracts offer year-month only (or the reverse).
- **fix:** reword the claim to the granular form via `alx find`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** claim `1918`; extract `1918-01`.

### `ledger/extract-length` — W/F
- **rule:** advice only (ruling R13): the whole extract is < 20 normalized chars (< 10 when it contains CJK). Never raised on an ellipsis-separated piece, and never blocks `claim add`. Length is not a fabrication check; `fidelity/mismatch` decides that. An empty `extract_or_location` is still hard.
- **fix:** extend the quote in claims/<file>; widen with `alx find S<n> KEYWORD`.
- **remove:** none (Class A).
- **example:** `extract_or_location: "short"` (5 chars, threshold 20).

### `ledger/claim-input` — F
- **rule:** claim-input object fails `references/claim-input.schema.json`, misses `claim_id`, names an unfetched source, or repeats an id inside one batch.
- **fix:** set field `<name>` in `claims/<file>.json`, then `alx claim add claims/<file>.json` (the claim re-enters the ledger only through `claim add`, which upserts by `claim_id`).
- **remove:** `alx claim drop C<n> --apply`
- **example:** `kind: analysis` without `reasoning`.

### `ledger/schema` — F
- **rule:** ledger fails `evidence-ledger.schema.json`.
- **fix:** set field `<name>` in `ledger.json` via `alx ledger merge` (brief/people/coverage/synthesis only).
- **remove:** `alx claim drop C<n> --apply` if the invalid object is a claim.
- **example:** missing `schema_version`.

### `ledger/key-claim` — F
- **rule:** key/central claim rests on `unverified`/interested-only sources, or lacks `decision_relevance`/`what_would_change`. `unverified` counts as interested.
- **fix:** `alx source set S<n> --provenance P`
- **remove:** `alx claim drop C<n> --apply`
- **example:** C5 is central; S1 and S2 are both `unverified`.

### `ledger/provenance` — F
- **rule:** provenance/roles/accountability combination is not admissible for the claim's use.
- **fix:** `alx source set S<n> --provenance P --role R`
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** subject-controlled page classified `primary_independent`.

### `ledger/portfolio` — F
- **rule:** the source portfolio is not independent enough for the claim set (all sources interested, or one family only).
- **fix:** `alx source set S<n> --provenance P`, or fetch an independent source.
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** 9 of 9 claims on one publisher.

### `ledger/triangulation` — F
- **rule:** `triangulation.status`/`rationale` contradicts the merged source families.
- **fix:** set field triangulation in claims/<file>, then `alx claim add claims/<file>`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `status: met` with one family.

### `ledger/host-conflict` — F
- **rule:** sources presented as independent share one host; reported in one pass with provenance per id.
- **fix:** `alx source set S<n> --family-justification FILE` (free text via file, D10)
- **remove:** n/a (the justification is the repair)
- **example:** S3 and S7 both on `example.org`.

### `ledger/source-family` — W
- **rule:** `source_family` label is not the registrable domain and no `family_justification` explains the split.
- **fix:** `alx check --fix` (auto-derives from the domain).
- **remove:** n/a
- **example:** family `Example` for `records.example.org`.

### `ledger/source-ids` — F/W
- **rule:** `source_ids` missing (warn; derived from `source_evidence`) or naming a source the evidence does not carry (hard).
- **fix:** `alx check --fix` (derives `source_ids` from `source_evidence`)
- **remove:** `alx claim drop C<n> --apply`
- **example:** C5 has extracts on S1,S2; `source_ids` empty.

### `ledger/https` — F
- **rule:** `source.url` is not https (aliases may be http).
- **fix:** `alx fetch <https form of the url>` (`--refresh` re-fetches the http url and fails again).
- **remove:** n/a
- **example:** `http://records.example.org/a`.

### `ledger/freshness` — F
- **rule:** a `time_sensitive` claim is older than its freshness window, or `verified_at` precedes `as_of`.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `as_of` 2026-09-14, `verified_at` 2026-09-13.

### `ledger/undated-reason` — F
- **rule:** an undated source has no accepted `undated_reason` phrasing.
- **fix:** `alx source set S<n> --undated-reason FILE`
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** S4 has no `published` and no reason.

### `ledger/person` — F/W
- **rule:** person-linked claim without a registered person, or `living_status: unknown`. R15 (W): a claim naming a registered person without the `person_id` is auto-linked by `claim add` / `check --fix` and warns; the harm rules then run on the linked claim and stay hard.
- **fix:** `alx ledger merge people.json` (auto-link warn: `alx check --fix`)
- **remove:** `alx claim drop C<n> --apply`
- **example:** C3 names P1 while P1 status is `unknown`.

### `ledger/harm` — F
- **rule:** living/recently_deceased/unknown person claim without a complete `human_harm_review`; the message lists the missing keys.
- **fix:** `alx ledger merge people.json`, then re-add the claim with `human_harm_review`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** missing `human_harm_review.right_of_reply`.

### `ledger/excluded-supports` — F
- **rule:** a surviving claim's `supports` names a claim in `excluded_claims`.
- **fix:** set field `supports` in `claims/<file>.json`, then `alx claim add claims/<file>.json`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C4 supports C2, and C2 was dropped.

### `ledger/coverage` — W
- **rule:** coverage item linkage inconsistent with the claims (status vs `claim_ids`, gap with claims).
- **fix:** `alx ledger merge coverage.json` (`--fix` repairs no coverage linkage)
- **remove:** n/a (Class A)
- **example:** area `supported` with an empty `claim_ids`.

### `ledger/synthesis` — F
- **rule:** synthesis names a claim that does not exist, or a central judgment with no claim behind it.
- **fix:** `alx ledger merge coverage.json`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `central_judgment_claim_ids: ["C9"]`; C9 was dropped.

### `ledger/reference` — F
- **rule:** cross-reference between claims, people or sources does not resolve.
- **fix:** set field supports in claims/<file>, then `alx claim add claims/<file>`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `responds_to_claim_ids: ["C12"]`; no C12.

## Integrity (`check` a / `validate_report`)

### `integrity/control-chars` — F
- **rule:** C0 except `\t\n\r` in the report or the snapshot.
- **fix:** n/a (the restore is the repair; `alx` prints one remedy, never the same one twice)
- **remove:** `alx snapshot --restore`
- **example:** U+0001 in paragraph 12 (limit 0).

### `integrity/replacement-char` — F
- **rule:** U+FFFD in the report (mis-decoded paste).
- **fix:** n/a (printed as the remove remedy only)
- **remove:** `alx snapshot --restore`
- **example:** `���` inside a quotation.

### `integrity/quotation-lost` / `fidelity/quotation-lost` — F
- **rule:** a snapshot quoted span (「」『』“”‘’ or straight "…" ≥ 4 chars) is missing verbatim from the report. `validate_report` emits the `integrity/` spelling, `rewild_gate` the `fidelity/` one. A span that lived inside a paragraph `claim drop --apply` deleted is an allowed loss and never reported.
- **fix:** n/a — the restore is the whole repair, printed once as the remove
- **remove:** `alx snapshot --restore` (restores the snapshot minus the mechanically dropped paragraphs)
- **example:** 「原始日記」 dropped during humanize.

### `integrity/encoding` — F
- **rule:** `report.md` is not decodable UTF-8.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** GBK bytes written into report.md.

### `integrity/structure` — A
- **rule:** missing H1, standfirst blockquote, or Sources H2 last.
- **fix:** (edit prose; waivable by alx issue --deliver) — `--fix` writes no headings.
- **remove:** n/a
- **example:** two H1 headings.

### `integrity/date-line` — A
- **rule:** strict-locale date line absent or ≠ `ledger.report_date`.
- **fix:** `alx check --fix` when only the whitespace of the line under the H1 is wrong; otherwise (placement or format) (edit prose; waivable by alx issue --deliver).
- **remove:** n/a
- **example:** `> 2026年9月14日` vs ledger `2026-09-15`.

### `integrity/length` — F/A
- **rule:** report length outside the band (en 7,500–15,000 words; zh 5,000–10,000 report-body characters), counted on the visible prose body — front matter, headings, the Sources section and the machine-written Verification note excluded (`report_blocks.report_length`). `alx check` prints `length <count> <unit>; floor <n>, ceiling <m>`. Below the floor arrives as a warning (Class A); above the ceiling is hard.
- **fix:** extend the report body in report.md (below the floor; Class A).
- **remove:** delete paragraph `<n>` of report.md (above the ceiling)
- **example:** 16,400 words; ceiling 15,000.

## Binding (`check` c / `validate_report`, `alx`)

### `binding/link-not-in-ledger` — F
- **rule:** a body link URL, normalized, is in no source's `url`/`aliases`.
- **fix:** `alx fetch <url>`
- **remove:** delete paragraph `<n>` of report.md
- **example:** `https://blog.example.net/x` cited, never fetched.

### `binding/claim-paragraph` — F
- **rule:** an `include_in_report` claim maps to zero or to more than one paragraph.
- **fix:** `alx claim bind C<n> --paragraph N` — `N` is the body-paragraph number of `validate_report.split_body_paragraphs`, the one numbering `check`, `claim bind`, `claim drop` and the claim→paragraph table all print.
- **remove:** `alx claim drop C<n> --apply`
- **example:** ambiguous: candidates 12, 19.

### `binding/excerpt-missing` — F
- **rule:** an `include_in_report` claim has an empty `report_excerpts`.
- **fix:** `alx claim bind C<n> --paragraph N` — `--fix` writes the excerpt of a bound claim in the same run, so a surviving finding is unbound. With no candidate paragraph the claim is cited nowhere: add the source link to paragraph `<n>` of report.md (ruling R9).
- **remove:** `alx claim drop C<n> --apply`
- **example:** C6 bound to paragraph 8, `report_excerpts: []`.

### `binding/leftover-prose` — F
- **rule:** an excluded claim's mapped paragraph text is still in `report.md`.
- **fix:** delete paragraph `<n>` of report.md
- **remove:** `alx claim drop C<n> --apply`
- **example:** C8 dropped; paragraph 19 still present.

### `binding/sources-section` — A
- **rule:** Sources H2 is not last, or ≠ the cited-source list.
- **fix:** `alx check --fix` (regenerates from the ledger).
- **remove:** n/a
- **example:** S5 cited, absent from Sources.

## Cache and fidelity (`check` b,d / `source_fidelity`, `alx`)

### `fidelity/mismatch` — F
- **rule:** an extract segment is absent from the cache (offline) or from the live text (online). Full coverage; no first-window rule.
- **fix:** `alx find S<n> KEYWORD`, then extend the quote in claims/<file>.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C2 extract "4,000 documents" not in S1.txt.

### `fidelity/context-changed` — F
- **rule:** the probe is present but a recorded probe-context hash changed since research; correction markers (更正/撤回/correction/retract/erratum) are flagged when present. Never self-authorizing.
- **fix:** `alx fetch --id S<n> --refresh, then alx claim add claims/<file>` — the refresh alone keeps the recorded probe contexts; `claim add` re-confirms the extract and re-binds them.
- **remove:** `alx claim drop C<n> --apply`
- **example:** S7 paragraph now begins "Correction:".

### `fidelity/cache-missing` — F
- **rule:** an extract probe has no `sources/S<n>.txt`.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** n/a
- **example:** S4 cache file absent.

### `fidelity/cache-detached` — F
- **rule:** `sources/S<n>.meta.json` url ≠ ledger url, or `text_sha256` ≠ sha of `sources/S<n>.txt`.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** n/a
- **example:** S1.txt hand-edited after the fetch.

### `fidelity/unreachable` — F offline / A online
- **rule:** the source cannot be fetched (dns, timeout, tls, http-<status>, plaintext-http, oversize, redirect-loop, cross-domain-redirect). Offline, with a cache present, it is fabrication; live, beyond quorum, it is availability.
- **fix:** `alx issue --deliver`
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** S9 UNREACHABLE (timeout) at issue time.

### `fidelity/undecodable` — F offline / A online
- **rule:** the fetched bytes do not decode (U+FFFD ratio > 1% after the charset ladder).
- **fix:** `alx issue --deliver`
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** S6 UNDECODABLE (gb2312).

## Rewild (`check` e / `rewild_gate`)

### `fidelity/semantic` — F
- **rule:** negation, direction, causal or association drift between snapshot and report, measured on citation-stripped, quote-masked prose with monotonic clause alignment.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** snapshot "did not exceed"; report "exceeded".

### `fidelity/rewild` — F
- **rule:** the naturalness checker's "Fidelity (rewrite vs original)" section — fabricated figures, attribution drift.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** figure 4,000 became 40,000 during humanize.

### `rewild/region` — F
- **rule:** the checker's "Region" section and every other hard checker error: wrong-region vocabulary or script.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** 簡體 vocabulary in a zh-HK report.

### `rewild/ai-vocabulary` — A
- **rule:** the checker's "AI vocabulary" section, length-scaled, counted on quote-masked prose.
- **fix:** (edit prose; waivable by alx issue --deliver)
- **remove:** n/a — no Class A finding carries a remove remedy (ruling R8).
- **example:** "delve" ×7 at 8,000 words.

### `rewild/style` — A (warn)
- **rule:** every other checker section — Rhythm, Openers, Serial enumeration, Paragraphs, Paragraph closers, Punctuation.
- **fix:** (edit prose; waivable by alx issue --deliver)
- **remove:** n/a (ruling R8).
- **example:** 9 consecutive sentences open with the subject.

### `rewild/length` — A
- **rule:** length floor or ceiling, language and script checks (en 7,500–15,000 words; zh 5,000–10,000 report-body characters), the same count as `integrity/length`, counted on the visible prose body — front matter, headings, the Sources section and the machine-written Verification note excluded (`report_blocks.report_length`).
- **fix:** (edit prose; waivable by alx issue --deliver)
- **remove:** n/a (ruling R8).
- **example:** report has 68 words; minimum is 7,500.

### `rewild/checker` — A
- **rule:** bookkeeping: unreadable files, unsupported language, checker subprocess failure or timeout (120 s under `alx`, 300 s standalone).
- **fix:** `alx issue --deliver`
- **remove:** n/a (Class A)
- **example:** Rewild checker timed out after 120 seconds.

### `rewild/humanization` — A
- **rule:** `issue` had to create the snapshot itself, so the report was never humanized (`humanization: none`).
- **fix:** `alx issue --deliver`
- **remove:** `alx snapshot --restore`
- **example:** issue run straight after drafting.

## Reviews (`check` f / `content_gate`, `rewild_gate`, `alx`)

### `review/rewild` — A
- **rule:** the blind-review note is missing, incomplete, or no longer matches the reviewed report/source/language/profile.
- **fix:** `alx review start rewild --iter`
- **remove:** `alx review start rewild`
- **example:** note does not match the reviewed report: report_sha256.

### `review/content-missing` — F
- **rule:** no finished content review.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** `reviews/content.json` absent.

### `review/content-stale` — F
- **rule:** report or ledger changed beyond the §6.8 mechanical-delta allowlist since the content review.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** 2 paragraphs rewritten after `review finish content`.

### `content/score` — F
- **rule:** a content-review score is missing or below 4.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** `scores.evidence.score = 3`.

### `content/check` — F
- **rule:** the content note fails `content-review.schema.json` or its completeness rules; the same family also carries the two claim-binding errors below.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** `status` is not `completed`.
- **binding exceptions (ruling R9):** "cannot be located in the report" → `alx check --fix` (it re-derives `report_excerpts` from the bound paragraph), or `alx claim bind C<n> --paragraph N` when the claim is unbound; "has no nearby citation to its ledger source" → add the source link to paragraph `<n>` of report.md. A re-review fixes neither, and a link insertion with unchanged visible text is a mechanical delta (§6.8).

### `content/critical-finding` — F
- **rule:** a critical review finding is not dispositioned `resolved`.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** findings[2] disposition `open`.

### `content/disclosure` — F
- **rule:** a required disclosure excerpt cannot be located in `report.md`.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** disclosure quotes a sentence that was edited away.

### `content/claim-support` — F
- **rule:** a retained claim→paragraph mapping has no support disposition in the note.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** C4 bound to paragraph 8, no `claim_support` entry.

### `content/claim-binding` — W
- **rule:** the note's claim binding disagrees with the ledger's mapping.
- **fix:** `alx claim bind C<n> --paragraph N`
- **remove:** `alx review restore content`
- **example:** note says paragraph 7, ledger says 8.

### `content/language` — F
- **rule:** report language does not match the ledger's `report_language`.
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** zh-CN ledger, English body.

## Tooling (`issue` / `render`)

### `tooling/receipt` — A
- **rule:** a receipt could not be issued or verified — rewild, content, source-fidelity, or `validate_report --fast --final-once`.
- **fix:** `alx issue --deliver`
- **remove:** `alx fetch --id S<n> --refresh`
- **example:** source-fidelity receipt not issued: network unavailable.

### `tooling/render` — A
- **rule:** md_to_pdf or the rasterizer failed or timed out (90 s each); the backend chain pdfkit → pdfium → poppler is already exhausted.
- **fix:** `alx issue --deliver`
- **remove:** n/a
- **example:** poppler timeout on page 41.

## Aliases

Spec and legacy spellings, and the family the code actually emits. Use the emitted name.

| spec / legacy | emitted |
|---|---|
| `quotation-lost`, `Fidelity/quotations` | `integrity/quotation-lost` (report) / `fidelity/quotation-lost` (rewild) |
| `cache-detached` | `fidelity/cache-detached` |
| `cache-missing` | `fidelity/cache-missing` |
| `leftover-prose` | `binding/leftover-prose` |
| `binding/ambiguous`, `binding/missing` | `binding/claim-paragraph`, `binding/excerpt-missing` |
| `ledger/unverified-key-claim` | `ledger/key-claim`, `ledger/provenance` |
| `ledger/disputed` | `ledger/synthesis` |
| `ledger/family-label` | `ledger/source-family` |
| `ledger/derived-assertions` | `ledger/derived` |
| `ledger/granularity` | `ledger/date-granularity` |
| `rewild/semantic-fidelity` | `fidelity/semantic` |
| `rewild/regional` | `rewild/region` |
| `rewild/review-stale` | `review/rewild` |
| `rewild/humanization-none` | `rewild/humanization` |
| `length-below-floor` | `rewild/length`, `integrity/length` |
| `sources-section` | `binding/sources-section` |
| `tooling/renderer`, `tooling/rasterizer` | `tooling/render` |
