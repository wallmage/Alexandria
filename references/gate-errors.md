# Gate errors

Family → severity → rule → fix → remove → example. One section per family the code emits, grouped by the module that emits it.

Severity is three-valued (ruling R33). **F = HARD-drop**: at `issue` the offending claim, paragraph or edit is removed or restored so it never ships; delivery continues; the removal is printed and noted. **B = HARD-refuse**: `issue` (or `render`) stops with exit 1 and the fix list; nothing is written until fixed; used only for whole-report defects that no drop can cure: no snapshot at `issue`, a report under two thirds of the length floor, an unrestorable encoding, a broken PDF at `render`. An unsupported figure, a Rewild meaning reversal and an unfixed critical review finding are warnings that `issue` repeats as reminders (user ruling, 09-16). HARD-refuse prints `=== BLOCKED (fix, then alx issue again) ===` and blocks `issue` and `render`. **W = WARN**: printed with a fix; never changes the deliverable. WARN is listed in the delivery notes and never blocks `issue`, `render` or `claim add`.

Commands: `"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/alx.py" …`.

Legacy and spec spellings map to the emitted family in [Aliases](#aliases).

Remedy rules `alx check` applies to every line it prints: the producing module's own fix/remove wins and is printed once; `alx` adds a generic remedy only when the finding carries none; the same remedy is never printed twice in one line; `Fix: alx check --fix` appears only for the mechanical repairs of spec §6.7 — `ledger/source-ids`, `ledger/person`, `ledger/source-family`, `ledger/freshness`, `binding/excerpt-missing`, `binding/sources-section`, `integrity/date-line` — whichever module wrote the remedy (ruling R10), and a bare `Fix: alx check` is never printed at all; a WARN finding never carries a `Remove:` remedy, and one whose only honest repair is editing the prose prints `Fix: edit prose (warning; never blocks)` (ruling R8); no printed line exceeds 800 characters (the quoted window is truncated with `…`, never the remedy); the WARN tier prints one line per family (family, count, the first member's message cut at 160 characters, its fix), and `alx check --verbose` expands it to one line per item (5 per family, then `+N more`).

## Ledger (`check` b / `validate_ledger`)

### `ledger/quantity` — W
- **rule:** an Arabic-digit figure, percentage, currency or date in a claim that no extract or cached page of its sources carries. Date fragments cover themselves; `n:` never covered by date parts. R14: a month-day (or day) fragment covers the claim's full date when the omitted year — and the month, for a day fragment — appears elsewhere in that source's cached text, title or `published`; without a cache the rule is unchanged. R14b: the same haystack covers a year-month claim (`1945年8月`) offered as a month-day fragment of that month (`8月2日`). R21: a bare-year claim (`1917年`) is covered by the same 4-digit number in any cited extract (`n:1917`, years 1000-2999 only) — an extract that ends before 年 still states the year. R29: a quantity spelled in Han numeral words (`三`, `三十萬`, with or without a classifier such as 位/次/个/年/月/日) carries no obligation and raises no finding; a digit, percentage, currency or date is covered when its form appears in the claim's extracts or anywhere in the cached page, title or `published` of any source the claim cites; a Han ordinal or year count on the page (第十三年, 十三周年) covers the digits 13. Han numerals stay silent (R26/C26). Display and Fix use the claim's surface text; the search covers every cited source (`source_evidence` ∪ `source_ids`). Message: `C3: '1919年10月2日' is in the claim but not in S13 or S1. Fix: alx find S18 1919年10月2日`.
- **fix:** `alx find S<n> <surface form> — paste that window into extract_or_location and alx claim add, or reword the claim`
- **remove:** n/a (warning; `issue` repeats it under `=== REMINDERS (not fixed yet; warnings, never block) ===` and still issues)
- **example:** C8 asserts `n:1918`; S16 offers `d:1918-01` only.

### `ledger/status` — W
- **rule:** status assertion (patched, discontinued, approved, …) not in extracts. R29: a lexical heuristic, not verbatim fidelity.
- **fix:** quote a sentence carrying the status via `alx find`.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** claim says "all since patched"; extract has figures only.

