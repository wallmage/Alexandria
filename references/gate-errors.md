# Gate errors

Family → class → rule → fix → remove → example. Grouped by gate. Class F never waived; Class A only via `alx issue --deliver`.

Commands: `"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/alx.py" …`.

## Ledger (`check` b / `validate_ledger`)

### `ledger/quantity` — F
- **rule:** claim quantity uncovered or contradicted by extracts. Date fragments cover themselves; `n:` never covered by date parts.
- **fix:** `alx find S<n> TOKEN` then extend quote, or reword claim to dated form.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C8 asserts `n:1918`; S16 offers `d:1918-01` only.

### `ledger/status` — F
- **rule:** status assertion (patched, discontinued, approved, …) not in extracts.
- **fix:** quote a sentence carrying the status via `alx find`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** claim says "all since patched"; extract has figures only.

### `ledger/direction` — F
- **rule:** increased/decreased (and numeric/legal carriers) must appear in extracts. Bare `under|below|settled` without a carrier is not a trigger.
- **fix:** quote the directional sentence or drop the clause.
- **remove:** `alx claim drop C<n> --apply`
- **example:** "increased 12%" vs extract "12% in 2024".

### `ledger/schema` — F
- **rule:** ledger fails `evidence-ledger.schema.json`.
- **fix:** set field `<name>` in `ledger.json` via `alx ledger merge` (brief/people/coverage/synthesis only).
- **remove:** `alx claim drop C<n> --apply` if the invalid object is a claim.
- **example:** missing `schema_version`.

### `ledger/unverified-key-claim` — F
- **rule:** key/central claim cites `provenance: unverified` or interested-only sources. `unverified` counts as interested.
- **fix:** `alx source set S<n> --provenance P`
- **remove:** `alx claim drop C<n> --apply`
- **example:** C1 importance=key, S3 provenance=unverified.

### `ledger/person` — F
- **rule:** person-linked claim while `people[0].living_status` missing/`unknown`, or people row absent.
- **fix:** `alx ledger merge` people first.
- **remove:** `alx claim drop C<n> --apply`
- **example:** `claim add` refused: set people[0].living_status.

### `ledger/harm` — F
- **rule:** living/recently_deceased/unknown person claim missing `human_harm_review` keys.
- **fix:** set field `human_harm_review` in the claim-input file; `alx claim add`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** message lists missing harm keys.

### `ledger/excluded-supports` — F
- **rule:** surviving `supports` names an excluded claim.
- **fix:** set field `supports` in the claim-input file; `alx claim add`.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C4.supports includes dropped C2.

### `ledger/coverage` — W
- **rule:** coverage/synthesis linkage inconsistent (area status vs claim_ids).
- **fix:** set field `coverage` in the patch; `alx ledger merge`
- **remove:** n/a
- **example:** area `supported` with empty `claim_ids`.

### `ledger/synthesis` — W
- **rule:** synthesis linkage inconsistent with claims/coverage.
- **fix:** set field `synthesis` in the patch; `alx ledger merge`
- **remove:** n/a
- **example:** adversarial_tests names a dropped claim.

### `ledger/disputed` — W
- **rule:** disputed/resolution prose missing or one-sided.
- **fix:** set field `contradicts` / resolution prose via `alx claim add`
- **remove:** n/a
- **example:** C2 contradicts C1; C1 has no reciprocal note.

### `ledger/family-label` — W
- **rule:** `source_family` split from domain when the domain label is derivable (`check --fix` auto-derives).
- **fix:** `alx check --fix` or `alx source set` after fetch
- **remove:** n/a
- **example:** family `Acme Blog` vs domain `acme.example.com`.

### `ledger/derived-assertions` — W
- **rule:** `derived_assertions` excuses nothing (expression already in extract, or derivation empty).
- **fix:** set field `derived_assertions` in the claim-input file; `alx claim add`
- **remove:** `alx claim drop C<n> --apply`
- **example:** derived string copies the extract.

