# Fable Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct every reproducible defect in Fable's review, strengthen the system-level contracts that allowed them, and replace or remove invalid demonstration artifacts.

**Architecture:** Treat the review as four connected quality systems: evidence validation, editorial/review gates, rendering, and documentation/samples. Each defect receives a regression test before its implementation; shared behavior is centralized rather than patched at individual call sites.

**Tech Stack:** Python 3.11–3.13, unittest, JSON Schema, Markdown, CSS Paged Media, WeasyPrint, pypdf, Poppler.

## Global Constraints

- Work directly on `main`; do not create a worktree or pull request.
- Preserve read/write safety, deterministic receipts, and Windows/macOS/Linux behavior.
- Prefer computed evidence over reviewer self-attestation.
- A sample artifact must pass the same current validators as a user deliverable.
- Do not claim completion without a fresh full test, lint, render, and validation run.

---

### Task 1: Rendering contract and CSS defects

**Files:**
- Modify: `scripts/pdf_templates.py`
- Modify: `scripts/md_to_pdf.py`
- Modify: `tests/test_md_to_pdf.py`

**Interfaces:**
- Consumes: `build_css(template, ...)`, HTML generation helpers.
- Produces: placeholder-free CSS for all templates and stable paged-media layout.

- [ ] Add failing tests for unresolved CSS placeholders, row splitting, margin-box padding, TOC numbering, HTML suppression, URL handling, cover escaping, fenced metadata, and locale-independent dates.
- [ ] Run the focused tests and confirm each fails for the reviewed defect.
- [ ] Build the full CSS string before token substitution and centralize shared page-layout rules.
- [ ] Fix table rows, header/footer rules, TOC paint order/counters, section heading grouping, metric/code/source presentation, and template-specific body treatments.
- [ ] Fix sanitizer suppression, URL/path conversion, single-point escaping, metadata parsing, and date formatting.
- [ ] Run focused rendering tests and full template renders.

### Task 2: Evidence and content-gate contracts

**Files:**
- Modify: `scripts/validate_ledger.py`
- Modify: `scripts/content_gate.py`
- Modify: `references/evidence-ledger.schema.json`
- Modify: `references/content-review.schema.json`
- Modify: `references/content-quality.md`
- Modify: `references/research-protocol.md`
- Modify: `tests/test_validate_ledger.py`
- Modify: `tests/test_content_gate.py`

**Interfaces:**
- Consumes: v3 evidence ledgers and content review notes.
- Produces: independently computable portfolio, confidence, freshness, traceability, and review pass/fail decisions.

- [ ] Add failing tests for an all-interested source portfolio, unsupported high-confidence inference, supported official-only coverage, false review booleans, and uncited decision language.
- [ ] Run focused tests and confirm reviewed behavior is currently accepted.
- [ ] Add portfolio-level independence and confidence checks, with explicit gap handling.
- [ ] Make review schemas record both pass and fail; keep pass enforcement in the gate.
- [ ] Derive machine-checkable checks from ledger/report data and retain reviewer judgment only where automation is not credible.
- [ ] Document confidence anchors, evidence-of-absence rules, freshness expectations, and omission rules.
- [ ] Run focused ledger and content-gate tests.

### Task 3: Rewild fidelity and receipt integrity

**Files:**
- Modify: `scripts/rewild_gate.py`
- Modify: `references/rewild-review.schema.json`
- Modify: `tests/test_rewild_receipt.py`
- Modify: `tests/build_gated_fixtures.py`

**Interfaces:**
- Consumes: pre-Rewild report, final report, review note.
- Produces: semantic-fidelity decisions and hash-bound receipts.

- [ ] Add failing tests for faithful above/below co-occurrence, Sources/URL exclusion, no-op resolved findings, atomic receipt preservation, and checker timeout/JSON parsing.
- [ ] Confirm each regression test fails for the expected reason.
- [ ] Restrict document-level semantic fallback to unaligned passages and use checker prose.
- [ ] Reject no-op reports that claim resolved edits.
- [ ] Cache repeated semantic tokenization.
- [ ] Write receipts atomically only after success and harden subprocess handling.
- [ ] Make fixtures contain genuine source/report deltas and negative gate cases.
- [ ] Run focused Rewild tests.

### Task 4: Shared platform behavior and dependency hygiene

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/report_contract.py`
- Modify: `scripts/md_to_pdf.py`
- Modify: `scripts/validate_report.py`
- Modify: `scripts/content_gate.py`
- Modify: `scripts/rewild_gate.py`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `tests/test_validate_report.py`

**Interfaces:**
- Produces: one language detector, one length policy, portable receipt paths, and explicit dependencies.

- [ ] Add failing tests for consistent language ties, Windows file URIs, moved receipt directories, and indirect PDF `/MarkInfo`.
- [ ] Centralize language detection, thresholds, stable English month names, and receipt path normalization.
- [ ] Replace dual import paths with package-relative imports plus script-entry compatibility.
- [ ] Pin Pillow explicitly and add complete project/test metadata.
- [ ] Run focused platform tests on the supported local environment.

### Task 5: Editorial rules, localized documentation, and sample integrity

**Files:**
- Modify: `references/editorial-en.md`
- Modify: `references/editorial-modes.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `README.zh-HK.md`
- Modify or remove: `reports/claude-code-vs-codex-2026-07-28/`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Produces: operational editorial constraints and no invalid flagship artifact.

- [ ] Replace tautological copy tests with behavioral contract tests.
- [ ] Add operational rules for serial enumeration, repeated epigrams, duplicate decision sections, quantified claims, terminology, and citation proximity.
- [ ] Correct Mainland/Hong Kong localization and remove repeated beauty claims.
- [ ] Remove the invalid legacy sample from the product surface unless it can be regenerated completely under the v3 contract.
- [ ] Render and visually inspect all eleven current templates using conformant gated fixtures.

### Task 6: Final verification and release

**Files:**
- Modify: `SKILL.md` and affected references for the final behavior.
- Update: installed Alexandria skill after repository commit/push.

**Interfaces:**
- Produces: verified repository and synchronized installed skill.

- [ ] Run `python3 -m unittest discover -s tests -t .`.
- [ ] Run Ruff and Python compilation.
- [ ] Generate gated fixtures, render every template/language combination, and validate every PDF.
- [ ] Render page images for all eleven templates and inspect representative cover, TOC, opener, table, and sources pages.
- [ ] Validate every bundled report/ledger/review/receipt artifact.
- [ ] Review `git diff`, commit on `main`, push, then synchronize the installed self-made skill to the committed version.