### `ledger/direction` — W
- **rule:** increased/decreased (and numeric/legal carriers) must appear in extracts. Bare `under|below|settled` without a carrier is not a trigger. R17: the negation window stops at ASCII `.`/`;` as well as `。`/`；`, so a 未/不 in an earlier sentence of a scraped Chinese page no longer denies the evidence; and two CJK carriers bind on a shared four-character phrase, since the 0.75 bigram ratio is unreachable for Chinese clauses. It warns because the lexical detector misfires often (`higher|rose|growth`); it is the first candidate for a better detector.
- **fix:** quote the directional sentence or drop the clause.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** "increased 12%" vs extract "12% in 2024".

### `ledger/derived` — F/W
- **rule:** `derived_assertions` must be covered by the extracts; hard when the derivation asserts what no source offers, warn when it only excuses a gap.
- **fix:** `alx find S<n> KEYWORD` then extend the quote in claims/<file>.
- **remove:** `alx claim drop C<n> --apply`
- **example:** derived "therefore the fleet doubled"; no extract carries the base.

### `ledger/extract-length` — W
- **rule:** advice only (ruling R13): the whole extract is < 20 normalized chars (< 10 when it contains CJK). Never raised on an ellipsis-separated piece, and never blocks `claim add`. Length is not a fabrication check; `fidelity/mismatch` decides that. An empty `extract_or_location` is still hard.
- **fix:** extend the quote in claims/<file>; widen with `alx find S<n> KEYWORD`.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `extract_or_location: "short"` (5 chars, threshold 20).

### `ledger/claim-input` — F
- **rule:** claim-input object fails `references/claim-input.schema.json`, misses `claim_id`, names an unfetched source, or repeats an id inside one batch, or has an empty `claim`, `source_evidence` or `extract_or_location`. Every conditional field — `responds_to_claim_ids`, `resolves_claim_ids`, `decision_relevance`, `what_would_change`, `limitations`, `confidence`, `triangulation` — is optional at schema and never a `ledger/claim-input` finding (R28). Missing `reasoning` on `kind: analysis` or `assumptions` on `kind: estimate` is advised under `ledger/reference` (W), not here.
- **fix:** set field `<name>` in `claims/<file>.json`, then `alx claim add claims/<file>.json` (the claim re-enters the ledger only through `claim add`, which upserts by `claim_id`).
- **remove:** `alx claim drop C<n> --apply`
- **example:** `C17 FAIL [fidelity/mismatch] extract not found verbatim in S15 (searched: …)` then `  S15 extract_or_location: "…"`; or `source_evidence: []`.

### `ledger/schema` — W
- **rule:** jsonschema on `sources`/`claims` items only; every violation prints as `<json path>: <message>`. R29: the ledger is machine-written, so a schema defect is never something the model can repair. `brief`/`people`/`coverage`/`synthesis` are notes and are not validated here.
- **fix:** set field `<name>` in `ledger.json` for `sources`; claims paths: set field `<name>` in `claims/*.json`, then `alx claim add claims/*.json`.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `claims.0.claim: ''`; `sources.0.url` missing.

### `ledger/key-claim` — W
- **rule:** key/central claim rests on `unverified`/interested-only sources, or lacks `decision_relevance`/`what_would_change`. `unverified` counts as interested.
- **fix:** `alx source set S<n> --provenance P`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** C5 is central; S1 and S2 are both `unverified`.

### `ledger/provenance` — W
- **rule:** provenance/roles/accountability combination is not admissible for the claim's use.
- **fix:** `alx source set S<n> --provenance P --role R`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** subject-controlled page classified `primary_independent`.

### `ledger/portfolio` — W
- **rule:** the source portfolio is not independent enough for the claim set (all sources interested, or one family only).
- **fix:** `alx source set S<n> --provenance P`, or fetch an independent source. The message lists the allowed values, one line each:
  - `--provenance`: `primary_independent, primary_interested, secondary_independent, secondary_dependent, unverified`
  - `--type`: `accountable_record, peer_reviewed, preprint, official_documentation, dataset_or_test, reported_interview, news_report, opinion_or_forecast, marketing, anecdote`
  - `--role`: `subject_official, counterparty_official, independent_analysis, empirical_data, affected_stakeholder, expert_interpretation, historical_record`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** 9 of 9 claims on one publisher.
