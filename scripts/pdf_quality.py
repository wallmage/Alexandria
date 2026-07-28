#!/usr/bin/env python3
"""Programmatic quality gates for Alexandria PDFs and template colour tokens.

Two independent families of checks live here:

* Pure-data checks over ``pdf_templates.TEMPLATES`` and the CSS token table.
  These need no render and run in milliseconds, so they are safe to call from
  ``validate_report.py`` on every report.
* Render-derived checks over a produced PDF: per-page ink coverage, the gap
  between the running-header baseline and the first body baseline, and content
  that escapes the page box.

The module is importable; ``run_quality_checks`` is the single entry point.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from .pdf_templates import TEMPLATES, css_color_tokens
except ImportError:
    from pdf_templates import TEMPLATES, css_color_tokens

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0

# --- Layout contract shared with pdf_templates.COMMON_CSS @page rules --------
PAGE_MARGIN_TOP_MM = 26.0
PAGE_MARGIN_BOTTOM_MM = 19.0
PAGE_MARGIN_SIDE_MM = 18.0

# Minimum vertical air between the running-header baseline box and the first
# body line on a continuation page. Below this the header reads as body text.
MIN_HEADER_GAP_MM = 6.0

# A non-cover page must put this much ink inside the content box. Calibrated
# against the near-blank Blueprint opener overflow (0.40%) and the sparsest
# legitimate page in the corpus, a three-entry bibliography tail (0.86%).
MIN_INK_RATIO = 0.006
# ...and carry at least this many characters of text. This is the metric that
# actually separates a shipped blank page (51-139 chars) from a legitimate
# short section tail (305-350 chars). The final page is exempt.
MIN_PAGE_CHARS = 220
# Feature openers are intentionally concise but occupy most of the printable
# height. A low-text page is exempt only when it immediately follows the final
# Contents page and clears this rendered fill threshold.
MIN_EDITORIAL_OPENER_FILL_RATIO = 0.50
# Vertical fill below this is reported as a warning, not an error: a section
# that ends near the top of a page is normal, a page that is empty is not.
MIN_FILL_RATIO = 0.32

INK_THRESHOLD = 200


def mm_to_pt(value):
    return value / MM_PER_INCH * PT_PER_INCH


def pt_to_mm(value):
    return value / PT_PER_INCH * MM_PER_INCH


# --------------------------------------------------------------------------
# Colour maths (WCAG 2.1)
# --------------------------------------------------------------------------


def parse_hex(value):
    """Return (r, g, b) in 0-255 for a #rgb or #rrggbb string."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"Not a hex colour: {value!r}")
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"Not a hex colour: {value!r}") from exc


def to_hex(rgb):
    channels = (max(0, min(255, round(c))) for c in rgb)
    return "#{:02x}{:02x}{:02x}".format(*channels)


def relative_luminance(color):
    """WCAG relative luminance for a hex string or an (r, g, b) triple."""
    rgb = parse_hex(color) if isinstance(color, str) else color
    channels = []
    for raw in rgb:
        srgb = raw / 255.0
        channels.append(
            srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground, background):
    """WCAG contrast ratio between two colours (always >= 1.0)."""
    lum_a = relative_luminance(foreground)
    lum_b = relative_luminance(background)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def _mix(color, target, amount):
    src = parse_hex(color) if isinstance(color, str) else color
    dst = parse_hex(target) if isinstance(target, str) else target
    return tuple(s + (d - s) * amount for s, d in zip(src, dst, strict=True))