### `ledger/granularity` — W
- **rule:** bare-year vs year-month granularity (claim `n:1918` / `d:1918` vs extract `d:1918-01`).
- **fix:** reword to the dated form, or quote a bare-year sentence via `alx find`
- **remove:** `alx claim drop C<n> --apply`
- **example:** claim 1918; extract 1918年1月.

### `ledger/source-ids` — W
- **rule:** `source_ids` missing; derived from `source_evidence` (warn). Extras: one hard error per claim.
- **fix:** `alx check --fix`
- **remove:** n/a
- **example:** C5 has extracts on S1,S2; `source_ids` empty.

## Integrity (`check` a)

### `integrity/control-chars` — F
- **rule:** C0 except `\t\n\r`, or U+FFFD.
- **fix:** before snapshot, delete the bad bytes in `report.md`; after `alx snapshot`, `alx snapshot --restore`
- **remove:** `alx snapshot --restore` (no-op if no snapshot yet)
- **example:** U+FFFD in paragraph 12.

### `quotation-lost` / `integrity/quotation-lost` / `fidelity/quotation-lost` / `Fidelity/quotations` — F
- **rule:** snapshot quoted span (「」『』“”‘’ or straight "…" ≥ 4 chars) missing verbatim.
- **fix:** `alx snapshot --restore`
- **remove:** `alx snapshot --restore`
- **example:** 「西安事变」 dropped in humanize.

### `leftover-prose` — F
- **rule:** excluded claim's mapped paragraph text still in `report.md`.
- **fix:** delete paragraph `<n>` of report.md (or `alx claim drop` already should).
- **remove:** `alx claim drop C<n> --apply`
- **example:** C8 dropped; paragraph 19 still present.

## Cache / fidelity (`check` b,d / `source_fidelity`)

### `cache-detached` — F
- **rule:** `sources/S<n>.meta.json` url or text_sha256 ≠ ledger/cache.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** `alx claim drop C<n> --apply` for claims on that source.
- **example:** S7 meta url ≠ ledger url.

### `cache-missing` — F
- **rule:** extract probe has no `sources/S<n>.txt`.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** `alx claim drop C<n> --apply`
- **example:** S4 cache file absent.

### `fidelity/mismatch` — F
- **rule:** extract segment not in cache (offline) or live text (online). Full coverage.
- **fix:** `alx find S<n> KEYWORD`; extend the quote in claims/<file>.
- **remove:** `alx claim drop C<n> --apply`
- **example:** C3 segment "12个师" absent from S9.

### `fidelity/short-segment` — F
- **rule:** ellipsis-split segment < 8 normalized chars. Rejected, not skipped.
- **fix:** extend the quote in claims/<file>
- **remove:** `alx claim drop C<n> --apply`
- **example:** extract `…12日…`.

### `fidelity/context-changed` — F
- **rule:** probe present but probe-context hash changed vs research cache. Message quotes window; flags 更正|撤回|訂正|勘误|correction|retract|erratum|update.
- **fix:** `alx fetch --id S<n> --refresh` then re-probe.
- **remove:** `alx claim drop C<n> --apply`
- **example:** S7 window now starts with "勘误".

### `fidelity/unreachable` — A
- **rule:** live fetch dns/timeout/tls/http-*/plaintext-http/oversize/redirect-loop/cross-domain-redirect. Beyond quorum → Class A.
- **fix:** `alx fetch URL` (printed final URL if cross-domain) or `alx fetch --id S<n> --refresh`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `UNREACHABLE (cross-domain-redirect → https://other.example/x)`

### `fidelity/undecodable` — A
- **rule:** charset ladder failed or U+FFFD > 1%.
- **fix:** `alx fetch --id S<n> --refresh`
- **remove:** `alx claim drop C<n> --apply`
- **example:** `UNDECODABLE (gbk)`.

## Binding (`check` c)

### `binding/link-not-in-ledger` — F
- **rule:** body URL after normalize (lowercase scheme/host, strip fragment/`utm_*`, trailing slash) ∉ url∪aliases.
- **fix:** `alx fetch URL` or change the link to a ledger URL.
- **remove:** `alx claim drop C<n> --apply` if the claim depends on that URL.
- **example:** nearest ledger URL printed.