- **`--provenance`:** `primary_independent` `primary_interested` `secondary_independent` `secondary_dependent` `unverified`
- **`--type`:** `accountable_record` `peer_reviewed` `preprint` `official_documentation` `dataset_or_test` `reported_interview` `news_report` `opinion_or_forecast` `marketing` `anecdote`
- **`--role`:** `subject_official` `counterparty_official` `independent_analysis` `empirical_data` `affected_stakeholder` `expert_interpretation` `historical_record` (repeat the flag per role)

### `ledger/triangulation` — W
- **rule:** `triangulation.status`/`rationale` contradicts the merged source families.
- **fix:** set field triangulation in claims/<file>, then `alx claim add claims/<file>`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `status: met` with one family.

### `ledger/host-conflict` — W
- **rule:** sources presented as independent share one host; reported in one pass with provenance per id.
- **fix:** `alx source set S<n> --family-justification FILE` (free text via file, D10)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** S3 and S7 both on `example.org`.

### `ledger/source-family` — W
- **rule:** `source_family` label is not the registrable domain and no `family_justification` explains the split.
- **fix:** `alx check --fix` (auto-derives from the domain).
- **remove:** n/a (warning; never blocks `issue`)
- **example:** family `Example` for `records.example.org`.

### `ledger/source-ids` — W
- **rule:** `source_ids` missing (warn; derived from `source_evidence`) or naming a source the evidence does not carry (hard).
- **fix:** `alx check --fix` (derives `source_ids` from `source_evidence`)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** C5 has extracts on S1,S2; `source_ids` empty.

### `ledger/https` — W
- **rule:** `source.url` is not https (aliases may be http).
- **fix:** `alx source set S<n> --url https://…` (rewrites `sources[].url`, keeps the cache)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `http://records.example.org/a`.

### `ledger/freshness` — W
- **rule:** a `time_sensitive` claim is older than its freshness window, or `verified_at` precedes `as_of`.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `as_of` 2026-09-14, `verified_at` 2026-09-13.

### `ledger/undated-reason` — W
- **rule:** an undated source has no accepted `undated_reason` phrasing.
- **fix:** `alx source set S<n> --undated-reason FILE`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** S4 has no `published` and no reason.

### `ledger/person` — W
- **rule:** a person-linked claim names an unregistered person id. R15: a claim naming a registered person without the `person_id` is auto-linked by `claim add` / `check --fix`.
- **fix:** set the person in a patch file, then `alx ledger merge <patch>` (auto-link warn: `alx check --fix`)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** C3 names P9; no P9 in `people`.

### `ledger/excluded-supports` — W
- **rule:** a surviving claim's `supports` names a claim in `excluded_claims`.
- **fix:** set field `supports` in `claims/<file>.json`, then `alx claim add claims/<file>.json`.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** C4 supports C2, and C2 was dropped.

### `ledger/coverage` — W
- **rule:** coverage item linkage inconsistent with the claims (status vs `claim_ids`, gap with claims); a coverage item that is not an object, an unknown `status`, or `claim_ids` that is not a list (`ledger merge` prints these too; the value is stored as given). Readers accept `claim_ids` or `claims` (list of strings). Merge warns once per item with neither key: `WARN coverage[3] '<area>': no claim_ids — check reads claim_ids: ["C1", …]`.
- **fix:** `set coverage[i].claim_ids to supported claim ids in a patch file, then alx ledger merge <patch>`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** area `supported` with an empty `claim_ids`.

### `ledger/synthesis` — W
- **rule:** synthesis names a claim that does not exist, or a central judgment with no claim behind it; a claim-id list that is not a list, or a synthesis item that is not an object (`ledger merge` prints these too; the value is stored as given).
- **fix:** `put the missing ids in synthesis.central_judgment_claim_ids in a patch file, then alx ledger merge <patch>`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `central_judgment_claim_ids: ["C9"]`; C9 was dropped.

