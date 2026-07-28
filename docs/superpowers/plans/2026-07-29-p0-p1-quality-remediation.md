# Alexandria P0/P1 Quality Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every confirmed P0 and P1 defect in the current Alexandria tree while deliberately leaving P2 and P3 findings out of scope.

**Architecture:** Keep the existing report pipeline and strengthen three boundaries: rendered-page classification, source-to-ledger verification, and high-risk claim validation. Every production change starts with a behavior-level regression test, and the final gate exercises a clean repository copy plus the complete report workflow.

**Tech Stack:** Python 3.11–3.13, `unittest`, JSON Schema 2020-12, `urllib`, `pypdfium2`, `pypdf`, WeasyPrint, Markdown, CSS Paged Media.

## Global Constraints

- Work directly on `main`; do not create a worktree or pull request.
- Fix only confirmed P0 and P1 findings. Do not broaden the work to P2 or P3 cleanup.
- Preserve all existing user changes in the dirty checkout.
- Generalize every fix to the violated contract rather than special-casing one fixture, source, template, or phrase.
- Write and observe a failing behavior-level test before changing production code.
- A skipped or incomplete live-source check is not a passing delivery gate.
- Commit and push only after full verification, then synchronize the installed self-made Alexandria skill to the pushed commit.

---

### Task 1: Distinguish designed opener pages from blank spill pages

**Files:**
- Modify: `scripts/pdf_quality.py`
- Modify: `tests/test_pdf_quality.py`
- Modify: `.github/workflows/test.yml` only if the production command needs correction

**Interfaces:**
- Consumes: per-page ink, text, and fill metrics from `check_pdf()`
- Produces: `blank_page` findings only for genuinely empty or orphaned pages while preserving warnings for intentionally sparse layouts

- [ ] Add a real Markdown-to-PDF regression that renders every advertised template and demonstrates the current false failure on feature openers.
- [ ] Run the focused test and confirm it fails because valid opener pages are classified as blank.
- [ ] Add a negative fixture containing a genuine mid-document blank/orphan page and confirm the test protects the original purpose of the gate.
- [ ] Replace the independent ink-or-character failure rule with a structural decision based on combined visual and textual evidence.
- [ ] Run the focused PDF-quality tests and the actual all-template production loop.

### Task 2: Bind evidence excerpts to their individual sources

**Files:**
- Modify: `references/evidence-ledger.schema.json`
- Modify: `references/research-protocol.md`
- Modify: `SKILL.md`
- Modify: `scripts/validate_ledger.py`
- Modify: `scripts/source_fidelity.py`
- Modify: `tests/fixtures/evidence-ledger.json`
- Modify: `tests/test_validate_ledger.py`
- Modify: `tests/test_source_fidelity.py`

**Interfaces:**
- Consumes: `claim.source_evidence[]` entries containing one `source_id` and one exact extract/location
- Produces: one probe set per claim/source pair; multi-source claims never require one page to contain another page's evidence

- [ ] Add failing schema and runtime tests for one claim supported by two sources with different valid extracts.
- [ ] Confirm the current implementation falsely rejects both sources.
- [ ] Add a per-source evidence structure and validate complete, unique coverage of every direct source used by factual, reported, and estimated claims.
- [ ] Preserve the claim-level extract as a synthesis field while deriving live probes only from the matching per-source entry.
- [ ] Add mismatch, missing-source, duplicate-source, PDF-source, and zero-sample cases.
- [ ] Run focused ledger and source-fidelity tests.

### Task 3: Make live-source verification safe and mandatory

**Files:**
- Modify: `scripts/source_fidelity.py`
- Modify: `scripts/content_gate.py`
- Modify: `scripts/validate_report.py`
- Modify: `scripts/md_to_pdf.py`
- Modify: `references/research-protocol.md`
- Modify: `references/pdf-production.md`
- Modify: `SKILL.md`
- Modify: `tests/test_source_fidelity.py`
- Modify: `tests/test_content_gate.py`
- Modify: `tests/test_validate_report.py`
- Modify: `tests/test_md_to_pdf.py`

**Interfaces:**
- Consumes: HTTP(S) sources and the exact evidence ledger
- Produces: a source-fidelity receipt bound to the ledger, verifier, checked source/probe set, and successful online result

- [ ] Add failing tests for `file:`, `data:`, loopback, private, link-local, reserved, credential-bearing, unsafe-port, and redirect-to-private URLs.
- [ ] Add failing tests proving offline, zero-sample, mismatch, and unverified runs cannot issue a passing receipt or exit successfully.
- [ ] Restrict fetching to validated HTTP(S) destinations, validate every redirect, cap response bytes, and reject unsupported content types.
- [ ] Extract readable text from supported HTML/text/JSON and PDF sources.
- [ ] Issue receipts atomically only for complete passing online checks and validate their ledger/verifier hashes.
- [ ] Require the receipt in the content gate, report validator, and PDF renderer.
- [ ] Run focused security, receipt-tampering, and complete-gate tests.

### Task 4: Enforce exact quantitative support and living-person safeguards

**Files:**
- Modify: `references/evidence-ledger.schema.json`
- Modify: `references/person.md`
- Modify: `references/research-protocol.md`
- Modify: `SKILL.md`
- Modify: `scripts/validate_ledger.py`
- Modify: `tests/fixtures/evidence-ledger.json`
- Modify: `tests/test_validate_ledger.py`

**Interfaces:**
- Consumes: normalized quantitative forms, subject risk metadata, sensitive-claim classifications, accountable evidence, and right-of-reply records
- Produces: exact quantity/status matching and deterministic rejection of under-sourced harmful claims about living people

- [ ] Add a failing regression showing that a derived `120` cannot excuse unsupported `20`, including percent, date, version, and status variants.
- [ ] Replace substring matching with exact normalized obligation-to-derivation matching.
- [ ] Add failing cases for a living-person wrongdoing claim with one source family, no accountable record, no attribution, or no documented response search.
- [ ] Add explicit subject-status and claim-sensitivity metadata.
- [ ] Enforce two independent families, one declared accountable basis, attributed wording, and a represented response or bounded response search.
- [ ] Enforce a public-record/materiality justification for sensitive private information.
- [ ] Run focused schema and validator tests.

### Task 5: Final proof and release

**Files:**
- Modify: current P0/P1 files only when verification exposes another confirmed P0/P1 regression
- Update after push: `/Users/wallny/.codex/skills/alexandria`

**Interfaces:**
- Produces: a clean, pushed `main` commit and an installed skill identical to it

- [ ] Run the complete unit suite under the supported Python environment.
- [ ] Run Ruff, Python compilation, JSON/schema parsing, and `git diff --check`.
- [ ] Test from a clean `git archive`/temporary copy so untracked dependencies cannot hide release failures.
- [ ] Render and validate the complete 11-template × 3-language matrix with pinned fonts.
- [ ] Run a full gated report through ledger, live-source receipt, Rewild, content, Markdown, PDF, and visual-quality validation.
- [ ] Dispatch a final read-only P0/P1 audit and fix any confirmed P0/P1 finding it produces.
- [ ] Review the final diff, commit and push `main`.
- [ ] Synchronize `/Users/wallny/.codex/skills/alexandria` to the pushed repository state and verify file hashes.