def adjust_to_contrast(color, background, target_ratio, *, toward=None):
    """Darken (or lighten) ``color`` until it clears ``target_ratio``.

    Deterministic: walks a 0-1 mix toward black or white in 1/256 steps and
    returns the first hex value that satisfies the ratio. Returns the fully
    mixed endpoint when the target is unreachable.
    """
    if toward is None:
        toward = "#000000" if relative_luminance(background) > 0.18 else "#ffffff"
    if contrast_ratio(color, background) >= target_ratio:
        return to_hex(parse_hex(color) if isinstance(color, str) else color)
    for step in range(1, 257):
        candidate = to_hex(_mix(color, toward, step / 256.0))
        if contrast_ratio(candidate, background) >= target_ratio:
            return candidate
    return to_hex(parse_hex(toward) if isinstance(toward, str) else toward)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str  # "error" | "warning"
    message: str
    where: str = ""

    def format(self):
        location = f" [{self.where}]" if self.where else ""
        return f"{self.severity.upper()} {self.check}{location}: {self.message}"


@dataclass
class QualityReport:
    findings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self):
        return not self.errors

    def to_dict(self):
        return {
            "ok": self.ok,
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "message": f.message,
                    "where": f.where,
                }
                for f in self.findings
            ],
            "metrics": self.metrics,
        }

    def format_lines(self):
        return [f.format() for f in self.findings]


# --------------------------------------------------------------------------
# Token contrast checks (no render required)
# --------------------------------------------------------------------------

# Each rule: (label, foreground token, background token, minimum ratio).
# "large" covers >=14pt bold / >=18pt text; uppercase micro-labels are held to
# 4.5 anyway because they are small, not large.
CONTRAST_RULES = (
    ("body text on page", "__TEXT__", "#ffffff", 4.5),
    ("body text on pale panel", "__TEXT__", "__PALE__", 4.5),
    ("body link on page", "__LINK__", "#ffffff", 4.5),
    ("body link on pale panel", "__LINK__", "__PALE__", 4.5),
    ("citation marker on page", "__ACCENT_TEXT__", "#ffffff", 4.5),
    ("heading on page", "__DARK__", "#ffffff", 4.5),
    ("muted text on page", "__MUTED__", "#ffffff", 4.5),
    ("insight panel body", "#ffffff", "__DARK__", 4.5),
    ("insight panel label", "__INSIGHT_ACCENT__", "__DARK__", 4.5),
    ("insight panel link", "__LINK_ON_DARK__", "__DARK__", 4.5),
    ("takeaway band body", "__ON_ACCENT__", "__TAKEAWAY__", 4.5),
    ("takeaway band label", "__TAKEAWAY_ACCENT__", "__TAKEAWAY__", 4.5),
    ("table header text", "#ffffff", "__DARK__", 4.5),
)


def _token_values(template):
    return css_color_tokens(template)


def template_contrast_table(template):
    """Return [(label, fg_hex, bg_hex, ratio, minimum, passed)] for a template."""
    tokens = _token_values(template)
    rows = []
    for label, fg_token, bg_token, minimum in CONTRAST_RULES:
        foreground = tokens.get(fg_token, fg_token)
        background = tokens.get(bg_token, bg_token)
        ratio = contrast_ratio(foreground, background)
        rows.append(
            (label, foreground, background, ratio, minimum, ratio >= minimum - 1e-9)
        )
    return rows


def check_template_contrast(templates=None):
    """Assert WCAG AA over the colour-token table for every template."""
    names = list(templates) if templates else list(TEMPLATES)
    findings = []
    metrics = {}
    for name in names:
        rows = template_contrast_table(name)
        metrics[name] = {
            label: round(ratio, 2) for label, _, _, ratio, _, _ in rows
        }
        for label, foreground, background, ratio, minimum, passed in rows:
            if not passed:
                findings.append(
                    Finding(
                        check="contrast",
                        severity="error",
                        message=(
                            f"{label}: {foreground} on {background} is "
                            f"{ratio:.2f}:1, needs {minimum}:1"
                        ),
                        where=name,
                    )
                )
    return findings, metrics


# --------------------------------------------------------------------------
# Render-derived checks
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Embedded-font checks (CJK script purity)
# --------------------------------------------------------------------------