### `ledger/reference` — F/W
- **rule:** cross-reference between claims, people or sources does not resolve. R22: two or more `source_evidence` entries with the same `source_id` are legitimate (two passages from one page) — no finding, and each entry is probed on its own. R23: counterevidence with no adversarial test is a thin synthesis, not a fabrication (W). R24: `as_of` up to 1 day after `verified_at` is timezone drift (UTC fetch vs local date); past that the finding names both dates and the threshold. Analysis/estimate completeness (W): `kind: analysis` with empty/missing `reasoning`, or `kind: estimate` with empty/missing `assumptions` (no non-blank entries). Never blocks `claim add` or `issue`.
- **fix:** set field supports in claims/<file>, then `alx claim add claims/<file>`; untested counterevidence: `set field synthesis.adversarial_tests, then alx ledger merge synthesis`; as_of drift: set field as_of in claims/<file>, then `alx claim add claims/<file>`; analysis missing reasoning: `set field reasoning in claims/*.json`, then `alx claim add claims/*.json`; estimate missing assumptions: `set field assumptions in claims/*.json`, then `alx claim add claims/*.json`
- **remove:** `alx claim drop C<n> --apply` — hard half only (a `source_id` no fetched source carries); every other cross-reference is W and carries no remove
- **example:** `responds_to_claim_ids: ["C12"]`; no C12. `kind: analysis`, `reasoning` absent. `kind: estimate`, `assumptions: []`.

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

### `integrity/encoding` — B
- **rule:** `report.md` is not decodable UTF-8. The report is not valid UTF-8 and no snapshot restores a valid one (already HARD; the restore stays the first remedy, the refuse is the fallback).
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`; HARD-refuse if no snapshot restores a valid UTF-8 report (nothing is written)
- **example:** GBK bytes written into report.md.

### `integrity/structure` — W
- **rule:** missing H1, standfirst blockquote, or Sources H2 last.
- **fix:** edit prose (warning; never blocks) — `--fix` writes no headings.
- **remove:** n/a (warning; never blocks `issue`)
- **example:** two H1 headings.

### `integrity/date-line` — W
- **rule:** strict-locale date line absent or ≠ `ledger.report_date`. Expected form: en `> 15 September 2026` (`DD Month YYYY`), zh-CN and zh-HK `> 2026年9月15日`.
- **fix:** `alx check --fix` when only the whitespace of the line under the H1 is wrong; otherwise (placement or format) edit prose (warning; never blocks).
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `> 2026年9月14日` vs ledger `2026-09-15`.

### `integrity/length` — B/W
- **rule:** report length outside the band (en 7,500–15,000 words; zh 5,000–10,000 report-body characters), counted on the visible prose body — front matter, headings, Sources excluded (`report_blocks.report_length`). `alx check` prints `length <count> <unit>; floor <n>, ceiling <m>`. HARD-refuse when below two thirds of the floor (en < 5,000 words; zh-CN/zh-HK < 3,333 non-whitespace chars). Between two thirds and the floor stays WARN. The ceiling stays WARN; SKILL.md keeps the target.
- **fix:** deepen (research, counterevidence, implications), never pad; or delete a paragraph (above the ceiling).
- **remove:** n/a (HARD-refuse below two thirds of the floor; nothing is written. WARN half never blocks `issue`)
- **example:** 16,400 words; ceiling 15,000.

## Binding (`check` c / `validate_report`, `alx`)

### `binding/link-not-in-ledger` — F
- **rule:** a body link URL, normalized, is in no source's `url`/`aliases`. A same-page variant (paths and queries match after `normalize_url`, path has at least two segments, hosts match after stripping `www.` and the public suffix) is rewritten by `alx check --fix` instead of flagged.
- **fix:** cite the nearest ledger URL instead (alx check --fix rewrites it when only www. or the domain suffix differs); a page you did not fetch must be fetched first
- **remove:** delete paragraph `<n>` of report.md
- **example:** `https://blog.example.net/x` cited, never fetched.

