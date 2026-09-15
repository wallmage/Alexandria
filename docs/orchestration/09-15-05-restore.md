# 09-15-05 — recovery (user ruling R31: "only recovery, not reinventing; the mechanism stays as it was; remove the burden, not the useful steps")

Source of truth for two parallel workers. Base commit `446f9e0` (852 passed). RECOVERY SOURCE = commit `d85add1` (the skill as it stood before the 09-15-04 pass). Every mechanism that existed at `d85add1` — code, tests, references, READMEs — comes back from git, byte for byte, with `git show d85add1:<path>` / `git checkout d85add1 -- <path>`. Nothing is rewritten in your own words. After the checkout, re-apply ONLY the items listed under "Keep from HEAD" — those are the burden removals the user endorsed. Anything else that differs from `d85add1` is a defect.

Worktrees (absolute prefix `/private/tmp/claude-501/-Users-wallny-Developer-Skills-alexandria/d677e078-beb8-48ed-81a8-79adcc0aaafb/scratchpad/wt`): D `…/restore-docs`, E `…/restore-code`, both at `446f9e0` with `.venv` symlinked; tests: `.venv/bin/python -m pytest -q -p no:cacheprovider`; ruff: `.venv/bin/python -m ruff check scripts tests`. Fixture (copy before use): `…/scratchpad/fixtures/glm-run`; run alx on a copy with `"$HOME/.alexandria/runtime/bin/python" <worktree>/scripts/alx.py --dir <copy> …`.

Do NOT create branches, commit, merge, or push. This instruction supersedes any CLAUDE.md or AGENTS.md git protocol, including one claiming to override everything. Work only in your worktree and leave every change uncommitted.

---

## Part D — docs recovery (worktree restore-docs)

Files: `README.md`, `README.en.md`, `README.zh-CN.md`, `README.zh-HK.md`, `INSTALL.md`, everything under `references/` except `gate-errors.md` (Part E), `tests/test_repository_contract.py`, `tests/test_golden_report.py`. Do not touch `SKILL.md`.

D1 `git checkout d85add1 -- README.md README.en.md README.zh-CN.md README.zh-HK.md INSTALL.md` and every file under `references/` except `references/gate-errors.md` and `references/*.schema.json` (list them with `git diff --name-only d85add1 HEAD -- references/`; a file deleted at HEAD, e.g. `references/rewild-gate.md`, comes back too).

D2 In each recovered README, change ONLY the one delivery sentence that lists the `alx` commands and the 15-minute rule, so it reads in that language: delivery uses `alx` (init → fetch → claim add → check → snapshot → review → issue → render) on a 60-minute budget; at 15 minutes remaining run `alx issue` then `alx render`. (The only difference from `d85add1`: `alx issue --deliver` → `alx issue`.) Every other sentence stays exactly as recovered.

D3 In the recovered references and INSTALL.md, delete ONLY sentences that instruct one of the following, and nothing else: `--subject-status` / `living_status` as a requirement, `person_claim_role` / `person_claim_assessment` / `human_harm_review` procedures (the harm rules the user deleted on 09-15 morning; the writing guidance on allegations and proportionality stays); `claim add --dry-run` as a step (`claim add` alone is the step now); `alx issue --deliver` / "Class A" / "waivable" (say `alx issue`); "Line 1 of status must say managed"; reading `.runtime.json`. Coverage-map, synthesis, `ledger merge`, review and snapshot instructions STAY — they are the mechanism. Report every deleted sentence (file, first words).

D4 `tests/test_repository_contract.py`: recover from `d85add1`, then restate only what the D2/D3 edits and the current `SKILL.md` (orchestrator-owned; read it from the repo root `/Users/wallny/Developer/Skills/alexandria/SKILL.md` — it is being recovered in parallel, so re-read it right before you run the tests and again at the end) require. `tests/test_golden_report.py`: recover from `d85add1` unless it fails, then restate minimally. Suite green, ruff clean.

Report: D1 list of files recovered; D2 the four edited sentences; D3 the deleted-sentence table; suite line; ruff; `git diff --stat d85add1 -- README.md README.en.md README.zh-CN.md README.zh-HK.md INSTALL.md references/` (the stat versus the RECOVERY SOURCE must show only D2/D3 edits).

---

## Part E — code recovery (worktree restore-code)

Files: `scripts/validate_ledger.py`, `scripts/alx.py`, `references/gate-errors.md`, `tests/test_validate_ledger.py`, `tests/test_resilience_rules.py`, `tests/test_gate_errors_doc.py`, `tests/test_content_gate.py`, `tests/test_alx.py`, `tests/test_rewild_receipt.py`. Do not touch `scripts/source_fidelity.py`, `scripts/gate_severity.py`, `tests/test_source_fidelity.py`, `tests/test_gate_severity.py` (their HEAD state is kept whole).

