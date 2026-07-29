# Alexandria 10/10 Completion Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every confirmed P0/P1 blocker left after commit `9faeb50`, prove the standard unit suite is hermetic, and withhold the 10/10 verdict until pushed `main` passes its real GitHub workflow.

**Architecture:** Preserve the fail-closed production source-fidelity contract: only a complete live check through the DNS-pinned HTTP transport may authorize delivery. Make tests deterministic at the transport boundary with one shared test utility that supplies public DNS answers and pinned HTTP responses, and remove the separately confirmed dependency-security blocker by pinning the fixed Pillow release in both package manifests.

**Tech Stack:** Python 3.10–3.14, `unittest`, GitHub Actions, `pip-audit`, Pillow, WeasyPrint, Ruff.

## Global Constraints

- Work directly on `main`; do not create a worktree or pull request.
- Fix only confirmed P0 and P1 findings; ignore minor cleanup.
- Never weaken the rule that skipped, incomplete, test-transport, empty, mismatched, or unverified source checks cannot issue a delivery receipt.
- Generalize fixes at the shared dependency or transport boundary, not in individual assertions.
- Preserve all unrelated user changes.
- Commit and push only after fresh complete verification.
- After push, synchronize `/Users/wallny/.codex/skills/alexandria` to the pushed repository and verify content parity.

---

### Task 1: Remove the vulnerable image dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: the same Pillow API already used by Alexandria's image and PDF pipeline
- Produces: one identical fixed Pillow pin for installation through either manifest

- [ ] **Step 1: Preserve the failing security evidence**

Record the GitHub Actions result for run `30407718950`: `pip-audit` rejects `Pillow==12.1.1`, with fixed versions culminating in `12.3.0`.

- [ ] **Step 2: Change both manifests**

Replace `Pillow==12.1.1` with `Pillow==12.3.0` in `requirements.txt` and `pyproject.toml`; no other dependency changes belong in this task.

- [ ] **Step 3: Verify the dependency and rendering contract**

Run:

```bash
python -m pip install -r requirements.txt
python -m pip_audit -r requirements.txt --vulnerability-service osv
python -m unittest -v tests.test_md_to_pdf tests.test_pdf_quality tests.test_validate_report
```

Expected: installation succeeds, the audit reports no known vulnerabilities, and every image/PDF test passes.

### Task 2: Make receipt-building tests independent of DNS and HTTP

**Files:**
- Create: `tests/source_fidelity_transport.py`
- Modify: `tests/test_content_gate.py`
- Modify: `tests/test_source_fidelity.py`
- Modify: `tests/test_rewild_receipt.py`

**Interfaces:**
- Produces: `mock_production_transport(responses)` context manager
- `responses` maps host names to `(status, headers, payload)` tuples
- The context manager patches only the production resolver and pinned request boundary while leaving receipt validation, observation creation, probe matching, sampling, hashing, and gate composition real

- [ ] **Step 1: Preserve the failing offline regression**

Run the affected modules with `socket.getaddrinfo` forced to raise for `example.com`, `example.org`, and `example.net`.

Expected before the fix: 67 tests run with exactly 14 errors—10 content-gate, 2 Rewild-receipt, and 2 source-fidelity receipt tests.

- [ ] **Step 2: Add the shared deterministic transport utility**

Implement a context manager that:

```python
@contextmanager
def mock_production_transport(responses):
    ...
```

Its resolver must return a syntactically public IPv4 address for mapped hosts and fail for unmapped hosts. Its request function must return only the mapped `(status, headers, payload)` response for the validated target host. It must patch `scripts.source_fidelity.socket.getaddrinfo` and `scripts.source_fidelity._request_pinned` for the duration of the context, then restore both.

- [ ] **Step 3: Replace every partial or live receipt setup**

Use the shared context manager in the content-gate fixture builder, both source-fidelity receipt tests, and both Rewild receipt audit tests that call `build_case()`. Do not change production receipt acceptance or add an offline passing state.

- [ ] **Step 4: Verify the regression is green**

Run the same forced-offline 67-test command.

Expected after the fix: 67 tests pass with zero failures and zero errors.

- [ ] **Step 5: Verify the whole standard suite is hermetic**

Run all tests with DNS and TCP connection attempts forced to fail unless a test's explicit scoped mock replaces them.

Expected: all tests pass without an external DNS lookup or TCP connection.

### Task 3: Close image-decoding and cover-HTML security boundaries

**Files:**
- Modify: `scripts/md_to_pdf.py`
- Modify: `scripts/pdf_templates.py`
- Modify: `tests/test_md_to_pdf.py`

**Interfaces:**
- Consumes: cover images, local Markdown images, embedded image data URLs, and template cover sources
- Produces: decoded PNG/JPEG/GIF/WebP assets within explicit byte, pixel, frame, and aggregate-pixel budgets; escaped HTML attributes for every template

- [ ] Reject an unsupported decoded format even when its suffix or data-URL media type is allowed.
- [ ] Reject excessive decoded dimensions, animation frames, and aggregate pixels before rendering.
- [ ] Decode every accepted frame at the validation boundary.
- [ ] Escape the final cover-image attribute for all eleven templates, including Maison, Terrain, Apricot, and Horizon.
- [ ] Prove a crafted filename cannot inject elements or CSS into the gated report.

