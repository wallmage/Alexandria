#!/usr/bin/env python3
"""
Alexandria Report: Markdown -> PDF converter (WeasyPrint)
Usage: python3 md_to_pdf.py input.md output.pdf [--title "Title"] [--subtitle "Subtitle"]

Dependencies: install from requirements.txt
"""

import argparse
import html
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


LANG_CHOICES = ("auto", "en", "zh-CN", "zh-HK")
TRADITIONAL_MARKERS = set("這個為與報發後裡麼還說對時國學術據點體現關於會開")
SIMPLIFIED_MARKERS = set("这个为与报发后里么还说对时国学术据点体现关于会开")
SAFE_TAGS = {
    "a", "b", "blockquote", "br", "code", "del", "div", "em", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre",
    "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul",
}
SAFE_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "h5": {"id"},
    "h6": {"id"},
    "code": {"class"},
}
LOCAL_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SAFE_IMAGE_DATA_TYPES = ("data:image/png", "data:image/jpeg", "data:image/gif", "data:image/webp")
MAX_ASSET_BYTES = 25_000_000


class SafeHTMLParser(HTMLParser):
    """Keep Markdown's structural HTML while dropping active/embed markup."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in SAFE_TAGS:
            return
        allowed = SAFE_ATTRIBUTES.get(tag, set())
        safe_attrs = []
        for name, value in attrs:
            if name not in allowed or value is None:
                continue
            if tag == "a" and name == "href":
                parsed = urlparse(value)
                if not (value.startswith("#") or parsed.scheme in {"http", "https"}):
                    continue
            if tag == "img" and name == "src":
                parsed = urlparse(value)
                if parsed.scheme not in {"", "file", "data"}:
                    continue
            safe_attrs.append(f' {name}="{html.escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(safe_attrs)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in SAFE_TAGS and tag not in {"br", "hr", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")


def sanitize_html_fragment(value):
    parser = SafeHTMLParser()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)


def make_url_fetcher(asset_root, default_fetcher=None):
    """Allow only image assets contained by the Markdown directory."""
    asset_root = Path(asset_root).resolve()

    def secure_fetch(url):
        parsed = urlparse(url)
        if parsed.scheme == "data":
            media_type = url[5:].split(",", 1)[0].split(";", 1)[0].lower()
            allowed_media_types = {
                item.removeprefix("data:") for item in SAFE_IMAGE_DATA_TYPES
            }
            if media_type not in allowed_media_types:
                raise ValueError("Only PNG, JPEG, GIF, and WebP data URLs are allowed.")
            if len(url) > MAX_ASSET_BYTES * 2:
                raise ValueError("Embedded image exceeds the resource limit.")
            if default_fetcher is None:
                from weasyprint import default_url_fetcher as fetch
            else:
                fetch = default_fetcher
            return fetch(url)

        if parsed.scheme not in {"", "file"}:
            raise ValueError(f"Remote resource blocked during PDF rendering: {url}")

        raw_path = unquote(parsed.path if parsed.scheme == "file" else url)
        resource_path = Path(raw_path).resolve()
        if not resource_path.is_relative_to(asset_root):
            raise ValueError(f"Asset is outside the report directory: {resource_path}")
        if resource_path.suffix.lower() not in LOCAL_ASSET_SUFFIXES:
            raise ValueError(f"Unsupported local asset type: {resource_path.suffix}")
        if resource_path.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError(f"Asset exceeds the {MAX_ASSET_BYTES}-byte limit: {resource_path}")
        if default_fetcher is None:
            from weasyprint import default_url_fetcher as fetch
        else:
            fetch = default_fetcher
        return fetch(resource_path.as_uri())

    return secure_fetch


def detect_language(text):
    """Return a practical HTML language tag for English or Chinese text."""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_alpha = len(re.findall(r'[a-zA-Z]', text))
    if chinese_chars <= total_alpha * 0.3:
        return "en"

    traditional = sum(text.count(char) for char in TRADITIONAL_MARKERS)
    simplified = sum(text.count(char) for char in SIMPLIFIED_MARKERS)
    return "zh-HK" if traditional > simplified else "zh-CN"


def build_toc_html(html_body, lang="en"):
    """Extract H2/H3 headers from HTML and build a styled TOC page."""
    headers = re.findall(r'<(h[23])\s*id="([^"]*)"[^>]*>(.*?)</\1>', html_body)
    if not headers:
        # Fallback: headers without id attributes
        headers = re.findall(r'<(h[23])[^>]*>(.*?)</\1>', html_body)
        if not headers:
            return ""
        # Reformat to match (tag, id, text) structure
        headers = [(h[0], "", h[1]) for h in headers]

    toc_title = {"en": "Contents", "zh-CN": "目录", "zh-HK": "目錄"}[lang]
    items = []
    for tag, hid, text in headers:
        clean = html.unescape(re.sub(r'<[^>]+>', '', text)).strip()
        safe_text = html.escape(clean)
        indent = "toc-h3" if tag == "h3" else "toc-h2"
        if hid:
            safe_id = html.escape(hid, quote=True)
            items.append(f'<div class="{indent}"><a href="#{safe_id}">{safe_text}</a></div>')
        else:
            items.append(f'<div class="{indent}">{safe_text}</div>')

    return f"""
    <div class="toc-page">
        <h2 class="toc-title">{toc_title}</h2>
        {"".join(items)}
    </div>
    """


# Font stacks: platform-aware with CJK coverage
FONT_SANS_CN = (
    '"Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", '
    '"Microsoft YaHei", "Droid Sans Fallback", '
    '"Helvetica Neue", Helvetica, Arial, sans-serif'
)
FONT_SANS_HK = (
    '"Noto Sans CJK HK", "PingFang HK", "Hiragino Sans", '
    '"Microsoft JhengHei", "Droid Sans Fallback", '
    '"Helvetica Neue", Helvetica, Arial, sans-serif'
)
FONT_SANS_EN = '"Source Sans 3", "Helvetica Neue", Helvetica, Arial, sans-serif'
FONT_MONO = '"Menlo", "Consolas", "Courier New", Courier, monospace'


def escape_css_content(value):
    """Escape text for a double-quoted CSS content string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\\A ")
        .replace("\r", "\\A ")
        .replace("\n", "\\A ")
        .replace("\f", "\\C ")
        .replace("<", "\\3C ")
        .replace(">", "\\3E ")
    )

