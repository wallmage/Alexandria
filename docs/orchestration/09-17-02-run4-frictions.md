# 0917 run 4 (WorkBuddy 2026-09-17-01-37-01, 蒋介石日记 zh-CN, 11 min, delivered) — W14 contract

Bug report /Users/wallny/WorkBuddy/2026-09-17-01-37-01/bug-report.md triaged by the orchestrator. Verified against code + log 02-session-native-decoded.log. All nine reproduce. BUG-1 "silent" overstated: `check` printed the coverage WARN eight times into delivery-notes; the defect is that no doc lists the enum. Rulings R28–R38 hold: WARN, exit 0, stored as given, no refusal.

## Tasks (W14, one worker)

A BUG-1 docs: SKILL.md:85 and references/research-protocol.md (where coverage rows are described) list the coverage `status` enum literally: `unstarted|in_progress|supported|disputed|gap`, with one example row `{"area":"…","status":"supported","claim_ids":["C1"]}`. gate-errors ledger/coverage names the enum too.

B BUG-2 kind: docs write the wire value `reported_claim` (SKILL.md:114, references/evidence-recording.md:15,24, rewild-gate.md:31 may stay prose). Code: `claim add` normalizes `kind` before validation — lower-case, spaces/hyphens → `_` — and prints one WARN `C8 kind 'reported claim' stored as reported_claim` when it changed. Test.

C BUG-3: `findings[N]` in review notes is 0-based (alx.py ~3443 and ~3477: `enumerate(..., start=1)` → 0-based), matching `coverage[N]` and the JSON array. Fix any test pinning the old numbers.

D BUG-5 docs: rewild-gate.md:68 and the note skeleton hint (alx.py ~4067) say: `resolved` = fixed OR checked and nothing to change; `rejected` = the finding stands and was not applied; a region/fidelity check that found nothing is `resolved` (or not recorded at all).

E BUG-4 fetch http fallback: `_fetch_one` upgrades http→https. When the https attempt is unreachable OR returns an HTTP error class (404 etc.), retry the ORIGINAL http url once. Success → store the http url, set `source["plain_http"] = "https failed: <reason_class>"`, print `S12 fetched over plain http (https failed: tls)`. Both fail → today's UNREACHABLE line. validate_ledger `ledger/https` skips a source carrying `plain_http`. Tests for fallback success, both-fail, and the ledger/https skip.

F BUG-6/7/8 docs (SKILL.md, runtime/commands area and §1, §7): (1) after init: "init writes `report.md` (skeleton) and `ledger.json`; a host that guards Write with Read: Read `report.md` and `reviews/<kind>.json` with the Read tool before writing them — a shell `cat` does not count." (2) Write every alx command in full; never `A="…"; $A …` (zsh runs the whole string as one command name). (3) review set example with a real path: `alx review set rewild findings.0.disposition=resolved fidelity_checks.quotes_unchanged=true` (use the real path syntax `_assignment_tokens` accepts — check it); `review finish` fills `status`; there is no `--status` flag.

G BUG-9: `alx claim schema` prints, from references/claim-input.schema.json, one line per property: name, type, enum values if any, `required` marked; then the four gate-required fields. SKILL.md §3 mentions it in one clause. Test.

H excerpt binding after Rewild: in `_binding_findings`, the excerpt re-derive block (bound paragraph still exists but no longer contains the excerpt → `report_excerpts = [prose[:EXCERPT_CHARS]]`, then save_ledger) runs on every `check` and `issue`, not only under `--fix`. `--fix` keeps the marker/link rewrites. Field run: 4 false `binding/excerpt-missing` lines at issue after Rewild → 0. Test: bound claim, paragraph reworded at its start, plain `check` → no excerpt-missing line.

Not changed: coverage status stored as given (R35.14); WARN tiers; disposition enum stays resolved|rejected.

## W15 delta (runs 2026-09-17-01-37-17 and 01-36-37, same session, same worktree)

Triage. Run 01-37-17 report: item 1 (circular supports WARN at add, HARD at check) FALSE — the cycle is WARN in both; the 3 HARD were unbound claims. Item 2 (review set cannot express arrays/objects) half true: values already parse as JSON and paths index arrays; undocumented. Item 3 (review finish feedback unclear) FALSE — finish printed the unfilled scores and false checks; the agent's own filler script crashed. Run 01-36-37 report: P1 TLS = same as task E, plus the https-original case (record 53: original https url, cert hostname mismatch). P1 `claim add` does not validate kind FALSE — record 158 shows the FAIL line with the enum. P2 `ledger merge` synthesis-as-list REAL: stored via the top-level `else`, next merge and `check` crash with tracebacks (records 146/149). P2 review finish not idempotent FALSE — two invocations 35 s apart, finish copies report.md into the review dir, re-finishing re-attests, harmless. P2 language mix: no detector exists; add a narrow WARN. P3 English guidance text: no quality impact, not changed. P3 quantity on unreachable sources FALSE — S8/S4 were fetched; B6 ruling stands. P3 install_runtime encoding: real, trivial. P3 render sparse page: ruled 0917 (WARN by design).

I `claim add` on a file that is not valid JSON prints one line like `ledger merge` does (`<file> is not valid JSON: <msg> at line L column C`), exit 1, no traceback. Test.
J SKILL.md §7: `review set` values parse as JSON when they can (arrays, objects, true/false, numbers), else string; paths index arrays with `.N.`. Example with real note fields: `'evidence_limitations=["…"]' checks.<real key>=true section_reviews.0.<real key>=…`. Keep the 3200-word pin (tests/test_repository_contract.py).
K `ledger merge`: for a mergeable key whose patch value type does not match the expected type (`brief`/`synthesis` object; `people`/`coverage`/`unresolved_questions` list) print `WARN <key>: expected object, got list — not merged` and skip that key (never crash, exit 0). `_ledger_findings` (alx.py ~2892) tolerates a non-dict `synthesis` (treated as empty). Tests: list synthesis merge → WARN, ledger unchanged, `check` exit 0.
L Extend task E: an https url whose fetch is unreachable with reason_class `tls` also retries over plain http (same host/path), same `plain_http` note and line. Test.
M scripts/install_runtime.py:102 `read_text(encoding="utf-8")`.
N `integrity/language-mix` WARN (validate_report integrity findings, zh-CN/zh-HK only): a run of ≥ 4 consecutive ASCII words (letters/digits, space-separated) in body prose — excluding markdown links, URLs, code spans, the Sources section — prints `paragraph <n>: "<first 60 chars of the run>"`, at most 5 lines, one family line. Never blocks. Tests: English sentence inside a zh paragraph → line; "Hoover Institution" alone → no line.
