# PDF production

## Resolve paths

Set `SKILL_ROOT` to the absolute directory containing Alexandria's `SKILL.md`. Keep report files in the user's chosen output directory. Create the dependency environment and inspection images in task-owned temporary or cache directories outside the user's project.

Never rely on the current working directory. Pass paths as argument-array values where possible; otherwise quote every shell path and variable.

## Environment

Create an isolated environment. On POSIX:

```bash
ALEXANDRIA_ENV="$(mktemp -d)/venv"
python3 -m venv "$ALEXANDRIA_ENV"
ALEXANDRIA_PYTHON="$ALEXANDRIA_ENV/bin/python"
"$ALEXANDRIA_PYTHON" -m pip install -r "$SKILL_ROOT/requirements.txt"
```

On Windows, use a task-owned temporary directory and set `ALEXANDRIA_PYTHON` to `Scripts/python.exe`.

WeasyPrint may need platform libraries. Follow its official installation guide if the dependency check reports an unusable installation.

## Chinese fonts

Alexandria bundles Source Sans 3, Source Serif 4, and Source Code Pro, and embeds and subsets them on every render. It does **not** bundle a CJK face by default, and that is a deliberate, documented limitation rather than an oversight:

- The obvious candidates it could legally redistribute are Noto Sans CJK and Noto Serif CJK (OFL). A Simplified + Traditional pair in both sans and serif is roughly 40-80MB, which is one to two orders of magnitude larger than the entire rest of the skill. A range subset does not solve it either: report text is open-vocabulary, so any subset narrow enough to be small will drop characters from some future report, and it would drop them silently.
- The faces actually installed on most authoring machines - PingFang, Songti, Hiragino - are proprietary and cannot be redistributed.

So zh output uses the host's fonts, and the pipeline makes that safe instead of pretending otherwise:

1. **Script-pure stacks.** `scripts/md_to_pdf.py` defines one font stack per locale containing only Simplified faces for `zh-CN` and only Traditional faces for `zh-HK`. Japanese faces and `Droid Sans Fallback` were removed, and no stack ends in a generic `serif` / `sans-serif` / `monospace` keyword, because fontconfig answered those generics with whichever Songti it felt like. That is how a Hong Kong document previously ended up set in PingFang HK, Songti TC, *and* Songti SC-Bold at once.
2. **An enforced check.** `scripts/pdf_quality.check_cjk_fonts(pdf, lang)` reads the embedded font list back out of the finished PDF, classifies every face as Simplified, Traditional, or Latin, and **fails** if the render mixes scripts, uses the wrong script for the locale, or embeds no CJK face at all. Silent SC/TC mixing is no longer possible; the build stops.
3. **An opt-in bundle.** Drop `AlexandriaCJK-SC.ttf` and/or `AlexandriaCJK-TC.ttf` into `assets/fonts/` and `BUNDLED_FONT_CSS` picks them up automatically and pins them at the head of every zh stack. With those files present, `zh-CN` and `zh-HK` render identically on every machine and pagination stops being host-dependent.

Without the optional bundle, pagination remains host-dependent, so a `--min-pages` threshold can pass on one machine and fail on another. Verify the intended family is installed before rendering:

- Simplified Chinese: Noto Sans CJK SC, Source Han Sans SC, PingFang SC, or Microsoft YaHei.
- Hong Kong Traditional Chinese: Noto Sans CJK HK/TC, Source Han Sans HK, PingFang HK, or Microsoft JhengHei.

On Debian/Ubuntu CI, install `fonts-noto-cjk`. A PDF that extracts the right Unicode text can still display missing-glyph boxes, so this does not replace visual inspection.

## Render

Read `references/pdf-templates.md` and resolve the intake values before rendering. The available systems are Executive, Spectrum, Atlas, Horizon, Maison, Blueprint, Terrain, Orbit, Sunbeam, Current, and Apricot. Set `REPORT_TEMPLATE` to the matching lowercase identifier; use `auto` only when deterministic topic adaptation is intended.

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_ledger.py" "$LEDGER_JSON"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/source_fidelity.py" "$LEDGER_JSON" \
  --online --receipt "$SOURCE_FIDELITY_RECEIPT"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/content_gate.py" "$REPORT_MD" \
  --ledger "$LEDGER_JSON" --review-note "$CONTENT_REVIEW_NOTE" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --receipt "$CONTENT_RECEIPT"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/md_to_pdf.py" \
  "$REPORT_MD" "$REPORT_PDF" --lang "$REPORT_LANG" \
  --template "$REPORT_TEMPLATE" --prepared-by "$PREPARED_BY" \
  --ledger "$LEDGER_JSON" --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT"
