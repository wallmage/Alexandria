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

For Chinese reports, verify that one intended CJK family is installed before rendering:

- Simplified Chinese: Noto Sans CJK SC, PingFang SC, Hiragino Sans GB, or Microsoft YaHei.
- Hong Kong Traditional Chinese: Noto Sans CJK HK, PingFang HK, Hiragino Sans, or Microsoft JhengHei.

On Debian/Ubuntu CI, install `fonts-noto-cjk`. A PDF that extracts the right Unicode text can still display missing-glyph boxes, so this does not replace visual inspection.

## Render

Read `references/pdf-templates.md` and resolve the intake values before rendering. Set `REPORT_TEMPLATE` to `executive`, `spectrum`, `atlas`, `horizon`, `maison`, `blueprint`, `terrain`, or `orbit`; use `auto` only when deterministic topic adaptation is intended.

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/md_to_pdf.py" \
  "$REPORT_MD" "$REPORT_PDF" --lang "$REPORT_LANG" \
  --template "$REPORT_TEMPLATE" --prepared-by "$PREPARED_BY" \
  --rewild-receipt "$REWILD_RECEIPT"
```

Use `--lang en`, `--lang zh-CN`, or `--lang zh-HK` when automatic script detection is ambiguous. Use `--keep-html` only when debugging layout. The converter refuses to replace an existing PDF; prefer a versioned filename, or pass `--force` only when replacement is intentional.

Optional metadata and imagery:

- `--client "$CLIENT_NAME"`: show a client field only when the value is non-empty.
- `--confidential`: add “Strictly Confidential” and controlled-copy footer wording. Omit the flag when confidentiality is Off.
- `--date "$REPORT_DATE"`: override the Markdown metadata date and today's fallback.
- `--cover-image "$COVER_IMAGE"`: use a verified local raster image inside the report directory when the selected visual system benefits from subject-specific imagery, especially Maison, Atlas, Horizon, or Terrain.

When the user did not choose a template, render Executive first, then render the non-Executive result from `select_adaptive_companion()` in `scripts/pdf_templates.py` to a second filename. Both PDFs must use the same Markdown, evidence, and Rewild receipt.

The contents page includes only the report structure: section titles, short section descriptions, and page numbers. Do not add document-control or engagement panels.

Relative raster-image paths resolve from the Markdown file's directory. Remote images, SVG, active HTML, local-file traversal, and network resource fetches are blocked.

## Validate

Run the ledger validator first, then cross-check the report and PDF:

```bash
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_ledger.py" "$LEDGER_JSON"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/validate_report.py" \
  "$REPORT_MD" --ledger "$LEDGER_JSON" \
  --rewild-receipt "$REWILD_RECEIPT" --pdf "$REPORT_PDF" \
  --expected-lang "$REPORT_LANG" \
  --min-sources 1 --min-sections 3 \
  --min-pages 10 --min-text-chars 5000 --min-links 1
```

Set `REPORT_LANG` to `en`, `zh-CN`, or `zh-HK`. Also enforce `--min-words 7500 --max-words 15000` for English, or `--min-chars 5000 --max-chars 10000` for Simplified or Traditional Chinese.

## Visual inspection

Create a new task-owned temporary directory, render every page with the bundled cross-platform rasterizer, and inspect every PNG or a complete contact sheet:

```bash
PDF_CHECK_DIR="$(mktemp -d)"
"$ALEXANDRIA_PYTHON" "$SKILL_ROOT/scripts/render_pdf_pages.py" \
  "$REPORT_PDF" "$PDF_CHECK_DIR" --dpi 144
```

Look for:

- missing glyphs or incorrect Simplified/Traditional Chinese;
- clipped text, images, tables, or code;
- blank or nearly blank pages;
- broken contents links or page numbers;
- long URLs extending past the page;
- stranded headings;
- unreadably small tables;
- incorrect cover title, date, header, or footer.

Delete only the exact task-owned environment and inspection directories after delivery.
