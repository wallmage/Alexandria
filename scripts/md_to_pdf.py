#!/usr/bin/env python3
"""
Alexandria Report: Markdown -> consulting-grade PDF (WeasyPrint)

Usage:
    python3 md_to_pdf.py input.md output.pdf --template executive \
        --rewild-receipt receipt.json

Dependencies: install from requirements.txt
"""

import argparse
import html
import json
import re
import sys
import tempfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_templates import (  # noqa: E402
    TEMPLATE_CHOICES,
    TEMPLATES,
    build_css,
    cover_art_html,
    select_template,
)
from validate_report import validate_markdown, validate_rewild_receipt  # noqa: E402


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
SAFE_IMAGE_DATA_TYPES = (
    "data:image/png",
    "data:image/jpeg",
    "data:image/gif",
    "data:image/webp",
)
MAX_ASSET_BYTES = 25_000_000

FONT_SANS_EN = '"Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif'
FONT_SANS_CN = (
    '"Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", '
    '"Microsoft YaHei", "Droid Sans Fallback", Arial, sans-serif'
)
FONT_SANS_HK = (
    '"Noto Sans CJK HK", "PingFang HK", "Hiragino Sans", '
    '"Microsoft JhengHei", "Droid Sans Fallback", Arial, sans-serif'
)
FONT_SERIF_EN = (
    '"Iowan Old Style", "Baskerville", "Palatino Linotype", Georgia, serif'
)
FONT_SERIF_CN = (
    '"Noto Serif CJK SC", "Songti SC", "STSong", "SimSun", serif'
)
FONT_SERIF_HK = (
    '"Noto Serif CJK HK", "Songti TC", "STSong", "PMingLiU", serif'
)
FONT_MONO = '"Menlo", "Consolas", "Courier New", Courier, monospace'


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
    """Allow only bounded raster assets contained by the Markdown directory."""
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
            raise ValueError(
                f"Asset exceeds the {MAX_ASSET_BYTES}-byte limit: {resource_path}"
            )
        if default_fetcher is None:
            from weasyprint import default_url_fetcher as fetch
        else:
            fetch = default_fetcher
        return fetch(resource_path.as_uri())

    return secure_fetch


def detect_language(text):
    """Return a practical HTML language tag for English or Chinese text."""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    total_alpha = len(re.findall(r"[a-zA-Z]", text))
    if chinese_chars <= total_alpha * 0.3:
        return "en"

    traditional = sum(text.count(char) for char in TRADITIONAL_MARKERS)
    simplified = sum(text.count(char) for char in SIMPLIFIED_MARKERS)
    return "zh-HK" if traditional > simplified else "zh-CN"


def plain_text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def trim_summary(value, limit=145):
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(".,;:，。；：")
    return f"{shortened}…"