```

Use `--lang en`, `--lang zh-CN`, or `--lang zh-HK` when automatic script detection is ambiguous. Use `--keep-html` only when debugging layout. The converter refuses to replace an existing PDF; prefer a versioned filename, or pass `--force` only when replacement is intentional.

Optional metadata and imagery:

- `--client "$CLIENT_NAME"`: show a client field only when the value is non-empty.
- `--confidential`: add “Strictly Confidential” and controlled-copy footer wording. Omit the flag when confidentiality is Off.
- `--date "$REPORT_DATE"`: override the Markdown metadata date and today's fallback.
- `--cover-image "$COVER_IMAGE"`: use a verified local raster image inside the report directory when the selected visual system benefits from subject-specific imagery, especially Maison, Atlas, Horizon, Terrain, Current, or Apricot.

Cover text cannot become a post-gate prose channel. A supplied `--title` or
`--subtitle` must exactly match visible text in the gated Markdown. Before
running the gates, put every non-default identity value in the immediate H1
metadata block as `> Client: Acme Research` or
`> Prepared by: Alice Smith`; the renderer accepts only that exact typed value.
The constant default preparer `Alexandria` needs no metadata line. Identity
fields use a short person/organization grammar and reject sentences, unsafe
punctuation, and harm language.

Every custom cover or Markdown body image must also have an `approved`
`visual_assets` record in the content review with its report-relative path,
exact SHA-256, `cover`/`body` usage, and visible text/claims assessment. The
renderer rejects unreviewed images, changed pixels, and approvals unused by the
actual sanitized HTML.

When the user did not choose a template, render Executive first, then render the non-Executive result from `select_adaptive_companion()` in `scripts/pdf_templates.py` to a second filename. Both PDFs must use the same Markdown, evidence, Rewild receipt, and content receipt.

The contents page includes only the report structure: section titles and page numbers. Truncated section teasers were removed - they read as filler and forced the contents onto a second, mostly empty sheet. Do not add document-control or engagement panels.

Relative raster-image paths resolve from the Markdown file's directory. Remote
images, SVG, active HTML, local-file traversal, and network resource fetches are
blocked. User-supplied cover images must also meet the converter's minimum
resolution floor.

## Validate

Reopen and cross-check the report and rendered PDF:

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" \
  "$REPORT_MD" --ledger "$LEDGER_JSON" \
  --rewild-receipt "$REWILD_RECEIPT" \
  --source-fidelity-receipt "$SOURCE_FIDELITY_RECEIPT" \
  --content-receipt "$CONTENT_RECEIPT" \
  --pdf "$REPORT_PDF" \
  --expected-lang "$REPORT_LANG" \
  --min-sources 1 --min-sections 3 \
  --min-pages 10 --min-text-chars 5000 --min-links 1
```

Set `REPORT_LANG` to `en`, `zh-CN`, or `zh-HK`. Also enforce `--min-words 7500 --max-words 15000` for English, or `--min-chars 5000 --max-chars 10000` for Simplified or Traditional Chinese.

The PDF check also requires title and author metadata, the declared document
language, tagged structure for assistive technology, navigation bookmarks,
consistent A4 pages, selectable text, and clickable source links. Rendering
revalidates the report, receipts, and reviewed local assets before writing the
PDF; validation then reopens the delivered file and checks its structure.

## Byte reproducibility

Two renders of identical Markdown now produce identical SHA-256 digests. Two things had to be pinned:

- **Tagged-structure IDs.** WeasyPrint 69 stamps every table `StructElem` with `pydyf.String(id(box))`, a CPython memory address, and repeats it in the `/Headers` arrays. `deterministic_struct_ids()` in `scripts/md_to_pdf.py` shadows the module-level `id` inside `weasyprint.pdf.tags` for the duration of one render and hands out a stable counter instead.
- **Font-subset timestamps.** fontTools writes the current time into `head.modified` of every subset. It honours `SOURCE_DATE_EPOCH`, so a build that has not pinned one gets Alexandria's fixed epoch.

Font *subsetting itself* is deterministic: every `/FontFile2` stream hashes identically run to run once the timestamp is pinned. The earlier claim that subsetting was the source of nondeterminism was wrong.

Set `SOURCE_DATE_EPOCH` yourself if you want the embedded font timestamps to match a specific build date; otherwise leave it unset and the renderer supplies one.

## Automated quality gate

The visual checklist below is necessary but was never sufficient: "blank or nearly blank pages" has been on it for months and a near-blank page still shipped, because nothing enforced it. `scripts/pdf_quality.py` now makes the mechanical half of the checklist executable.

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/pdf_quality.py" \
  "$REPORT_PDF" --lang "$REPORT_LANG"
```

It exits non-zero on any error-severity finding and reports:

| Check | Fails when |
|---|---|
| `contrast` | any colour token in any of the eleven templates falls below WCAG AA (4.5:1). Pure data - needs no PDF. |
| `blank_page` | a page carries under 0.6% ink inside the content box, or under 220 characters of text (the final page is exempt from the character floor). |
| `header_gap` | the running header sits closer than 6mm to the first body baseline. |
| `overflow` | any text box escapes the page box. |
| `cjk_fonts` | a zh render mixes Simplified and Traditional faces, or uses the wrong script for the locale. Needs `--lang`. |
| `sparse_page` | *(warning only)* a page's inked band covers under 32% of the text block. A section ending near the top of a page is normal. |

Import it instead of shelling out when you need the numbers:

```python
from scripts.pdf_quality import run_quality_checks

report = run_quality_checks(pdf_path, lang="zh-HK")
if not report.ok:
    raise SystemExit("\n".join(report.format_lines()))
```

`report.metrics` carries per-page ink ratio, fill ratio, trailing whitespace in millimetres, header gap, and character count, plus the full contrast table for every template.

## Visual inspection

Create a new task-owned temporary directory, render every page with the bundled cross-platform rasterizer, and inspect every PNG or a complete contact sheet:

```bash
PDF_CHECK_DIR="$(mktemp -d)"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/render_pdf_pages.py" \
  "$REPORT_PDF" "$PDF_CHECK_DIR" --dpi 144
```

Run `scripts/pdf_quality.py` first. It settles the mechanical questions - blank pages, header collisions, overflow, contrast, CJK script purity - so the human pass can spend its attention on the ones a machine cannot answer:

- missing glyphs, or Chinese that is the right script but the wrong register;
- clipped or awkwardly cropped images;
- broken contents links or page numbers;
- long URLs extending past the page;
- stranded headings and orphaned single lines;
- unreadably small or badly proportioned tables;
- incorrect cover title, date, header, or footer;
- whether the opener plate actually says something about *this* report.

Anything found here that a machine could have caught belongs in `scripts/pdf_quality.py` as a new check, with a test, before the next release.

Delete only the exact task-owned environment and inspection directories after delivery.
