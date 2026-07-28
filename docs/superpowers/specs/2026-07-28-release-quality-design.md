# Alexandria release-quality design

## Goal

Make every Alexandria report defensible as research, useful as a long-form
decision document, readable as human writing, and distributable as a
professional PDF. Preserve the intentional report-length ranges and all eleven
visual systems.

## Quality contract

### Research and content

- Evidence ledgers must reject duplicate source URLs and normalize source-family
  names before counting independent support.
- A key judgment may claim full triangulation only when it uses at least two
  source families and at least one independent source.
- Source and claim dates may not exceed the report date.
- Gaps must be genuine gaps, not coverage items with hidden supporting claims.
- Every report must document and resolve at least one serious rival hypothesis
  through an adversarial test.
- Final content review must account for every substantive report section and
  state the value that section adds.

### Design and PDF production

- Decorative accent colors remain vivid; small accent-colored text uses a
  separate accessible token with WCAG AA contrast.
- Generated PDFs include title, author, language, bookmarks, tagged structure,
  consistent A4 pages, selectable text, and clickable source links.
- Successful exports are readable by normal recipients, not owner-only.
- User-supplied cover images must meet a minimum print-resolution floor.
- Every template must render through the real PDF pipeline in CI.

### Supply chain and maintenance

- Runtime dependencies must have no known published vulnerabilities.
- CI runs unit, schema, compile, security, and all-template production checks.

## Compatibility

The evidence-ledger schema advances to version 3 and the content-review schema
to version 2. Existing reports need their review artifacts regenerated; this is
intentional because receipts are cryptographically bound to the schemas.
Report length, supported languages, template names, and command-line defaults
do not change.