def build_toc_html(html_body, lang="en"):
    """Build a clean contents page with section titles and short descriptions."""
    sections = list(
        re.finditer(
            r'<h2\s*id="([^"]*)"[^>]*>(.*?)</h2>(.*?)(?=<h2\b|\Z)',
            html_body,
            re.DOTALL,
        )
    )
    if not sections:
        fallback = list(
            re.finditer(
                r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2\b|\Z)",
                html_body,
                re.DOTALL,
            )
        )
        sections = fallback
        has_ids = False
    else:
        has_ids = True
    if not sections:
        return ""

    labels = {
        "en": (
            "Report navigation",
            "Contents",
            "A clear map of the report’s argument, evidence, and conclusions.",
            "Analysis, evidence, and implications.",
        ),
        "zh-CN": (
            "报告导航",
            "目录",
            "按章节查看报告的论点、证据与结论。",
            "本章的分析、证据与启示。",
        ),
        "zh-HK": (
            "報告導航",
            "目錄",
            "按章節查看報告的論點、證據與結論。",
            "本章的分析、證據與啟示。",
        ),
    }[lang]
    kicker, toc_title, toc_intro, fallback_summary = labels

    items = []
    for match in sections:
        if has_ids:
            hid, heading, content = match.groups()
        else:
            heading, content = match.groups()
            hid = ""
        title = html.escape(plain_text(heading))
        paragraph = re.search(r"<p>(.*?)</p>", content, re.DOTALL)
        if paragraph:
            summary = trim_summary(plain_text(paragraph.group(1)))
        else:
            subheads = [
                plain_text(item)
                for item in re.findall(r"<h3[^>]*>(.*?)</h3>", content, re.DOTALL)
            ]
            summary = " · ".join(subheads[:3]) or fallback_summary
        safe_summary = html.escape(summary)
        if hid:
            safe_id = html.escape(hid, quote=True)
            title_html = (
                f'<a class="toc-entry-title" href="#{safe_id}">{title}</a>'
            )
            page_html = f'<a class="toc-page-number" href="#{safe_id}"></a>'
        else:
            title_html = f'<span class="toc-entry-title">{title}</span>'
            page_html = '<span class="toc-page-number"></span>'
        items.append(
            '<div class="toc-entry">'
            '<span class="toc-number"></span>'
            f'<div class="toc-copy">{title_html}'
            f'<span class="toc-summary">{safe_summary}</span></div>'
            f"{page_html}</div>"
        )

    return (
        '<section class="toc-page">'
        f'<div class="toc-kicker">{html.escape(kicker)}</div>'
        f'<h2 class="toc-title">{html.escape(toc_title)}</h2>'
        f'<p class="toc-intro">{html.escape(toc_intro)}</p>'
        f'<div class="toc-list">{"".join(items)}</div>'
        "</section>"
    )


def transform_callouts(html_body):
    """Convert portable Markdown callout markers into designed report components."""
    class_names = {
        "METRIC": "metric-card",
        "INSIGHT": "insight-panel",
        "TAKEAWAY": "takeaway-band",
    }
    marker_pattern = re.compile(
        r"<p>\s*\[!(METRIC|INSIGHT|TAKEAWAY)\]\s*(?:<br\s*/?>|\r?\n)?",
        re.IGNORECASE,
    )

    def replace(match):
        inner = match.group(1)
        markers = list(marker_pattern.finditer(inner))
        if not markers:
            return match.group(0)

        components = []
        prefix = inner[: markers[0].start()]
        if prefix.strip():
            components.append(f"<blockquote>{prefix}</blockquote>")

        for index, marker in enumerate(markers):
            end = (
                markers[index + 1].start()
                if index + 1 < len(markers)
                else len(inner)
            )
            content = inner[marker.end() : end]
            content = re.sub(r"^\s*</p>\s*", "", content, count=1)
            if not re.match(
                r"\s*<(?:p|ul|ol|table|pre|div|blockquote|h[1-6])\b",
                content,
                re.IGNORECASE,
            ):
                content = f"<p>{content}"
            kind = marker.group(1).upper()
            if kind == "METRIC":
                content = re.sub(
                    r"^\s*<p>\s*<strong>(.*?)</strong>\s*(.*?)</p>",
                    r'<div class="metric-value">\1</div><p>\2</p>',
                    content,
                    count=1,
                    flags=re.DOTALL | re.IGNORECASE,
                )
            components.append(
                f'<aside class="{class_names[kind]}">{content}</aside>'
            )
        return "".join(components)

    return re.sub(
        r"<blockquote>(.*?)</blockquote>",
        replace,
        html_body,
        flags=re.DOTALL,
    )


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


def localized_today(lang, today=None):
    today = today or date.today()
    if lang == "en":
        return f"{today.day:02d} {today.strftime('%B')} {today.year}"
    return f"{today.year}年{today.month}月{today.day}日"


def extract_report_meta(md_text):
    """Extract the first H1 and an optional immediate blockquote metadata line."""
    title = ""
    meta_line = ""
    found_h1 = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not found_h1:
            title = stripped[2:].strip()
            found_h1 = True
            continue
        if found_h1 and stripped.startswith(">"):
            meta_line = stripped.lstrip(">").strip()
            break
        if found_h1 and stripped:
            break
    return title, meta_line


def split_cover_title(title, subtitle):
    """Use a colon as an intentional cover hierarchy when no subtitle was supplied."""
    if subtitle:
        return title, "", subtitle
    for separator in (":", "："):
        if separator in title:
            lead, accent = title.split(separator, 1)
            if lead.strip() and accent.strip():
                return lead.strip(), accent.strip(), ""
    return title, "", ""


