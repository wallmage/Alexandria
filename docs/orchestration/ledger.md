# Orchestration ledger — alexandria

## User decisions (verbatim)
- 2026-09-14: "Make our scale as resilient as possible... always provide the best quality Deep Researched report under 60 minutes... Whatever happens, we will always deliver... Burn tokens if you need to. I just want the best possible quality." (skill = the Alexandria skill)
- Delegation rule: orchestrator skill (/orchestrator).

## Standing orders
- Git: worktrees for edits; merge to main; no PRs; orchestrator owns git.
- Baseline: 503 passed, 3 pre-existing README subtest failures in tests/test_repository_contract.py (from commit 361298e). PARKED unless fixed by the README task.

## Task log
- 09-14 spec v1 written: docs/orchestration/09-14-01-spec.md. Debate: 3 seats (>4h job).
- 09-14 debate r1: 3 seats all REVISE (cursor 8, codex 12, codebuddy 10 findings; all accepted) → spec v2. r2 launched (resumed sessions: cursor 15efc6ac…, codex thread 01a0a034-8e82…, codebuddy 01a0a034-8c37…).
- Pending v3 edit: schema already has provenance enum `unverified` → D13 uses it (no new enum). Pinned fetch defaults: provenance=unverified, evidence_type=news_report, accountability_basis=none, roles=["independent_analysis"]; validate_ledger must treat `unverified` as non-independent in every rule (test).
- Runtime installed at ~/.alexandria/runtime (install.sh exit 0, smoke PDFs OK). Fixture (friend's final ledger 25/25 + report) at scratchpad/fixture/.
- 09-14 debate r2: all seats REVISE (cursor 4 new, codex 3 new + 4 partial, codebuddy 5 new). USER: "end after round 2… you be the adjudicator… no round 3." Spec v3 = final adjudication.
  Rulings (v3): accepted — render requires passed issue (cursor#9/codex#1); claim drop --apply deletes paragraph + excluded_claims (codex#13); Verification note by issue pre-hash (codex#15/cb#11); refresh → re-probe all claims (codex#14); changed context never self-authorizing (codex#9); fetch keeps transport lock, same-domain redirects (cursor#12); https scope url-only (cursor#11); person status at init (cursor#10); claim-input conditional fields + schema additions (codex#2); content review stale/missing = Class F, rewild review = Class A (codex#5 partial); default-to-F + explicit A list (cb#13); issue step semantics (cb#12); D14 scoped (cb#14); missing snapshot handled (cb#15). Rejected — none. Cost if wrong: drop cascade may over-delete prose under time pressure (accepted: shorter, never less true).
  Plan: no plan debate (user). Orchestrator = judge.
