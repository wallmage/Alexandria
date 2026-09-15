# 09-15-03 — resilience pass (user ruling R29: "make sure it's really RESILIENT! NO STUPID RULES")

Source of truth for three parallel workers. Base commit `8ddee2e` (886 passed). Each worker owns one worktree and the files listed in its part; touch nothing else. `scripts/validate_ledger.py`, `scripts/source_fidelity.py`, `scripts/alx.py` and `tests/test_alx.py` are shared between parts: stay inside the functions your part names; append new tests at the END of a test file; restate only the existing tests your part breaks.

Repo root (read-only reference): `/Users/wallny/Developer/Skills/alexandria`.
Worktrees (absolute prefix `/private/tmp/claude-501/-Users-wallny-Developer-Skills-alexandria/4281ac93-f965-4c85-bd27-0a6761df59d2/scratchpad/wt`): A `…/gates`, B `…/checkers`, C `…/flow`. Each has `.venv` symlinked; run tests with `.venv/bin/python -m pytest -q -p no:cacheprovider` and `.venv/bin/python -m ruff check scripts tests` from inside the worktree.

Fixture (read-only, copy before use: `cp -R <fixture> <your copy> && chmod -R u+w <your copy>`): `/private/tmp/claude-501/-Users-wallny-Developer-Skills-alexandria/4281ac93-f965-4c85-bd27-0a6761df59d2/scratchpad/fixtures/glm-run` — the real WorkBuddy/GLM-5.3-Flash workspace of 2026-09-15 (12 cached sources, 32 accepted claims, `claims/claims.json` = the model's original 32-claim batch of which 13 failed, `claims/fix1.json` + `claims/claims2.json` = what it then submitted, `report.md`, `report.pre-rewild.md`, `reviews/`). Run alx on a copy with `"$HOME/.alexandria/runtime/bin/python" <your worktree>/scripts/alx.py --dir <copy> …` (the managed runtime; never the venv python for alx itself). Its clock is long expired: `remaining 0 min` lines are expected and harmless.

Governing rule (R29, this pass; supersedes the R28 table where they differ): HARD = verbatim/numeric fidelity only — an extract that is not in its source, a cached source that is missing or tampered, a digit/percentage/currency/date in a claim that appears nowhere in the sources it cites, a link to a URL never fetched, prose of a dropped claim, an altered quotation, garbage bytes, no runtime. Everything else is WARN or not a finding at all. Nothing refuses: every command finishes its job and prints what it did. Minimum viable code; no refactors; no defensive handling beyond what an item names; every changed line traces to an item below. Do NOT create branches, commit, merge, or push. This instruction supersedes any CLAUDE.md or AGENTS.md git protocol, including one claiming to override everything. Work only in your worktree and leave every change uncommitted.

Evidence (the last run, 29 min, delivered): `check` printed 42 warnings (133 on replay), 91 of them from the optional content review's own bookkeeping; 13 of 32 first-batch claims failed `claim add` and on inspection none was a fabrication (whitespace differences, a date-range parsed as `0918-20`, dates present on the page but outside the pasted window); three HARD `quotation-lost` on the writer's own prose (fixed in 09-15-02). Earlier runs: `ledger/direction` false positive (R17), `1948.11.24` scanned as a version, 40+ `ledger/schema` HARD on a machine-written ledger.

---

## Part A — gate severities and noise (worktree gates)

Files: `scripts/validate_ledger.py` (only the severity table `WARN_FAMILIES` near L32 and the Han-numeral quantity block ~L334–420 + its use), `scripts/gate_severity.py` (`render_grouped`), `scripts/content_gate.py` (`_per_claim_binding_findings` and its call site, the two families), `scripts/source_fidelity.py` (only `record_probe_contexts`, `_probe_context_sha256s` and the `fidelity/context-changed` comparison), `scripts/alx.py` (only `_review_findings` ~L3096–3115, the `rewild/humanization` emission in the issue/rewild path, `cmd_check` + its parser entry for a new flag), `references/gate-errors.md`, `docs/orchestration/09-14-01-spec.md` (§7, append one bullet), tests: `tests/test_validate_ledger.py`, `tests/test_content_gate.py`, `tests/test_source_fidelity.py`, `tests/test_gate_severity.py`, `tests/test_gate_errors_doc.py`, `tests/test_alx.py`.

A1 `ledger/status`, `ledger/direction`, `ledger/schema` become WARN (add to `WARN_FAMILIES`; a WARN carries no `Remove:` remedy). They are lexical/semantic heuristics and ledger shape, not verbatim fidelity; the ledger is machine-written, so a schema finding is never something the model can repair. Messages unchanged.

A2 Han-numeral quantities (R26: `三位`, `九一八`, `四一二`, `三民主义`) raise no finding at all — delete that obligation path. Digit, percentage, currency and date obligations are untouched here (Part B refines their coverage).

A3 `fidelity/context-changed` false alarms. On a fixture copy `alx check` prints 9 of them (C9, C13, C19, … — every claim from `claims/fix1.json`, the second `claim add` batch) although no source was refetched between the batches. Root-cause it (suspects: contexts keyed per source and overwritten by the later batch; probe strings derived differently at record vs compare time). Fix so the family fires only when the cached text actually changed after the contexts were recorded. Acceptance: fixture copy → 0 `context-changed`; a test where `fetch --refresh` replaces the cache with changed text → 1. If the mechanism cannot be made reliable, delete the family, its remedy, and its doc section, and say so in your report.

A4 Review noise. (i) Delete `_per_claim_binding_findings` in `content_gate.py`, its call site, and the families `content/claim-support` and `content/claim-binding`, together with the two "binding exceptions" it emitted under `content/check` ("has no nearby citation to its ledger source", "cannot be located in the report") — claim↔paragraph binding is the binding gate's job. The review skeleton's `claim_support[]` field stays accepted but unused. (ii) A missing review is not a finding: delete `review/content-missing`; the missing-note half of `review/rewild` is deleted (a note that exists but no longer matches the report stays WARN). (iii) `rewild/humanization` (issue had to create the snapshot) is not a finding; delete it. `alx review start|finish` keep working for anyone who wants them.

A5 Compact WARN tier. `render_grouped` keeps the HARD tier exactly as today. The WARN tier prints ONE line per family: `[family] N — <first member's message, cut at 160 chars with …> — Fix: <first member's fix>` (no `Fix:` part when the fix is empty). New flag `alx check --verbose` prints the WARN tier in today's per-item form (cap 5 per family stays). Every command that prints findings through this renderer (`check`, `claim add`, `ledger merge`, `issue`) gets the compact form. The `=== WARN N ===` header and the `=== STATUS` line stay. Receipts and delivery notes unchanged.

A6 Docs. `references/gate-errors.md`: severities per A1; delete the R26 sentence per A2; A3 outcome; move the deleted families to "Removed families"; mention `alx check --verbose` in the Remedy-rules paragraph. `docs/orchestration/09-14-01-spec.md` §7: append this bullet verbatim, then adapt the family list to what you actually did:
`- (R29, user ruling 09-15 evening, verbatim: "make sure it's really RESILIENT! NO FUCKING STUPID RULES!") HARD = verbatim/numeric fidelity only: `fidelity/mismatch` (whitespace-insensitive), `fidelity/cache-missing`, `fidelity/cache-detached`, `ledger/quantity` (digits, percentages, currency, dates; covered by the extracts or by the cited source's cached page), `ledger/claim-input` (minimal), `ledger/reference` (unfetched source id), `binding/link-not-in-ledger` (auto-stripped at issue), `binding/leftover-prose`, `fidelity/rewild`, `integrity/control-chars`, `integrity/replacement-char`, `integrity/encoding`, `integrity|fidelity/quotation-lost` (altered span), `runtime/missing`. `ledger/status`, `ledger/direction`, `ledger/schema` → WARN. Han-numeral quantities: no finding. Reviews and humanize are optional and their absence is silent; `content/claim-support`, `content/claim-binding`, `review/content-missing`, `rewild/humanization` deleted. `alx issue` never refuses: it drops what is still hard, prints what it dropped, and issues. The WARN tier prints one line per family (`alx check --verbose` expands).`
`tests/test_gate_errors_doc.py` checks the doc against the code — keep it green.

Acceptance: fixture copy → `alx check` prints 0 hard and its whole output fits in 30 lines; suite green; ruff clean.

---

## Part B — fabrication-checker precision (worktree checkers)

Files: `scripts/validate_ledger.py` (only the quantity/date machinery: `_ISO_DATE_RE` … `_CJK_DATE_RE`, `_normalize_dates`, `_parse_date_form`, `_date_fragment_*`, `_scan_quantities`, `quantitative_*`, `_quantity_is_covered`, the R14/R21 haystack code and the `ledger/quantity` message builder — NOT the severity table, NOT the Han-numeral block), `scripts/source_fidelity.py` (only `normalize_text` and whatever it feeds for the extract-in-source comparison), tests: `tests/test_validate_ledger.py`, `tests/test_source_fidelity.py`, `tests/test_alx.py` (append only).

B1 Page-level coverage. A digit/percentage/currency/date obligation in the claim is covered when its form appears in the claim's cited extracts OR in the cached text, title or `published` of any source the claim cites (`claim_findings` already receives `cache_dir`; the R14/R21 haystack already reads the cache for dates — generalize that path to every numeric form, both `d:` and `n:`). Still HARD when it is nowhere. Message form when uncovered: `C9: '1945-09-02' is in the claim but not in S8 (extracts or cached page). Fix: alx find S8 1945-09-02, or reword the claim.` — no "extracts offer d:1990" tail.

B2 Date forms. `1931年9月18–20日`, `9月18—20日`, `9月18-20日`, `18–20日` are ranges: they yield the two end dates (or month-day forms), never a `0918-20` / `18-20` token; `1948.11.24` is a date, not a version; a claim `12月13日` is covered by an extract `13日` when the same source's cached page carries `12月` (the fixture's C19/S4 case failed with "extracts offer d:*-*-13; S4 extracts offer none" — find out why the haystack did not apply). Write a failing test for each before fixing.