SIMPLIFIED_MARKERS = frozenset({"sc", "gb", "hans", "simplified", "yahei", "simsun"})
TRADITIONAL_MARKERS = frozenset(
    {"tc", "hk", "tw", "mo", "hant", "big5", "traditional", "jhenghei", "mingliu"}
)
# Substrings that mark a face as CJK at all. Anything else is Latin and is
# irrelevant to script purity.
CJK_FAMILY_MARKERS = (
    "pingfang", "songti", "heiti", "hiragino", "yahei", "jhenghei", "mingliu",
    "notosanscjk", "notoserifcjk", "sourcehan", "droidsansfallback",
    "alexandriacjk", "stsong", "stheiti", "simsun", "kaiti", "fangsong",
)

_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+")


def _font_tokens(name):
    """Split a PDF BaseFont name into comparable tokens.

    Handles both ``Songti-SC-Bold`` and camel-run names such as
    ``NotoSansCJKsc`` and ``SourceHanSansHK``.
    """
    text = str(name)
    if "+" in text:
        text = text.split("+", 1)[1]
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def classify_font_script(name):
    """Return 'simplified', 'traditional', 'latin' or 'unknown' for a font."""
    tokens = _font_tokens(name)
    compact = "".join(tokens)
    if not any(marker in compact for marker in CJK_FAMILY_MARKERS):
        return "latin"
    token_set = set(tokens)
    traditional = bool(token_set & TRADITIONAL_MARKERS) or any(
        marker in compact
        for marker in (
            "jhenghei", "mingliu", "big5", "hant",
            "cjktc", "cjkhk", "cjktw", "cjkhant",
        )
    )
    simplified = bool(token_set & SIMPLIFIED_MARKERS) or any(
        marker in compact
        for marker in ("yahei", "simsun", "cjksc", "cjkhans")
    )
    if traditional and not simplified:
        return "traditional"
    if simplified and not traditional:
        return "simplified"
    return "unknown"


def embedded_font_names(pdf_path):
    """Every embedded font BaseFont name in a PDF, deduplicated and sorted."""
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    names = set()
    for page in reader.pages:
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for key in fonts:
            font = fonts[key].get_object()
            if font.get("/BaseFont"):
                names.add(str(font["/BaseFont"]))
            for descendant in font.get("/DescendantFonts") or []:
                child = descendant.get_object()
                if child.get("/BaseFont"):
                    names.add(str(child["/BaseFont"]))
    return sorted(names)


def check_cjk_fonts(pdf_path, lang):
    """Fail loudly when a Chinese render mixes Simplified and Traditional.

    Alexandria does not vendor a CJK face by default (see
    references/pdf-production.md), so zh output uses the host's fonts. That is
    tolerable only if the result is script-pure and single-sourced; silently
    setting a Hong Kong document in a mix of PingFang HK, Songti TC and
    Songti SC-Bold is not.
    """
    if not str(lang).startswith("zh"):
        return [], {}
    expected = "traditional" if lang == "zh-HK" else "simplified"
    names = embedded_font_names(pdf_path)
    by_script = {}
    for name in names:
        by_script.setdefault(classify_font_script(name), []).append(name)
    findings = []
    scripts = {key for key in by_script if key in {"simplified", "traditional"}}
    if len(scripts) > 1:
        findings.append(
            Finding(
                check="cjk_fonts",
                severity="error",
                message=(
                    "render mixes Simplified and Traditional faces: "
                    + ", ".join(
                        sorted(by_script.get("simplified", []))
                        + sorted(by_script.get("traditional", []))
                    )
                ),
                where=lang,
            )
        )
    elif scripts and expected not in scripts:
        findings.append(
            Finding(
                check="cjk_fonts",
                severity="error",
                message=(
                    f"{lang} render is set in {sorted(scripts)[0]} faces: "
                    + ", ".join(sorted(by_script[sorted(scripts)[0]]))
                ),
                where=lang,
            )
        )
    elif not scripts and not by_script.get("unknown"):
        findings.append(
            Finding(
                check="cjk_fonts",
                severity="error",
                message="render embeds no CJK face at all",
                where=lang,
            )
        )
    for name in by_script.get("unknown", []):
        findings.append(
            Finding(
                check="cjk_fonts",
                severity="warning",
                message=f"cannot classify the script of embedded face {name}",
                where=lang,
            )
        )
    return findings, {"fonts": names, "by_script": by_script}