### `binding/claim-paragraph` — W
- **rule:** an `include_in_report` claim maps to zero or to more than one paragraph.
- **fix:** `alx claim bind C<n>:<paragraph>` — the body-paragraph number of `validate_report.split_body_paragraphs`. Out of range is treated as unbound (same candidate search).
- **remove:** n/a (warning; never blocks `issue`)
- **example:** ambiguous: candidates 12, 19.

### `binding/excerpt-missing` — W
- **rule:** an `include_in_report` claim has an empty `report_excerpts`.
- **fix:** `alx claim bind C<n> --paragraph N` — `--fix` writes the excerpt of a bound claim in the same run, so a surviving finding is unbound. With no candidate paragraph the claim is cited nowhere: write `[C<n>]` at the end of the sentence in paragraph `<n>` of report.md, then `alx check --fix` (ruling R9).
- **remove:** n/a (warning; never blocks `issue`)
- **example:** C6 bound to paragraph 8, `report_excerpts: []`.

### `binding/leftover-prose` — F
- **rule:** an excluded claim's mapped paragraph text is still in `report.md`.
- **fix:** delete paragraph `<n>` of report.md
- **remove:** `alx claim drop C<n> --apply`
- **example:** C8 dropped; paragraph 19 still present.

### `binding/sources-section` — W
- **rule:** Sources H2 is not last, or ≠ the cited-source list (the cited list is the body links plus the sources of every bound claim).
- **fix:** `alx check --fix` (regenerates from the ledger; writes the Sources H2 when the report has none).
- **remove:** n/a (warning; never blocks `issue`)
- **example:** S5 cited, absent from Sources.

## Cache and fidelity (`check` b,d / `source_fidelity`, `alx`)

### `fidelity/mismatch` — F
- **rule:** an extract segment is absent from the cache (offline) or from the live text (online). Full coverage; no first-window rule. `claim add` prints three lines: `C<n> FAIL [fidelity/mismatch] extract not found verbatim in S<n> (searched: <first 60 chars>…)`, then `  S<n> extract_or_location: <json string>` (original cache window, ≤240 chars) or `  no similar passage in S<n> — alx find S<n> KEYWORD`.
- **fix:** paste the `extract_or_location` line into a new claims file and `alx claim add` it, or `alx find S<n> KEYWORD`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `C17 FAIL [fidelity/mismatch] extract not found verbatim in S15 (searched: The archive released 9,999 documents.…)` then `  S15 extract_or_location: "The archive released 1,204 documents…"`.

### `fidelity/context-changed` — W
- **rule:** printed only under `alx issue --live`. The probe is present but the probe's own recorded context hash changed since research; correction markers (更正/撤回/correction/retract/erratum) are flagged when present. Never self-authorizing. R29: contexts are recorded per probe, not per claim, so a claim quoting one source twice no longer reports a change on a cache that was never refetched, and a probe with no recorded context is not compared.
- **fix:** `alx fetch --id S<n> --refresh, then alx claim add claims/<file>` — the refresh alone keeps the recorded probe contexts; `claim add` re-confirms the extract and re-binds them.
- **remove:** n/a (warning; never blocks `issue`)
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

### `fidelity/unreachable` — W
- **rule:** printed only under `alx issue --live`. The source cannot be fetched (dns, timeout, tls, http-<status>, plaintext-http, oversize, redirect-loop, cross-domain-redirect). Availability, not fabrication, in both modes (R28): the cached text still decides fidelity.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** S9 UNREACHABLE (timeout) at issue time.

### `fidelity/undecodable` — W
- **rule:** printed only under `alx issue --live`. The fetched bytes do not decode (U+FFFD ratio > 1% after the charset ladder). Availability, not fabrication, in both modes (R28).
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** S6 UNDECODABLE (gb2312).

## Rewild (`check` e / `rewild_gate`)