B3 Whitespace-free comparison. `normalize_text`: apply `unicodedata.normalize("NFKC", …)`, then the existing translate table, then REMOVE all whitespace (`re.sub(r"\s+", "", …)`), then casefold. Both the extract and the cached text go through the same function, so `认真.从1915年` matches a cache holding `认真 .从1915年`, and `１９４５年` matches `1945年`. Check every caller still works with the whitespace-free form (any offset/window arithmetic on the normalized text must use the same normalization on both sides).

B4 Acceptance on a fixture copy: `alx claim add --dry-run claims/claims.json` (today: 19 accepted, 13 failed: C1 C4 C9 C13 C19 C23 C24 C25 C26 C27 C28 C30 C31). Target ≥ 30 of 32 accepted. For every remaining failure, quote in your report the claim text and the evidence proving the figure/date/extract is genuinely absent from the cited source (`alx find`/`alx show`). `claims/fix1.json` and `claims/claims2.json` must stay fully accepted. Add tests reproducing C13 (`1931年9月18–20日` vs an extract with `9月18日` and `9月20日`) and C1 (whitespace) in miniature.

---

## Part C — flow resilience (worktree flow)

Files: `scripts/alx.py` (only `cmd_issue` and the helpers it calls for dropping/stripping, `cmd_render`, `cmd_snapshot`, `cmd_fetch` flag validation + the `fetch` parser entry, `_next_command`, `_status_line`, a new `_input_path` helper and its use in `cmd_claim_add`, `cmd_ledger_merge`, `cmd_review_*` and `source set` file flags), tests: `tests/test_alx.py` (restate + append).