# -- CSS Template --
CSS_TEMPLATE = f"""
@page {{
    size: A4;
    margin: 25mm 20mm 20mm 20mm;

    @top-center {{
        content: "HEADER_TEXT";
        font-family: FONT_SANS;
        font-size: 8pt;
        color: #95a5a6;
        border-bottom: 0.5pt solid #ecf0f1;
        padding-bottom: 3mm;
    }}

    @bottom-center {{
        content: "PAGE_LABEL " counter(page) "PAGE_SUFFIX";
        font-family: FONT_SANS;
        font-size: 8pt;
        color: #95a5a6;
        border-top: 0.8pt solid #1a5276;
        padding-top: 2mm;
    }}
}}

@page :first {{
    @top-center {{ content: none; }}
    @bottom-center {{ content: none; }}
}}

@page toc {{
    @top-center {{ content: none; }}
    @bottom-center {{ content: none; }}
}}

body {{
    font-family: FONT_SANS;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #2c3e50;
    text-align: justify;
}}

/* Cover */
.cover {{
    page-break-after: always;
    text-align: center;
    padding-top: 45%;
}}
.cover h1 {{
    font-size: 28pt;
    color: #1a5276;
    margin-bottom: 8mm;
    font-weight: bold;
    letter-spacing: 2pt;
    border: none;
    page-break-before: avoid;
}}
.cover .subtitle {{
    font-size: 14pt;
    color: #95a5a6;
    margin-bottom: 6mm;
}}
.cover .meta {{
    font-size: 11pt;
    color: #95a5a6;
    margin-bottom: 4mm;
}}
.cover .divider {{
    width: 60%;
    margin: 8mm auto;
    border: none;
    border-top: 1.5pt solid #1a5276;
}}

/* Table of Contents */
.toc-page {{
    page: toc;
    page-break-after: always;
    padding-top: 10mm;
}}
.toc-title {{
    font-size: 18pt;
    color: #1a5276;
    margin-bottom: 8mm;
    padding-bottom: 3mm;
    border-bottom: 1.5pt solid #1a5276;
    page-break-before: avoid;
}}
.toc-h2 {{
    font-size: 11pt;
    margin: 2mm 0;
    padding: 1.5mm 0;
    border-bottom: 0.3pt dotted #bdc3c7;
}}
.toc-h2 a {{
    color: #1a5276;
    text-decoration: none;
    font-weight: bold;
}}
.toc-h2 a::after, .toc-h3 a::after {{
    content: target-counter(attr(href), page);
    float: right;
}}
.toc-h3 {{
    font-size: 10pt;
    margin: 1mm 0 1mm 8mm;
    padding: 1mm 0;
    color: #5d6d7e;
}}
.toc-h3 a {{
    color: #5d6d7e;
    text-decoration: none;
}}

/* H1 - chapter starts */
h1 {{
    font-size: 20pt;
    color: #1a5276;
    margin-top: 16mm;
    margin-bottom: 6mm;
    padding-bottom: 3mm;
    border-bottom: 2pt solid #1a5276;
    page-break-before: always;
    font-weight: bold;
}}

/* H2 */
h2 {{
    font-size: 14pt;
    color: #1e8449;
    margin-top: 10mm;
    margin-bottom: 5mm;
    font-weight: bold;
}}

/* H3 */
h3 {{
    font-size: 12pt;
    color: #2e86c1;
    margin-top: 6mm;
    margin-bottom: 3mm;
    font-weight: bold;
}}

h4 {{
    font-size: 11pt;
    color: #5b2c6f;
    margin-top: 5mm;
    margin-bottom: 2mm;
    font-weight: bold;
}}
h2, h3, h4 {{
    break-after: avoid;
}}

/* Paragraphs */
p {{
    margin-top: 1.5mm;
    margin-bottom: 1.5mm;
    orphans: 3;
    widows: 3;
}}

/* Blockquotes */
blockquote {{
    margin: 4mm 0;
    padding: 4mm 4mm 4mm 10mm;
    background: #f8f9fa;
    border-left: 3pt solid #1a5276;
    color: #5d6d7e;
    font-size: 10pt;
}}
blockquote p {{
    margin: 1mm 0;
}}

/* Bold */
strong, b {{
    font-weight: bold;
    color: #1a252f;
}}

/* Inline code */
code {{
    font-family: {FONT_MONO};
    background: #fdf2e9;
    color: #c0392b;
    padding: 0.5mm 1.5mm;
    border-radius: 2pt;
    font-size: 9.5pt;
}}
pre {{
    font-family: {FONT_MONO};
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    background: #f8f9fa;
    padding: 3mm;
    border: 0.5pt solid #dfe6e9;
    font-size: 8.5pt;
}}
pre code {{
    background: transparent;
    color: #2c3e50;
    padding: 0;
}}

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4mm 0;
    font-size: 9.5pt;
}}
thead {{
    display: table-header-group;
}}
thead th {{
    background: #1a5276;
    color: white;
    padding: 3mm;
    text-align: left;
    font-weight: bold;
}}
tbody td {{
    padding: 2.5mm 3mm;
    border-bottom: 0.5pt solid #bdc3c7;
}}
tbody tr:nth-child(even) {{
    background: #f8f9fa;
}}

/* Horizontal rules */
hr {{
    border: none;
    border-top: 0.5pt solid #bdc3c7;
    margin: 4mm 0;
}}

/* Lists */
ul, ol {{
    margin: 2mm 0;
    padding-left: 8mm;
}}
li {{
    margin-bottom: 1mm;
}}

/* Links */
a {{
    color: #2e86c1;
    text-decoration: none;
    overflow-wrap: anywhere;
}}
img {{
    display: block;
    max-width: 100%;
    height: auto;
    margin: 4mm auto;
}}
"""


