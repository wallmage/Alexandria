#!/usr/bin/env python3
"""
Alexandria Report: Markdown -> PDF converter (WeasyPrint)
Usage: python md_to_pdf.py input.md output.pdf [--title "Title"] [--subtitle "Subtitle"]

Dependencies: pip install weasyprint markdown --break-system-packages
"""

import sys
import os
import re
import html
import argparse
import markdown


def detect_language(text):
    """Detect if text is primarily Chinese or English."""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_alpha = len(re.findall(r'[a-zA-Z]', text))
    if chinese_chars > total_alpha * 0.3:
        return "zh"
    return "en"


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

    toc_title = "Contents" if lang == "en" else "\u76ee\u5f55"
    items = []
    for tag, hid, text in headers:
        clean = re.sub(r'<[^>]+>', '', text).strip()
        indent = "toc-h3" if tag == "h3" else "toc-h2"
        if hid:
            items.append(f'<div class="{indent}"><a href="#{hid}">{clean}</a></div>')
        else:
            items.append(f'<div class="{indent}">{clean}</div>')

    return f"""
    <div class="toc-page">
        <h2 class="toc-title">{toc_title}</h2>
        {"".join(items)}
    </div>
    """


# Font stacks: platform-aware with CJK coverage
FONT_SANS = (
    '"Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", '
    '"Microsoft YaHei", "Droid Sans Fallback", '
    '"Helvetica Neue", Helvetica, Arial, sans-serif'
)
FONT_MONO = '"Menlo", "Consolas", "Courier New", Courier, monospace'

# -- CSS Template --
CSS_TEMPLATE = f"""
@page {{
    size: A4;
    margin: 25mm 20mm 20mm 20mm;

    @top-center {{
        content: "HEADER_TEXT";
        font-family: {FONT_SANS};
        font-size: 8pt;
        color: #95a5a6;
        border-bottom: 0.5pt solid #ecf0f1;
        padding-bottom: 3mm;
    }}

    @bottom-center {{
        content: "PAGE_LABEL " counter(page) "PAGE_SUFFIX";
        font-family: {FONT_SANS};
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
    font-family: {FONT_SANS};
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

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4mm 0;
    font-size: 9.5pt;
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
}}
"""


def md_to_html(md_text, title=None, subtitle=None):
    """Convert Markdown to HTML with cover page and TOC."""

    lang = detect_language(md_text)

    # Defaults based on language
    default_title = "Alexandria Deep Research Report" if lang == "en" else "Alexandria \u6df1\u5ea6\u7814\u7a76\u62a5\u544a"
    default_subtitle = "Alexandria Deep Research Report" if lang == "en" else "Alexandria \u6df1\u5ea6\u7814\u7a76\u62a5\u544a"
    page_label = "Page " if lang == "en" else "\u7b2c "
    page_suffix = "" if lang == "en" else " \u9875"

    title = title or default_title
    subtitle = subtitle or default_subtitle

    # Convert markdown body (toc extension adds id attributes to headers)
    md_ext = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'toc'],
        extension_configs={'toc': {'toc_depth': '2-3'}},
        output_format='html5'
    )
    html_body = md_ext.convert(md_text)

    # Extract first H1 for cover
    first_h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_body)
    if first_h1_match:
        extracted_title = html.unescape(re.sub(r'<[^>]+>', '', first_h1_match.group(1)).strip())
        if title in (default_title, "Alexandria Deep Research Report", "Alexandria \u6df1\u5ea6\u7814\u7a76\u62a5\u544a"):
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
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', '\\"')
    safe_subtitle = subtitle.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', '\\"')
    header_text = f"{safe_title}  |  {safe_subtitle}"
    css = CSS_TEMPLATE.replace("HEADER_TEXT", header_text)
    css = css.replace("PAGE_LABEL", page_label)
    css = css.replace("PAGE_SUFFIX", page_suffix)

    # Build cover (use HTML-escaped versions to prevent markup injection)
    cover_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cover_subtitle = subtitle.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cover_meta = meta_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if meta_line else ""
    cover_html = f"""
    <div class="cover">
        <h1>{cover_title}</h1>
        <div class="subtitle">{cover_subtitle}</div>
        {"<div class='meta'>" + cover_meta + "</div>" if cover_meta else ""}
        <hr class="divider">
    </div>
    """

    html_lang = "zh-CN" if lang == "zh" else "en"

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


def main():
    parser = argparse.ArgumentParser(description="Alexandria Report: Markdown to PDF")
    parser.add_argument("input", help="Input Markdown file")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument("--title", default=None, help="Report title (auto-detected from H1 if omitted)")
    parser.add_argument("--subtitle", default=None, help="Report subtitle")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        md_text = f.read()

    html = md_to_html(md_text, title=args.title, subtitle=args.subtitle)

    # Save intermediate HTML for debugging
    html_path = args.output.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML generated: {html_path}")

    # Convert to PDF
    from weasyprint import HTML
    HTML(string=html).write_pdf(args.output)
    size_kb = os.path.getsize(args.output) / 1024
    print(f"[OK] PDF generated: {args.output} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