### Task 4: Preserve quantitative meaning and mandatory person safeguards

**Files:**
- Modify: `scripts/validate_ledger.py`
- Modify: `references/evidence-ledger.schema.json`
- Modify: `tests/test_validate_ledger.py`

**Interfaces:**
- Consumes: quantities in claims, evidence extracts, derivations, and report excerpts; named-person assertions in every archetype
- Produces: structured quantity identities preserving sign, comparator, magnitude, scale, currency, and dimension; mandatory registry/status linkage for named-person harm

- [ ] Reject opposite signs, incompatible comparators, and incompatible units.
- [ ] Normalize equivalent English and Chinese scales while rejecting different magnitudes.
- [ ] Cover percentages, currencies, time, data, counts, accounting negatives, and Simplified/Traditional Chinese numerals.
- [ ] Detect named-person harmful or sensitive claims even when `people`, `person_ids`, or `human_harm_review` were omitted.
- [ ] Require the existing independent-source, accountable-record, attribution, response-search, privacy, and materiality protections after detection.

### Task 5: Validate every visible report assertion

**Files:**
- Modify: `scripts/validate_report.py`
- Modify: `scripts/rewild_gate.py`
- Create if needed: `scripts/report_blocks.py`
- Modify: `tests/test_validate_report.py`
- Modify: `tests/test_rewild_gate.py`
- Modify: `tests/test_rewild_receipt.py`

**Interfaces:**
- Consumes: one parsed Markdown block stream shared by evidence and Rewild validation
- Produces: exactly one terminal Sources section and validation coverage for every visible non-bibliography block

- [ ] Reject duplicate or non-terminal Sources headings.
- [ ] Validate assertions in tables, headings, questions, blockquotes, callouts, standfirsts, and transition-prefixed paragraphs.
- [ ] Exempt only strict document metadata and fenced code.
- [ ] Prove unsupported visible content cannot receive Rewild, content, Markdown, or PDF authorization.

### Task 6: Re-read live sources at final delivery

**Files:**
- Modify: `scripts/source_fidelity.py`
- Modify: `scripts/md_to_pdf.py`
- Modify: `scripts/validate_report.py`
- Modify: `tests/test_source_fidelity.py`

**Interfaces:**
- Produces: `validate_source_fidelity_receipt_online()` and final render/report validation that performs a fresh production-transport check

- [ ] Prove a structurally valid fabricated receipt cannot authorize delivery without a fresh source read.
- [ ] Re-run the exact receipt sample through the production transport at PDF render and final report validation.
- [ ] Reject mismatches, unavailable sources, changed selection, skipped checks, and test transports.

### Task 7: Bind the PDF to its gated artifacts

**Files:**
- Create: `scripts/render_binding.py`
- Modify: `scripts/md_to_pdf.py`
- Modify: `scripts/validate_report.py`
- Create: `tests/test_render_binding.py`
- Modify: `tests/test_md_to_pdf.py`
- Modify: `tests/test_validate_report.py`

**Interfaces:**
- Consumes: exact report, ledger, Rewild receipt, content receipt, and source-fidelity receipt
- Produces: an embedded SHA-256 render-binding token and final PDF validation against the current five artifacts

- [ ] Embed one canonical binding token in PDF metadata during rendering.
- [ ] Reject a missing, malformed, stale, or different-artifact binding.
- [ ] Reproduce and close validation of an unrelated high-quality PDF beside a valid current report.

### Task 8: Prove release completion

**Files:**
- Modify: current P0/P1 files only if verification exposes another confirmed P0/P1 defect
- Update after push: `/Users/wallny/.codex/skills/alexandria`

**Interfaces:**
- Produces: a clean pushed `main`, a matching installed skill, and a successful GitHub Actions run for the pushed commit

- [ ] **Step 1: Run local release verification**

Run the complete unit suite, forced-offline suite, Ruff, Python compilation, dependency audit, JSON/schema parsing, and `git diff --check`.

- [ ] **Step 2: Run production artifact verification**

Build the gated English, Simplified Chinese, and Hong Kong fixtures, render and validate all 11 templates in all three languages, rasterize sample pages, and run the PDF-quality checks.

- [ ] **Step 3: Test the committed contents independently**

Create a temporary directory from `git archive`, install the declared requirements, and repeat the release checks needed to prove no ignored or untracked file is required.

- [ ] **Step 4: Commit and push `main`**

Commit only reviewed P0/P1 remediation files, push `main`, and verify `HEAD == origin/main`.

- [ ] **Step 5: Synchronize the installed skill**

Copy repository-controlled skill files to `/Users/wallny/.codex/skills/alexandria`, remove obsolete installed files except runtime caches, and verify repository/installed hashes match.

- [ ] **Step 6: Verify the real GitHub workflow**

Wait for the GitHub Actions run attached to the pushed commit. Completion requires every matrix job and every gate to finish successfully.

- [ ] **Step 7: Perform the final completion audit**

Re-read this plan and every reviewer report. A 10/10 verdict is allowed only if every P0/P1 item has direct passing evidence and no required evidence is missing.