def load_markdown():
    """Load Python-Markdown only when conversion is requested."""
    try:
        import markdown
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'Markdown'. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ) from exc
    return markdown


def load_weasyprint_html():
    """Load WeasyPrint only when PDF rendering is requested."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "Missing or unusable dependency 'WeasyPrint'. Install dependencies with "
            "'python3 -m pip install -r requirements.txt' and follow WeasyPrint's "
            "platform installation guide if native libraries are missing."
        ) from exc
    return HTML


def md_to_html(md_text, title=None, subtitle=None, lang="auto"):
    """Convert Markdown to HTML with cover page and TOC."""

    markdown = load_markdown()
    lang = detect_language(md_text) if lang == "auto" else lang

    # Defaults based on language
    localized = {
        "en": ("Alexandria Research Report", "Page", "", FONT_SANS_EN),
        "zh-CN": ("Alexandria 深度研究报告", "第", " 页", FONT_SANS_CN),
        "zh-HK": ("Alexandria 深度研究報告", "第", " 頁", FONT_SANS_HK),
    }
    default_title, page_label, page_suffix, font_sans = localized[lang]

    title = title or default_title
    subtitle = subtitle or ""

    # Convert markdown body (toc extension adds id attributes to headers)
    md_ext = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'toc'],
        extension_configs={'toc': {'toc_depth': '2-3'}},
        output_format='html5'
    )
    html_body = sanitize_html_fragment(md_ext.convert(md_text))

    # Extract first H1 for cover
    first_h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_body)
    if first_h1_match:
        extracted_title = html.unescape(re.sub(r'<[^>]+>', '', first_h1_match.group(1)).strip())
        if title == default_title:
            title = extracted_title
        html_body = html_body.replace(first_h1_match.group(0), '', 1)

    # Extract metadata line (the line after H1 starting with >)
    # This is typically just a date like "> April 2026" or "> 2026年4月"
    meta_line = ""
    found_h1 = False
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not found_h1:
            found_h1 = True
            continue
        if found_h1 and stripped.startswith(">"):
            meta_line = stripped.lstrip(">").strip()
            break
        if found_h1 and stripped:
            break  # Non-empty, non-blockquote line after H1 — no metadata

    # Remove the metadata blockquote from body to avoid duplication with cover
    if meta_line:
        # The markdown converter turns "> Date: ..." into <blockquote><p>Date: ...</p></blockquote>
        # Match against the HTML-encoded version since markdown encodes special chars
        meta_line_html = html.escape(meta_line)
        meta_bq_pattern = re.compile(
            r'<blockquote>\s*<p>' + re.escape(meta_line_html) + r'</p>\s*</blockquote>',
            re.DOTALL
        )
        html_body = meta_bq_pattern.sub('', html_body, count=1)

    # Build TOC from the converted HTML
    toc_html = build_toc_html(html_body, lang)

    # Build CSS with header/footer text (escape HTML entities for CSS content string)
    safe_title = escape_css_content(title)
    safe_subtitle = escape_css_content(subtitle)
    header_text = f"{safe_title}  |  {safe_subtitle}" if subtitle else safe_title
    css = CSS_TEMPLATE.replace("HEADER_TEXT", header_text)
    css = css.replace("PAGE_LABEL", page_label)
    css = css.replace("PAGE_SUFFIX", page_suffix)
    css = css.replace("FONT_SANS", font_sans)

    # Build cover (use HTML-escaped versions to prevent markup injection)
    cover_title = html.escape(title)
    cover_subtitle = html.escape(subtitle)
    cover_meta = html.escape(meta_line) if meta_line else ""
    cover_html = f"""
    <div class="cover">
        <h1>{cover_title}</h1>
        {"<div class='subtitle'>" + cover_subtitle + "</div>" if cover_subtitle else ""}
        {"<div class='meta'>" + cover_meta + "</div>" if cover_meta else ""}
        <hr class="divider">
    </div>
    """

    html_lang = lang

    full_html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
    <meta charset="UTF-8">
    <style>{css}</style>
</head>
<body>
{cover_html}
{toc_html}
{html_body}
</body>
</html>"""

    return full_html