### `binding/ambiguous` — F
- **rule:** include_in_report claim maps to ≠1 paragraph; auto only when exactly one candidate.
- **fix:** `alx claim bind C<n> --paragraph N`
- **remove:** `alx claim drop C<n> --apply`
- **example:** candidates: 12, 19.

### `binding/missing` — F
- **rule:** claim without probed extracts or without a paragraph mapping.
- **fix:** `alx claim add` with extracts; `alx claim bind C<n> --paragraph N`
- **remove:** `alx claim drop C<n> --apply`
- **example:** C5 FAIL no extract.

## Rewild (`check` e)

### `rewild/semantic-fidelity` — F
- **rule:** negation/direction/causal/association broken vs snapshot (citation-stripped, terminator clauses).
- **fix:** `alx snapshot --restore` then re-humanize; or `alx review start rewild --iter`
- **remove:** `alx snapshot --restore`
- **example:** "may" → "will".

### `rewild/regional` — F
- **rule:** zh-HK register / regional identity failed.
- **fix:** edit per `references/rewild/rewild-hk/SKILL.md`; `alx review start rewild --iter`
- **remove:** `alx snapshot --restore`
- **example:** Mainland wording in zh-HK report.

### `rewild/ai-vocabulary` — A
- **rule:** AI-vocabulary above length-scaled threshold (quote-masked). Hard in checker; Class A for `--deliver`.
- **fix:** rewrite flagged spans; `alx review start rewild --iter`
- **remove:** `alx snapshot --restore`
- **example:** "delve" × N vs threshold.

### `rewild/style` — A
- **rule:** other style warnings.
- **fix:** edit or waive per `references/rewild-gate.md` (not Fidelity).
- **remove:** `alx snapshot --restore`
- **example:** parallel closers.

### `rewild/review-stale` — A
- **rule:** rewild review missing or stale (non-mechanical delta).
- **fix:** `alx review start rewild --iter` then `alx review finish rewild`
- **remove:** `alx review restore rewild` (reverts report.md)
- **example:** sentence changed after finish.

### `rewild/humanization-none` — A
- **rule:** `issue` created snapshot identical to report; `humanization: none`.
- **fix:** humanize then `alx snapshot --iter`
- **remove:** proceed with `--deliver` (recorded).
- **example:** issue with no prior snapshot.

## Reviews / content (`check` f)

### `review/content-missing` — F
- **rule:** content review note missing.
- **fix:** `alx review start content`
- **remove:** `alx review restore content`
- **example:** no `reviews/content.json`.

### `review/content-stale` — F
- **rule:** content review stale (non-mechanical report/ledger change).
- **fix:** `alx review start content --iter`
- **remove:** `alx review restore content`
- **example:** claim field edited after finish.

## Report / tooling (`check` a,c / render)

### `length-below-floor` — A
- **rule:** below hard floor (en 7500 words; zh 5000 non-ws chars). Threshold + actual in message.
- **fix:** deepen evidence; do not pad.
- **remove:** `alx claim drop` unused claims only — does not restore length.
- **example:** 4200 chars vs 5000.

### `sources-section` — A
- **rule:** Sources H2 not last or ≠ cited set; H1/standfirst/date-line format. `--fix` already ran or cannot repair (extra heading, two Sources blocks).
- **fix:** delete the extra Sources H2; put one Sources H2 last; rewrite the date line to equal `ledger.report_date`
- **remove:** n/a
- **example:** extra Sources heading mid-report.

### `tooling/receipt` — A
- **rule:** receipt tooling error; receipt never fabricated.
- **fix:** rerun `alx issue`
- **remove:** n/a
- **example:** write failed on `receipts/rewild.json`.

### `tooling/renderer` — A
- **rule:** md_to_pdf timeout/backend fail (90 s).
- **fix:** `alx render` (fallback chain).
- **remove:** n/a
- **example:** pdfkit missing; pdfium used.

### `tooling/rasterizer` — A
- **rule:** render_pdf_pages timeout/backend fail (90 s). pdfkit → pdfium → poppler.
- **fix:** `alx render`
- **remove:** n/a
- **example:** poppler timeout.