def _load_pdfium():
    try:
        import pypdfium2 as pdfium
    except (ImportError, OSError) as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "PDF quality checks need pypdfium2. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ) from exc
    return pdfium


def _load_pil():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "PDF quality checks need Pillow. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ) from exc


def _content_box_px(image_size, page_size):
    width_px, height_px = image_size
    width_pt, height_pt = page_size
    scale_x = width_px / width_pt
    scale_y = height_px / height_pt
    left = int(mm_to_pt(PAGE_MARGIN_SIDE_MM) * scale_x)
    right = int(width_px - mm_to_pt(PAGE_MARGIN_SIDE_MM) * scale_x)
    top = int(mm_to_pt(PAGE_MARGIN_TOP_MM) * scale_y)
    bottom = int(height_px - mm_to_pt(PAGE_MARGIN_BOTTOM_MM) * scale_y)
    return left, top, right, bottom


def _row_ink(gray_image):
    """Return (ink_ratio, first_inked_row, last_inked_row) for a mask image."""
    width, height = gray_image.size
    mask = gray_image.point(lambda value: 255 if value < INK_THRESHOLD else 0)
    data = mask.tobytes()
    total = 0
    first_row = None
    last_row = None
    for row in range(height):
        start = row * width
        chunk = data[start : start + width]
        count = width - chunk.count(0)
        if count:
            total += count
            if first_row is None:
                first_row = row
            last_row = row
    if not total:
        return 0.0, None, None
    return total / float(width * height), first_row, last_row


def page_ink_metrics(page):
    """Ink ratio and vertical fill for one page's content box."""
    _load_pil()
    page_size = page.get_size()
    bitmap = page.render(scale=1.0, draw_annots=False)
    try:
        image = bitmap.to_pil().convert("L")
    finally:
        bitmap.close()
    try:
        box = _content_box_px(image.size, page_size)
        cropped = image.crop(box)
        try:
            ratio, first_row, last_row = _row_ink(cropped)
            height_px = max(1, box[3] - box[1])
            scale_y = image.size[1] / page_size[1]
            fill = 0.0 if first_row is None else (last_row - first_row + 1) / height_px
            trailing_mm = (
                pt_to_mm((height_px - (last_row or 0) - 1) / scale_y)
                if last_row is not None
                else pt_to_mm(height_px / scale_y)
            )
            return {
                "ink_ratio": ratio,
                "fill_ratio": fill,
                "trailing_blank_mm": trailing_mm,
            }
        finally:
            cropped.close()
    finally:
        image.close()


#: Contents-page headings in every language the skill renders.
_CONTENTS_HEADINGS = ("contents", "目录", "目錄")


def _is_contents_page(page, rects=None):
    """True for the table-of-contents page.

    Its length is set by how many sections the report has, so a short report
    legitimately produces a short contents page. Detected from the rendered
    text rather than the page number, because the cover can be suppressed.
    """
    try:
        textpage = page.get_textpage()
        try:
            text = textpage.get_text_bounded().strip().casefold()
        finally:
            textpage.close()
    except Exception:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return any(
        line == heading or line.startswith(heading + " /")
        for line in lines
        for heading in _CONTENTS_HEADINGS
    )


def _is_editorial_opener(
    *,
    previous_is_contents,
    is_contents,
    metrics,
    min_ink_ratio,
):
    """Recognize the designed first content page from rendered evidence."""
    return (
        previous_is_contents
        and not is_contents
        and metrics["ink_ratio"] >= min_ink_ratio
        and metrics["fill_ratio"] >= MIN_EDITORIAL_OPENER_FILL_RATIO
    )