def html_debug_path(output_path):
    """Return the optional HTML debug artifact beside the PDF."""
    return Path(output_path).with_suffix(".html")


def validate_paths(input_path, output_path, *, force=False):
    """Validate CLI paths before loading optional rendering dependencies."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise ValueError(f"Input Markdown file not found: {input_path}")
    if output_path.suffix.lower() != ".pdf":
        raise ValueError(f"Output path must end in .pdf: {output_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")
    if output_path.exists() and not force:
        raise ValueError(
            f"Output PDF already exists; use --force to replace it: {output_path}"
        )
    return input_path, output_path


def render_pdf(
    input_path,
    output_path,
    *,
    title=None,
    subtitle=None,
    lang="auto",
    keep_html=False,
    force=False,
):
    """Render one Markdown file and return the output PDF path."""
    input_path, output_path = validate_paths(input_path, output_path, force=force)
    md_text = input_path.read_text(encoding="utf-8")
    rendered_html = md_to_html(md_text, title=title, subtitle=subtitle, lang=lang)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if keep_html:
        debug_path = html_debug_path(output_path)
        try:
            with debug_path.open("x", encoding="utf-8") as debug_file:
                debug_file.write(rendered_html)
        except FileExistsError as exc:
            raise ValueError(
                f"HTML debug artifact already exists; refusing to overwrite: {debug_path}"
            ) from exc
        print(f"[OK] HTML generated: {debug_path}")

    HTML = load_weasyprint_html()
    temp_handle = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}-",
        suffix=".pdf",
        dir=output_path.parent,
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    try:
        HTML(
            string=rendered_html,
            base_url=input_path.parent.resolve(),
            url_fetcher=make_url_fetcher(input_path.parent),
        ).write_pdf(temp_path)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    size_kb = output_path.stat().st_size / 1024
    print(f"[OK] PDF generated: {output_path} ({size_kb:.1f} KB)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Alexandria Report: Markdown to PDF")
    parser.add_argument("input", help="Input Markdown file")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument("--title", default=None, help="Report title (auto-detected from H1 if omitted)")
    parser.add_argument("--subtitle", default=None, help="Report subtitle")
    parser.add_argument(
        "--lang",
        choices=LANG_CHOICES,
        default="auto",
        help="Document language and locale (default: auto)",
    )
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="Keep the intermediate HTML file beside the PDF",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output PDF",
    )
    args = parser.parse_args()

    try:
        render_pdf(
            args.input,
            args.output,
            title=args.title,
            subtitle=args.subtitle,
            lang=args.lang,
            keep_html=args.keep_html,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