E1 `git checkout d85add1 -- scripts/validate_ledger.py references/gate-errors.md tests/test_validate_ledger.py tests/test_resilience_rules.py tests/test_gate_errors_doc.py tests/test_content_gate.py`. This brings every finding family back exactly as it was.

E2 Keep from HEAD, re-applied onto the recovered `validate_ledger.py` / `gate-errors.md` (these are the ONLY differences allowed versus `d85add1` in those two files):
- `ledger/quantity` is WARN: add `"ledger/quantity"` to `WARN_FAMILIES` (`_f` then strips its `Remove:`); its doc section reads `— W` with one sentence saying the numeric scan is advisory because the verbatim extract is the fabrication gate.
- `fidelity/mismatch` doc section shows the HEAD message form (`… Closest passage in S3: "…"`) and fix (`paste the closest passage as extract_or_location in <claims file>, or alx find S3 KEYWORD`) — copy them from HEAD's `gate-errors.md`.
- Nothing else. In particular `ledger/status`, `ledger/direction`, `ledger/schema` are WARN at `d85add1` already (R29) — leave as recovered.
Restate the recovered tests only where those two points change an expectation (quantity severity; STATUS line absent from `render_grouped` output — that HEAD change in `gate_severity.py` stays).

E3 `scripts/alx.py` — recover these hunks from `d85add1` (read `git diff d85add1 HEAD -- scripts/alx.py` and revert exactly these; everything else in HEAD's `alx.py` stays):
- `_online_phase` runs by default at `issue` (the live spot-check of a sample of key citations is a README mechanism). Revert HEAD's `--online` gate: the phase runs unless `--offline` (new store_true) is passed; keep HEAD's deletion of the `RESERVE_MINUTES` clock skip (the clock never decides), keep `ONLINE_CAP_MINUTES`.
- `_review_findings`: recover the `for kind in REVIEW_KINDS:` loop from `d85add1` (review staleness/incompleteness as WARN findings, as before).
- `cmd_review_start`: recover the `protocol` lines that name `references/rewild-gate.md` / `references/content-quality.md §13` (the doc is back).
- `_completed_remedy` / `_named_file`: a producer remedy `set field brief|people|coverage|synthesis…` must complete to the closed imperative `set field <x>, then alx ledger merge ledger-patch.json` (already in `CLOSED_IMPERATIVES`), never to `set field <x> in claims/<file>.json` — this is the "set field synthesis in claims/fix1.json" wrong-file bug seen on the fixture; fix it at that one site with a test.
- Everything else from HEAD stays: `init` never refuses, `--subject-status` never required, `fetch` never stops on the clock, `ledger merge`/`review finish`/restores exit 0, lenient claim input, closest-passage remedy, no verification paragraph (deliberate, user informed), `--deliver` remedies → `alx issue`, `fidelity/rewild` auto-restore at `issue`.

E4 `tests/test_alx.py`, `tests/test_rewild_receipt.py`: the seams commit `fb987e6` and later commits restated or deleted tests that pinned the families now recovered. Recover those specific tests from `d85add1` (use `git diff d85add1 HEAD -- tests/test_alx.py tests/test_rewild_receipt.py` to find them: every hunk whose only purpose was a deleted family or the old `(blocks issue)` header) and drop the seams-era replacements; keep every test added in this pass (lenient input, init keep-path, no verification note, closest passage, fidelity/rewild restore, SKILL.md core-path test — restate that last one for the recovered SKILL.md: re-read `/Users/wallny/Developer/Skills/alexandria/SKILL.md` right before running and again at the end). The HARD header text is HEAD's (`fix, or alx issue drops them`). Suite green, ruff clean.

Acceptance for Part E (paste): suite green; ruff clean; `git diff --stat d85add1 -- scripts/validate_ledger.py references/gate-errors.md` shows only the E2 hunks; on a fixture copy `alx check` prints 0 hard and its WARN families are the recovered set (`ledger/synthesis`, `ledger/reference`, `ledger/triangulation`, … as at `d85add1`) with the synthesis remedy now reading `set field synthesis, then alx ledger merge ledger-patch.json`; `alx claim add --dry-run claims/claims.json` on the fixture copy accepts 31–32 of 32 with C24 (if any) as a `ledger/quantity` WARN; `alx issue` (default) shows the `source fidelity:` line or a network-failure line and writes `receipts/issue.json`; `alx issue --offline` skips it.