### `fidelity/semantic` — W
- **rule:** Rewild reversed a direction, negation or causal link between the snapshot and the report. Negation, direction, causal or association drift between snapshot and report, measured on citation-stripped checker prose with monotonic clause alignment. Narrow split-remnant artifacts may be excused heuristically and recorded in the receipt. When more than eight such exemptions accumulate, `alx check` adds one finding in this family: `N heuristic split-remnant exemptions exceed the limit of 8; a report with this much structural churn must be re-checked against the pre-Rewild source and re-drafted, not exempted.`
- **fix:** rewrite the report clause to match the snapshot clause (direction, negation or causal link); or `alx snapshot --restore`
- **remove:** n/a (warning; a reversal is repeated by `issue` as a reminder and never blocks)
- **example:** snapshot "did not exceed"; report "exceeded".

### `fidelity/rewild` — F
- **rule:** the naturalness checker's "Fidelity (rewrite vs original)" section — fabricated figures, attribution drift.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** figure 4,000 became 40,000 during humanize.

### `rewild/region` — W
- **rule:** the checker's "Region" section and every other hard checker error: wrong-region vocabulary or script.
- **fix:** `alx snapshot --restore`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** 簡體 vocabulary in a zh-HK report.

### `rewild/ai-vocabulary` — W
- **rule:** the checker's "AI vocabulary" section; pass when `len(hits) <= 1 and hits[0][1] <= 1`, counted on checker prose.
- **fix:** edit prose (warning; never blocks)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** "delve" ×7 at 8,000 words.

### `rewild/style` — W
- **rule:** every other checker section — Rhythm, Openers, Serial enumeration, Paragraphs, Paragraph closers, Punctuation. Printed only when the rewild note has no style finding. One or more style findings (any disposition) means the reviewer ruled on style.
- **fix:** edit prose (warning; never blocks)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** 9 consecutive sentences open with the subject.

### `rewild/length` — W
- **rule:** length floor or ceiling, language and script checks (en 7,500–15,000 words; zh 5,000–10,000 report-body characters), the same count as `integrity/length`, counted on the visible prose body — front matter, headings, Sources excluded (`report_blocks.report_length`).
- **fix:** edit prose (warning; never blocks)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** report has 68 words; minimum is 7,500.

### `rewild/checker` — W
- **rule:** bookkeeping: unreadable files, unsupported language, checker subprocess failure or timeout (120 s under `alx`, 300 s standalone).
- **fix:** `alx check again — the checker has a 120 s budget`, or the unreadable path the message names
- **remove:** n/a (warning; never blocks `issue`)
- **example:** Rewild checker timed out after 120 seconds.

## Reviews (`check` f / `content_gate`, `rewild_gate`, `alx`)

### `review/rewild` — W
- **rule:** `N paragraph(s) changed since the rewild review — re-read them if the change was substantive; alx review finish rewild re-stamps.` Unknown or missing category is treated as style; unknown or missing disposition as rejected. Findings are kept. A finished note's quality lines print here the same way `review finish` printed them.
- **fix:** `re-read the changed paragraphs, then alx review finish rewild`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** 2 paragraph(s) changed since the rewild review.

### `review/content-missing` — W
- **rule:** no finished content review.
- **fix:** `alx review start content` when no iteration exists, else `alx review finish content`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `reviews/content.json` absent.

### `review/content-stale` — W
- **rule:** `N paragraph(s) changed since the content review — re-read them if the change was substantive; alx review finish content re-stamps.`
- **fix:** `re-read the changed paragraphs, then alx review finish content`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** 2 paragraph(s) changed since the content review.

### `content/score` — W
- **rule:** a content-review score is missing or below 4.
- **fix:** `edit reviews/content.json (raise the score), then alx review finish content`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `scores.evidence.score = 3`.

### `content/check` — W
- **rule:** the content note fails `content-review.schema.json` or its completeness rules; the same family also carries the two claim-binding errors below.
- **fix:** `edit reviews/content.json (set checks true / fill sections), then alx review finish content`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** `status` is not `completed`.
- **binding exceptions (ruling R9):** "cannot be located in the report" → `alx check --fix` (it re-derives `report_excerpts` from the bound paragraph), or `alx claim bind C<n> --paragraph N` when the claim is unbound; "has no nearby citation to its ledger source" → add the source link to paragraph `<n>` of report.md. A re-review fixes neither, and a link insertion with unchanged visible text is a mechanical delta (§6.8).