def page_text_characters(page, rects=None):
    """Characters of real body text inside the content box."""
    page_height = page.get_size()[1]
    textpage = page.get_textpage()
    try:
        rects = (
            [textpage.get_rect(i) for i in range(textpage.count_rects())]
            if rects is None
            else rects
        )
        total = 0
        for rect in rects:
            if rect[3] > page_height - mm_to_pt(PAGE_MARGIN_TOP_MM):
                continue
            if rect[1] < mm_to_pt(PAGE_MARGIN_BOTTOM_MM):
                continue
            total += len(textpage.get_text_bounded(*rect))
        return total
    finally:
        textpage.close()


def page_text_rects(page):
    textpage = page.get_textpage()
    try:
        return [textpage.get_rect(i) for i in range(textpage.count_rects())]
    finally:
        textpage.close()


def header_gap_mm(page, rects=None):
    """Vertical air between the running header and the first body line.

    Returns ``None`` when the page has no running header (cover pages) or no
    body text at all.
    """
    page_height = page.get_size()[1]
    rects = page_text_rects(page) if rects is None else rects
    if len(rects) < 2:
        return None
    header_zone = page_height - mm_to_pt(PAGE_MARGIN_TOP_MM)
    header = [r for r in rects if r[3] > header_zone]
    body = [r for r in rects if r[3] <= header_zone]
    if not header or not body:
        return None
    header_bottom = min(r[1] for r in header)
    body_top = max(r[3] for r in body)
    return pt_to_mm(header_bottom - body_top)


def overflow_findings(page, index, rects=None):
    """Text that sits outside the printable page box or bleeds off the edge."""
    width, height = page.get_size()
    rects = page_text_rects(page) if rects is None else rects
    findings = []
    tolerance = 1.0
    for left, bottom, right, top in rects:
        if (
            left < -tolerance
            or bottom < -tolerance
            or right > width + tolerance
            or top > height + tolerance
        ):
            findings.append(
                Finding(
                    check="overflow",
                    severity="error",
                    message=(
                        "text box escapes the page: "
                        f"({left:.1f}, {bottom:.1f}, {right:.1f}, {top:.1f}) "
                        f"outside 0..{width:.1f} x 0..{height:.1f}"
                    ),
                    where=f"page {index}",
                )
            )
    return findings


