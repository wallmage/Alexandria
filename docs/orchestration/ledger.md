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
- 09-14 execution: docs committed on main (62522f6). Worktrees (branch wip/<name>) under scratchpad/wt/: t1-fidelity t2-ledger t3-rewild t4-gates t5-alx t6-docs, all from 361298e. Briefs: .superpowers/sdd/09-14-01-plan/task-N-brief.md (git-ignored). Prompts: scratchpad/prompts/task-N.prompt.txt. Reports expected: scratchpad/reports/task-N-report.md.
  Dispatched: T1,T2,T4,T6 → Cursor grok-4.6-medium-fast (fleet monitor bf7my8fo7, logs scratchpad/fleet/tN.log); T3,T5 → Workflow opus high (run wf_e7197c21-43d). Task reviewers: grok-written → Workflow opus medium; opus-written → Cursor grok-medium --mode ask.
  Merge order plan: T2 (gate_severity.Finding) → T1 → T4 → T3 → T5 → T6; full suite after each; seams fixed by one Cursor dispatch (T7).
- T6: DONE (507 pass). Review (opus medium): spec ❌ 6 Important (invalid enum, time boxes, length floor, WARN families, weak assertion, README grammar). Fix round 1 (cursor resume): all fixed; scoped re-review done by orchestrator via grep + focused tests (18 pass). Task 6: complete (uncommitted in wt/t6-docs; deferred minor: quotation-lost alias collapse at T7).
- T1 DONE 524 pass; T2 DONE 526 pass; T4 DONE 527 pass — reviews running (wf_5fc86d92, wf_0c82cb2d, wf_6d6263fd). T3/T5 still implementing (wf_e7197c21).
- Reviews r1: T1 ❌ (Critical: policy v2 dead; Important ×7) → fix1 running (blu7n0f47). T2 ❌ (Important ×6: substring family classifier, dead granularity warn, remedies w/o operands, invented status/prose) → fix1 running (bu4398i0x). T4 ❌ (Critical ×2: --issue-receipt render crash, pdfkit timeout escapes; Important ×5) → fix1 running (bwhck52ja).
  Rulings: (R1) source_fidelity owns `record_probe_contexts(cache_dir, source_id, claim_id, probes)`; refresh preserves `probe_contexts`; alx claim add calls it. (R2) T4 owns references/content-review.schema.json and adds optional `claim_support[]`. Cost if wrong: seam rework at T7.

## HANDOFF (written 09-14 before manual compaction) — read this first on resume
Goal: implement spec v3 (docs/orchestration/09-14-01-spec.md) per plan (docs/orchestration/09-14-01-plan.md); orchestrator = judge (no more debate rounds, user decision). User wants context ≤300–400k: keep turns lean, delegate reads, do not paste diffs.
Progress ≈ 55% by effort. Remaining: finish T1/T2/T4 fix rounds → scoped re-checks; T3/T5 reports → reviews → fixes; T7 integration; e2e ×2; final review; merge/push/cleanup.

### Paths
- Repo main: /Users/wallny/Developer/Skills/alexandria (docs committed at 62522f6; ledger.md edits uncommitted).
- Scratchpad S=/private/tmp/claude-501/-Users-wallny-Developer-Skills-alexandria/1095d7dd-74cb-4300-9a63-e72f22f9f774/scratchpad
  - worktrees: $S/wt/{t1-fidelity,t2-ledger,t3-rewild,t4-gates,t5-alx,t6-docs} (branches wip/<name>, base 361298e, all changes UNCOMMITTED)
  - prompts: $S/prompts/task-N.prompt.txt, task-N-fix1.prompt.txt · reports: $S/reports/task-N-report.md · diffs: $S/reviews/tN.diff · fleet logs: $S/fleet/*.log, *.final.txt
  - fixture (friend's final ledger 25/25 + report): $S/fixture/ · session log: $S/log/
- Briefs: .superpowers/sdd/09-14-01-plan/task-N-brief.md (git-ignored).
- Runtime installed: ~/.alexandria/runtime (install.sh OK). Test cmd: .venv/bin/python -m pytest -q (503 pass baseline + 3 README subtests fixed by T6). Ruff: .venv/bin/python -m ruff check scripts tests.

### Agents (as of handoff)
- Cursor sessions (resume with `cursor-agent … --resume <id>`): T1 bd457f75-9497-4a02-b6ec-d767fbd0e2a8 · T2 217e0178-4ca3-4f58-aa9a-542733fab11b · T4 438c74f6-ace1-4832-9439-16319ef4a414 · T6 79d215ed-ce33-47a3-8c6e-a2cf9a09a9b9.
- Running at handoff: t1-fix1 (Monitor blu7n0f47), t2-fix1 (bu4398i0x), t4-fix1 (bwhck52ja), T3+T5 Workflow wf_e7197c21-43d (opus high; results → journal.jsonl under ~/.claude/projects/-Users-wallny-Developer-Skills-alexandria/1095d7dd-74cb-4300-9a63-e72f22f9f774/subagents/workflows/wf_e7197c21-43d/). Their final replies land in $S/fleet/tN-fix1.final.txt and $S/reports/task-3-report.md / task-5-report.md.
- Review script (reusable): Workflow scriptPath ~/.claude/projects/…/workflows/scripts/alexandria-task-review-wf_b38dedec-e33.js with args {task, brief, report, diff, worktree, model:"opus", effort:"medium"}; T3/T5 (opus-written) reviewers should instead be Cursor `cursor-grok-4.6-medium-fast --mode ask` per roster.

### Next steps (in order)
1. When fix rounds land: verify each with focused tests + greps of the named findings (cheap) instead of full re-reviews; mark Task N complete in Task log.
2. T3/T5: package diff (`cd wt; git add -N .; git status --short; git diff --stat; git diff -U10 > $S/reviews/tN.diff`), dispatch reviewer, one fix round max, then adjudicate.
3. T7 merge order on main: T2 → T1 → T4 → T3 → T5 → T6. For each: `git -C main checkout main; git merge wip/<name>` is NOT possible (uncommitted) → commit inside each worktree first (`git add -A && git commit -m "<task>"` with Co-Authored-By line), then merge serially, run full suite after each; seam fixes by ONE Cursor dispatch (families naming, Finding import fallbacks, claim_support schema, quotation-lost alias collapse in gate-errors.md, alx ↔ T1 record_probe_contexts).
4. Regression: run `alx check` on $S/fixture (copy into a temp workspace via alx init + place files) → grouped output, no traceback.
5. e2e clean path (spec §10): fresh dir; SKILL.md from main; Cursor `cursor-grok-4.6-medium-fast` with the friend's prompt (蒋介石日记, zh-CN); 60-min cap; then Codex gpt-6-astra control. Record timings/gate rounds here.
6. Final judgment review (Cursor xhigh --mode ask, judgment-reviewer.md) on the merged branch; push main; `git worktree remove` each wt; `git branch -d wip/*`; report "Rulings I made" (R1, R2 + debate rulings above) to user.
- T4 fix1 DONE: 535 pass (+3 README = T6). Critical ×2 fixed, Important fixed, minor 14 deferred. Task 4: complete pending integration.