def visual_text_units(value):
    """Estimate cover space, weighting CJK glyphs more heavily than Latin text."""
    return sum(
        2 if "\u3400" <= char <= "\u9fff" else 1
        for char in value
        if not char.isspace()
    )


def cover_density_class(title, subtitle):
    units = visual_text_units(title) + int(visual_text_units(subtitle) * 0.6)
    if units >= 115:
        return "cover-title-very-long"
    if units >= 60:
        return "cover-title-long"
    return "cover-title-standard"


def localized_settings(lang, template):
    sans = {
        "en": FONT_SANS_EN,
        "zh-CN": FONT_SANS_CN,
        "zh-HK": FONT_SANS_HK,
    }[lang]
    serif = {
        "en": FONT_SERIF_EN,
        "zh-CN": FONT_SERIF_CN,
        "zh-HK": FONT_SERIF_HK,
    }[lang]
    values = {
        "en": {
            "default_title": "Alexandria Research Report",
            "page_label": "",
            "page_suffix": "",
            "deep_research": "Deep Research Report",
            "prepared_by": "Prepared by",
            "client": "Client",
            "date": "Date",
            "confidential": "Strictly Confidential",
            "controlled": "Controlled copy · Not for external distribution",
            "insight": "Executive insight",
            "takeaway": "What this means",
        },
        "zh-CN": {
            "default_title": "Alexandria 深度研究报告",
            "page_label": "第",
            "page_suffix": " 页",
            "deep_research": "深度研究报告",
            "prepared_by": "撰写",
            "client": "客户",
            "date": "日期",
            "confidential": "严格保密",
            "controlled": "受控文件 · 不得对外传播",
            "insight": "核心判断",
            "takeaway": "这意味着什么",
        },
        "zh-HK": {
            "default_title": "Alexandria 深度研究報告",
            "page_label": "第",
            "page_suffix": " 頁",
            "deep_research": "深度研究報告",
            "prepared_by": "撰寫",
            "client": "客戶",
            "date": "日期",
            "confidential": "嚴格保密",
            "controlled": "受控文件 · 不得對外傳閱",
            "insight": "核心判斷",
            "takeaway": "這意味着甚麼",
        },
    }[lang]
    values["font_sans"] = sans
    values["font_display"] = serif if TEMPLATES[template].display_serif else sans
    return values