def check_pdf(
    pdf_path,
    *,
    min_ink_ratio=MIN_INK_RATIO,
    min_page_chars=MIN_PAGE_CHARS,
    min_fill_ratio=MIN_FILL_RATIO,
    min_header_gap_mm=MIN_HEADER_GAP_MM,
    skip_pages=(1,),
):
    """Run every render-derived check over ``pdf_path``."""
    pdfium = _load_pdfium()
    path = Path(pdf_path)
    if not path.is_file():
        raise ValueError(f"PDF file not found: {path}")
    findings = []
    pages = []
    document = pdfium.PdfDocument(path)
    try:
        total = len(document)
        previous_is_contents = False
        for index in range(total):
            number = index + 1
            page = document[index]
            try:
                rects = page_text_rects(page)
                metrics = page_ink_metrics(page)
                gap = header_gap_mm(page, rects)
                metrics["header_gap_mm"] = gap
                metrics["text_chars"] = page_text_characters(page, rects)
                metrics["page"] = number
                pages.append(metrics)
                findings.extend(overflow_findings(page, number, rects))
                is_contents = _is_contents_page(page, rects)
                if number in skip_pages:
                    previous_is_contents = is_contents
                    continue
                if gap is not None and gap < min_header_gap_mm:
                    findings.append(
                        Finding(
                            check="header_gap",
                            severity="error",
                            message=(
                                f"running header sits {gap:.1f}mm above the first "
                                f"body line, needs {min_header_gap_mm:.1f}mm"
                            ),
                            where=f"page {number}",
                        )
                    )
                # A page is allowed to end short when its length is set by the
                # document's structure rather than by a layout fault: the
                # contents page is as long as the report has sections, and the
                # bibliography stops when the sources run out. The defect this
                # check exists to catch is a mid-document continuation page
                # carrying a few orphaned lines above an empty sheet, so those
                # two structural cases are exempt and everything else is not.
                is_last = number == total
                is_structural = is_last or is_contents
                is_editorial_opener = _is_editorial_opener(
                    previous_is_contents=previous_is_contents,
                    is_contents=is_contents,
                    metrics=metrics,
                    min_ink_ratio=min_ink_ratio,
                )
                visually_sparse = metrics["ink_ratio"] < min_ink_ratio
                textually_sparse = metrics["text_chars"] < min_page_chars
                if not is_structural and visually_sparse:
                    findings.append(
                        Finding(
                            check="blank_page",
                            severity="error",
                            message=(
                                f"page carries {metrics['ink_ratio'] * 100:.2f}% "
                                "ink inside the content box, needs "
                                f"{min_ink_ratio * 100:.2f}%"
                            ),
                            where=f"page {number}",
                        )
                    )
                elif (
                    not is_structural
                    and not is_editorial_opener
                    and textually_sparse
                ):
                    findings.append(
                        Finding(
                            check="blank_page",
                            severity="error",
                            message=(
                                f"page carries only {metrics['text_chars']} "
                                f"characters ({metrics['trailing_blank_mm']:.0f}mm "
                                f"blank below), needs {min_page_chars}"
                            ),
                            where=f"page {number}",
                        )
                    )
                elif not is_structural and metrics["fill_ratio"] < min_fill_ratio:
                    findings.append(
                        Finding(
                            check="sparse_page",
                            severity="warning",
                            message=(
                                "content stops after "
                                f"{metrics['fill_ratio'] * 100:.0f}% of the text "
                                f"block ({metrics['trailing_blank_mm']:.0f}mm blank "
                                "below), needs "
                                f"{min_fill_ratio * 100:.0f}%"
                            ),
                            where=f"page {number}",
                        )
                    )
                previous_is_contents = is_contents
            finally:
                page.close()
    finally:
        document.close()
    metrics = {
        "page_count": len(pages),
        "pages": pages,
        "mean_trailing_blank_mm": (
            round(
                sum(p["trailing_blank_mm"] for p in pages[1:-1]) / max(1, len(pages) - 2),
                2,
            )
            if len(pages) > 2
            else 0.0
        ),
        "min_header_gap_mm": round(
            min(
                (p["header_gap_mm"] for p in pages if p["header_gap_mm"] is not None),
                default=0.0,
            ),
            2,
        ),
    }
    return findings, metrics


def run_quality_checks(
    pdf_path=None, *, lang=None, templates=None, check_tokens=True
):
    """Single entry point. Returns a :class:`QualityReport`.

    ``pdf_path`` may be ``None`` to run only the pure-data token checks;
    ``lang`` enables the CJK script-purity check for zh output.
    """
    report = QualityReport()
    if check_tokens:
        findings, metrics = check_template_contrast(templates)
        report.findings.extend(findings)
        report.metrics["contrast"] = metrics
    if pdf_path is not None:
        findings, metrics = check_pdf(pdf_path)
        report.findings.extend(findings)
        report.metrics["pdf"] = metrics
        if lang:
            findings, metrics = check_cjk_fonts(pdf_path, lang)
            report.findings.extend(findings)
            if metrics:
                report.metrics["fonts"] = metrics
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Alexandria PDF and design-token quality gate"
    )
    parser.add_argument("pdf", nargs="?", default=None, help="Rendered PDF to inspect")
    parser.add_argument(
        "--skip-tokens",
        action="store_true",
        help="Skip the colour-token contrast checks",
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="Document language; enables the CJK script-purity check",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report")
    args = parser.parse_args(argv)
    try:
        report = run_quality_checks(
            args.pdf, lang=args.lang, check_tokens=not args.skip_tokens
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for line in report.format_lines():
            print(line)
        print("[OK] PDF quality checks passed" if report.ok else "[FAIL] quality gate")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