### `content/critical-finding` — W
- **rule:** the content review lists a critical finding with no fix recorded. A critical review finding is not dispositioned `resolved`.
- **fix:** fix the report and record the disposition in reviews/content.json, then `alx review finish content`
- **remove:** n/a (warning; `issue` repeats it as a reminder — "not fixed yet" — and still issues)
- **example:** findings[2] disposition `open`.

### `content/disclosure` — W
- **rule:** a required disclosure excerpt cannot be located in `report.md`.
- **fix:** `edit reviews/content.json (excerpt ≥40 chars from report.md), then alx review finish content`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** disclosure quotes a sentence that was edited away.

### `content/language` — W
- **rule:** report language does not match the ledger's `report_language`.
- **fix:** `set brief.report_language "<lang>" in a patch file, then alx ledger merge <patch>`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** zh-CN ledger, English body.

## Tooling (`issue` / `render`)

### `tooling/receipt` — W
- **rule:** a receipt could not be issued or verified — rewild, content, source-fidelity, or `validate_report --fast --final-once`. `render` still runs on whatever `issue` produced. Offline delivery note: `source fidelity: offline — extracts were verified verbatim at claim add; alx issue --live re-reads a sample of cited pages`.
- **fix:** `alx issue`
- **remove:** n/a (warning; never blocks `issue`)
- **example:** source-fidelity receipt not issued: network unavailable.

### `tooling/render` — W
- **rule:** md_to_pdf or the rasterizer failed or timed out (90 s each); the backend chain pdfium → pdfkit → poppler is already exhausted. `render` keeps whatever PDFs it produced.
- **fix:** the underlying error line (`{template} not rendered: …`)
- **remove:** n/a (warning; never blocks `issue`)
- **example:** poppler timeout on page 41.

## Issue / render (flow)

### no snapshot at `issue`
- **rule:** the Rewild step never started. A snapshot that exists with an unchanged report stays a WARN.
- **fix:** `alx snapshot`, humanize per the bundled Rewild skill, `alx check`, then `alx issue`
- **remove:** n/a (HARD-refuse; nothing is written)
- **example:** `alx issue` with no snapshot in the workspace.

### report far below the length floor
- **rule:** `integrity/length` below two thirds of the floor (en < 5,000 words; zh-CN/zh-HK < 3,333 non-whitespace chars). Between two thirds and the floor stays WARN.
- **fix:** deepen (research, counterevidence, implications), never pad
- **remove:** n/a (HARD-refuse; nothing is written)
- **example:** English report at 4,200 words.

### broken PDF at `render`
- **rule:** no PDF file produced by any template, or a produced PDF whose extractable text is under 500 characters (image-only or empty file). Below 5,000 but ≥500 stays the WARN line. `render` returns 1 and says which template failed and why.
- **fix:** `alx render` after the template that failed is repaired
- **remove:** n/a (HARD-refuse; nothing is written)
- **example:** image-only PDF with 80 extractable characters.

## Removed families

R29 deletions: `content/claim-support` and `content/claim-binding` — claim↔paragraph binding is the binding gate's job, and the review skeleton's `claim_support[]` field stays accepted but unused. `rewild/humanization` — `issue` creating the snapshot itself is recorded as a delivery disclosure, not a finding. Han-numeral quantities raise no `ledger/quantity` finding.

R35 deletions: review-note metadata bindings (hash/path/profile/schema_version) — `issue` stamps them; content-review prose floors; evidence-ledger schema on `brief`/`people`/`coverage`/`synthesis`; PDF page-count minimum at `alx render`; live re-read by default at `issue`.

R37 deletions: the review-note exam that discarded unknown category or disposition findings; Unresolved style lines after a style finding is recorded.

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
| `rewild/semantic-fidelity` | `fidelity/semantic` |
| `rewild/regional` | `rewild/region` |
| `rewild/review-stale` | `review/rewild` |
| `length-below-floor` | `rewild/length`, `integrity/length` |
| `sources-section` | `binding/sources-section` |
| `tooling/renderer`, `tooling/rasterizer` | `tooling/render` |
