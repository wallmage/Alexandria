# Alexandria Content Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Alexandria’s research depth, reasoning, decision value, and final writing quality enforceable rather than aspirational.

**Architecture:** Upgrade the evidence ledger to a versioned research-and-synthesis record, add deterministic semantic invariants, and add a report-bound content review gate after Rewild. Keep nuanced editorial judgment in one focused reference file and enforce its completion through a hashed review receipt.

**Tech Stack:** Python 3.10+, JSON Schema Draft 2020-12, Markdown, unittest, existing Alexandria validators.

## Global Constraints

- Preserve English reports at 7,500–15,000 words.
- Preserve Chinese reports at 5,000–10,000 non-whitespace characters.
- Do not change the PDF template portfolio or rendering behavior.
- Work on `main`; do not create a worktree or pull request.
- Add tests before production behavior.

---

### Task 1: Evidence ledger version 2

**Files:**
- Modify: `references/evidence-ledger.schema.json`
- Modify: `scripts/validate_ledger.py`
- Modify: `tests/test_validate_ledger.py`
- Modify: `tests/fixtures/evidence-ledger.json`

**Interfaces:**
- Consumes: ledger JSON.
- Produces: `validate_references(data) -> list[str]` with coverage, triangulation, contradiction, and synthesis errors.

- [ ] **Step 1: Write failing tests**

Add tests for unresolved priority coverage, missing gap impact, weak key-judgment triangulation, asymmetric contradiction links, disputed claims without resolution, and invalid synthesis references.

- [ ] **Step 2: Run the ledger tests**

Run `python -m unittest tests.test_validate_ledger -v`. Confirm failures identify missing invariants.

- [ ] **Step 3: Extend the schema and validator**

Add `schema_version`, `brief`, richer coverage, source roles, claim importance and reasoning, triangulation records, and synthesis.

- [ ] **Step 4: Upgrade the ledger fixture**

Make the fixture a minimal valid version-2 ledger with one authoritative fact, one key analysis, and one evidence-backed takeaway.

- [ ] **Step 5: Run the ledger tests**

Run `python -m unittest tests.test_validate_ledger -v`. Expect all tests to pass.

### Task 2: Content review gate

**Files:**
- Create: `references/content-review.schema.json`
- Create: `scripts/content_gate.py`
- Create: `tests/test_content_gate.py`
- Modify: `scripts/validate_report.py`
- Modify: `tests/test_validate_report.py`

**Interfaces:**
- Consumes: final Markdown, evidence ledger, content review JSON.
- Produces: `run_content_gate(report, ledger, review, receipt) -> list[str]` and a hash-bound receipt.
- Produces: `validate_content_receipt(report, ledger, receipt, expected_lang=None) -> list[str]`.

- [ ] **Step 1: Write failing gate tests**

Test low scores, stale hashes, unresolved critical findings, undisclosed major limitations, and a clean passing review.

- [ ] **Step 2: Run the gate tests**

Run `python -m unittest tests.test_content_gate -v`. Confirm the module is missing.

- [ ] **Step 3: Implement the review schema and gate**

Validate the note, rerun ledger and report-to-ledger checks, verify disclosures, and write the receipt atomically only on success.

- [ ] **Step 4: Require the receipt in final report validation**

Add `--content-receipt` and reject missing, stale, wrong-language, or changed-ledger receipts.

- [ ] **Step 5: Run gate and report tests**

Run `python -m unittest tests.test_content_gate tests.test_validate_report -v`.

### Task 3: Research and editorial workflow

**Files:**
- Create: `references/content-quality.md`
- Modify: `references/research-protocol.md`
- Modify: `references/editorial-en.md`
- Modify: `references/editorial-zh.md`
- Modify: `references/editorial-modes.md`
- Modify: `SKILL.md`
- Modify: `references/pdf-production.md`

**Interfaces:**
- Consumes: the approved research brief, evidence ledger, and final report.
- Produces: an adversarial research pass, a value-density edit, a content review note, and a content receipt.

- [ ] **Step 1: Add repository-contract tests**

Require the new reference, content gate command, receipt argument, unchanged length bounds, and explicit counterevidence and decision-usefulness checks.

- [ ] **Step 2: Run the contract tests**

Run `python -m unittest tests.test_repository_contract -v`. Confirm the new contract fails.

- [ ] **Step 3: Write the content-quality reference**

Define the reader contract, query matrix, source portfolio, synthesis ladder, section value test, recommendation standard, forecast discipline, and reviewer rubric.

- [ ] **Step 4: Integrate the workflow**

Place the content review before final validation, after Rewild, and require rerunning it after any report or ledger change.

- [ ] **Step 5: Run the contract tests**

Run `python -m unittest tests.test_repository_contract -v`.

### Task 4: Fixture and CI integration

**Files:**
- Modify: `tests/build_gated_fixtures.py`
- Modify: `.github/workflows/test.yml`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consumes: language fixtures and the shared evidence ledger.
- Produces: Rewild and content receipts for English, Simplified Chinese, and Hong Kong Traditional Chinese validation.

- [ ] **Step 1: Add failing pipeline assertions**

Require all three validation commands to pass `--content-receipt`.

- [ ] **Step 2: Run the contract tests**

Confirm the workflow and fixture builder fail the new assertions.

- [ ] **Step 3: Build review notes and receipts**

Generate deterministic review notes bound to each expanded fixture, run `content_gate.py`, and pass the receipts to `validate_report.py`.

- [ ] **Step 4: Run the full suite**

Run `python -m unittest discover -s tests -v` and compile all scripts.

### Task 5: Deployment and completion audit

**Files:**
- Modify as required by failed verification only.

**Interfaces:**
- Produces: published `main` and an identical installed skill.

- [ ] **Step 1: Validate schemas and fixtures**

Run the ledger validator, content gate, Rewild gate, report validator, and representative PDF render.

- [ ] **Step 2: Inspect the final diff**

Run `git diff --check`, review every changed file, and confirm `reports/` remains untouched.

- [ ] **Step 3: Commit and push**

Commit the complete upgrade and push `main`.

- [ ] **Step 4: Refresh the installed skill**

Synchronize the committed files to `~/.codex/skills/alexandria` and compare every tracked file by SHA-256.

- [ ] **Step 5: Rerun the suite from the installed directory**

Run all tests from the installed skill path.

- [ ] **Step 6: Audit every requirement**

Match the approved quality goals to source files, tests, gate outputs, and final repository state before declaring completion.