def md_to_html(
    md_text,
    title=None,
    subtitle=None,
    lang="auto",
    template="auto",
    client=None,
    prepared_by="Alexandria",
    confidential=False,
    report_date=None,
    cover_image=None,
):
    """Convert Markdown to a complete template-aware HTML report."""
    markdown = load_markdown()
    lang = detect_language(md_text) if lang == "auto" else lang

    source_title, meta_line = extract_report_meta(md_text)
    provisional_title = title or source_title or "Alexandria Research Report"
    selected_template = select_template(
        f"{provisional_title}\n{md_text[:5000]}", template
    )
    localized = localized_settings(lang, selected_template)
    if not title:
        title = source_title or localized["default_title"]
    subtitle = subtitle or ""
    report_date = report_date or meta_line or localized_today(lang)
    prepared_by = prepared_by or "Alexandria"
    client = client.strip() if client and client.strip() else None

    md_ext = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
        output_format="html5",
    )
    html_body = sanitize_html_fragment(md_ext.convert(md_text))

    first_h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_body, re.DOTALL)
    if first_h1_match:
        html_body = html_body.replace(first_h1_match.group(0), "", 1)

    if meta_line:
        meta_line_html = html.escape(meta_line)
        meta_bq_pattern = re.compile(
            r"<blockquote>\s*<p>"
            + re.escape(meta_line_html)
            + r"</p>\s*</blockquote>",
            re.DOTALL,
        )
        html_body = meta_bq_pattern.sub("", html_body, count=1)

    html_body = transform_callouts(html_body)
    toc_html = build_toc_html(html_body, lang)

    safe_title_css = escape_css_content(title)
    header_text = f"{safe_title_css}  /  {TEMPLATES[selected_template].display_name}"
    footer_text = (
        escape_css_content(localized["controlled"])
        if confidential
        else "ALEXANDRIA  /  RESEARCH REPORT"
    )
    css = build_css(
        selected_template,
        font_sans=localized["font_sans"],
        font_display=localized["font_display"],
        font_mono=FONT_MONO,
        header_text=header_text,
        page_label=localized["page_label"],
        page_suffix=localized["page_suffix"],
        footer_text=footer_text,
        insight_label=escape_css_content(localized["insight"]),
        takeaway_label=escape_css_content(localized["takeaway"]),
    )

    cover_lead, cover_accent, cover_subtitle = split_cover_title(title, subtitle)
    safe_cover_image = html.escape(cover_image, quote=True) if cover_image else None
    art = cover_art_html(selected_template, safe_cover_image)

    metadata = []
    if client:
        metadata.append(
            '<div class="meta-cell">'
            f'<span class="meta-label">{html.escape(localized["client"])}</span>'
            f'<span class="meta-value">{html.escape(client)}</span></div>'
        )
    metadata.extend(
        [
            '<div class="meta-cell">'
            f'<span class="meta-label">{html.escape(localized["prepared_by"])}</span>'
            f'<span class="meta-value">{html.escape(prepared_by)}</span></div>',
            '<div class="meta-cell">'
            f'<span class="meta-label">{html.escape(localized["date"])}</span>'
            f'<span class="meta-value">{html.escape(report_date)}</span></div>',
        ]
    )
    if confidential:
        metadata.append(
            '<div class="meta-cell">'
            f'<span class="confidential-stamp">{html.escape(localized["confidential"])}</span>'
            "</div>"
        )

    cover_classes = [
        "cover",
        f"cover-{selected_template}",
        cover_density_class(title, subtitle),
        f"cover-meta-{len(metadata)}",
    ]
    if max(
        (visual_text_units(value) for value in (client or "", prepared_by)),
        default=0,
    ) >= 32:
        cover_classes.append("cover-meta-long")

    cover_html = (
        f'<section class="{" ".join(cover_classes)}">'
        f"{art}"
        '<div class="cover-topline"><span>Alexandria / Advisory</span>'
        f'<span>{html.escape(TEMPLATES[selected_template].display_name)} / '
        f'{html.escape(report_date)}</span></div>'
        '<div class="cover-copy">'
        f'<div class="cover-kicker">{html.escape(localized["deep_research"])}</div>'
        f"<h1>{html.escape(cover_lead)}</h1>"
        + (
            f'<div class="cover-title-accent">{html.escape(cover_accent)}</div>'
            if cover_accent
            else ""
        )
        + (
            f'<div class="subtitle">{html.escape(cover_subtitle)}</div>'
            if cover_subtitle
            else ""
        )
        + "</div>"
        f'<div class="cover-record">{"".join(metadata)}</div>'
        + (
            f'<div class="cover-confidential-note">{html.escape(localized["controlled"])}</div>'
            if confidential
            else ""
        )
        + "</section>"
    )

    return (
        "<!DOCTYPE html>"
        f'<html lang="{lang}"><head><meta charset="UTF-8">'
        f"<style>{css}</style></head><body>"
        f'<div class="report template-{selected_template}" '
        f'data-template="{selected_template}">'
        f"{cover_html}{toc_html}"
        f'<main class="report-body">{html_body}</main>'
        "</div></body></html>"
    )


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


def validate_cover_image(input_path, cover_image):
    """Return a safe path relative to the report directory."""
    if not cover_image:
        return None
    asset_root = input_path.parent.resolve()
    candidate = Path(cover_image)
    if not candidate.is_absolute():
        candidate = asset_root / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise ValueError(f"Cover image not found: {candidate}")
    if not candidate.is_relative_to(asset_root):
        raise ValueError("Cover image must be inside the Markdown report directory.")
    if candidate.suffix.lower() not in LOCAL_ASSET_SUFFIXES:
        raise ValueError(f"Unsupported cover image type: {candidate.suffix}")
    if candidate.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError(
            f"Cover image exceeds the {MAX_ASSET_BYTES}-byte limit: {candidate}"
        )
    return candidate.relative_to(asset_root).as_posix()