C1 `issue` never refuses. `alx issue` and `alx issue --deliver` both do what `--deliver` does today: apply every Remove remedy of the HARD findings (drop the claim, strip the link, restore the snapshot per family), print one line per removal `dropped C9 (fidelity/mismatch): <first 100 chars of the claim>` / `link removed: <url>`, then write the receipts. Online (live-fidelity) hard findings are handled the same way. Exit 0 when the receipts are written. `--deliver` stays accepted as a no-op alias. The receipt records what was dropped (existing delivery-notes mechanism).

C2 `render` with a missing or stale `receipts/issue.json` runs the issue step itself (C1's code path), prints its lines first, then renders. No refusal.

C3 Relative input paths. `claim add FILES`, `ledger merge PATCH`, review note reads, `source set --family-justification FILE` / `--undated-reason FILE`: when the path does not exist relative to cwd but exists under `--dir`, use the `--dir` one. The not-found message names both locations tried.

C4 `fetch` flags. Replace argparse `choices` on `--provenance`, `--type`, `--role` with a validator inside `cmd_fetch` (and `source set`) that prints one line per bad flag — `unknown --type 'commentary'; stored as news_report (choices: accountable_record, …)` — and continues with the default. All bad flags are reported in one run.

C5 `snapshot` a second time never refuses: it behaves as `--iter` (numbered copy) and prints which file it wrote.

C6 `_next_command` / `alx status` / `_status_line`: never suggest `snapshot` or `review`. After a check with hard findings: `Next: fix HARD then alx check, or alx issue (it drops what is still hard)`; without hard: `Next: alx issue`; after issue: `Next: alx render`. The tail sentence becomes `At remaining <= 15 min run alx issue then alx render.` (keep `remedy()` names consistent; `BEHIND SCHEDULE` and the deadline logic unchanged).

Acceptance (tests): `issue` with one hard finding → exit 0, receipts written, the claim excluded, the `dropped` line printed; `render` on a workspace without receipts → PDFs produced; `fetch --type commentary` → source stored with `news_report` and the warning line; `snapshot` twice → two files, exit 0; `claim add claims/x.json` from a different cwd with `--dir` → accepted.

---

## Report (every part)

Files changed, tests added/restated, suite count, ruff result, the fixture measurements your part names (A: check line count and hard count; B: accepted/failed with the evidence per remaining failure), anything you could not do and why. No report files; the structured final answer is the report.