def validate_rewild_for_render(input_path, receipt_path, lang):
    """Reject rendering unless the exact Markdown passed the Rewild gate."""
    if not receipt_path:
        raise ValueError(
            "A Rewild gate receipt is required. Run scripts/rewild_gate.py first."
        )
    receipt_path = Path(receipt_path)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Rewild receipt could not be read: {exc}") from exc
    receipt_lang = receipt.get("report_lang")
    expected_lang = receipt_lang if lang == "auto" else lang
    errors = validate_rewild_receipt(
        input_path,
        receipt,
        expected_lang=expected_lang,
    )
    text = input_path.read_text(encoding="utf-8")
    if expected_lang == "en":
        errors.extend(
            validate_markdown(
                text,
                min_words=7500,
                max_words=15000,
                min_sources=1,
                min_sections=3,
                expected_lang="en",
            )
        )
    elif expected_lang in {"zh-CN", "zh-HK"}:
        errors.extend(
            validate_markdown(
                text,
                min_chars=5000,
                max_chars=10000,
                min_sources=1,
                min_sections=3,
                expected_lang=expected_lang,
            )
        )
    else:
        errors.append("Rewild receipt has no supported report language.")
    if errors:
        raise ValueError("Rewild production gate failed: " + " ".join(errors))


def render_pdf(
    input_path,
    output_path,
    *,
    title=None,
    subtitle=None,
    lang="auto",
    template="auto",
    client=None,
    prepared_by="Alexandria",
    confidential=False,
    report_date=None,
    cover_image=None,
    rewild_receipt=None,
    keep_html=False,
    force=False,
):
    """Render one Markdown file and return the output PDF path."""
    input_path, output_path = validate_paths(input_path, output_path, force=force)
    validate_rewild_for_render(input_path, rewild_receipt, lang)
    safe_cover_image = validate_cover_image(input_path, cover_image)
    md_text = input_path.read_text(encoding="utf-8")
    rendered_html = md_to_html(
        md_text,
        title=title,
        subtitle=subtitle,
        lang=lang,
        template=template,
        client=client,
        prepared_by=prepared_by,
        confidential=confidential,
        report_date=report_date,
        cover_image=safe_cover_image,
    )

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
    parser = argparse.ArgumentParser(
        description="Alexandria Report: Markdown to consulting-grade PDF"
    )
    parser.add_argument("input", help="Input Markdown file")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument(
        "--title", default=None, help="Report title (auto-detected from H1 if omitted)"
    )
    parser.add_argument("--subtitle", default=None, help="Report subtitle")
    parser.add_argument(
        "--lang",
        choices=LANG_CHOICES,
        default="auto",
        help="Document language and locale (default: auto)",
    )
    parser.add_argument(
        "--template",
        choices=TEMPLATE_CHOICES,
        default="auto",
        help="PDF visual system; auto adapts by topic (default: auto)",
    )
    parser.add_argument(
        "--client",
        default=None,
        help="Optional client name; omitted from the report when blank",
    )
    parser.add_argument(
        "--prepared-by",
        default="Alexandria",
        help="Author or organization shown on the cover (default: Alexandria)",
    )
    parser.add_argument(
        "--confidential",
        action="store_true",
        help="Add Strictly Confidential stamps and controlled-copy footer wording",
    )
    parser.add_argument(
        "--date",
        dest="report_date",
        default=None,
        help="Cover date (default: report metadata line or today's date)",
    )
    parser.add_argument(
        "--cover-image",
        default=None,
        help="Optional local raster image inside the report directory",
    )
    parser.add_argument(
        "--rewild-receipt",
        required=True,
        help="passing Rewild receipt bound to the exact input Markdown",
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
            template=args.template,
            client=args.client,
            prepared_by=args.prepared_by,
            confidential=args.confidential,
            report_date=args.report_date,
            cover_image=args.cover_image,
            rewild_receipt=args.rewild_receipt,
            keep_html=args.keep_html,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
