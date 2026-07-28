#!/usr/bin/env python3
"""
Alexandria Report: Markdown -> consulting-grade PDF (WeasyPrint)

Usage:
    python3 md_to_pdf.py input.md output.pdf --template executive \
        --rewild-receipt receipt.json --ledger ledger.json \
        --content-receipt content-receipt.json

Dependencies: install from requirements.txt
"""

import argparse
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from content_gate import validate_content_receipt
from pdf_templates import (
    TEMPLATE_CHOICES,
    TEMPLATES,
    build_css,
    bundled_horizon_image_data_uri,
    bundled_template_image_data_uri,
    cover_art_html,
    select_adaptive_companion,  # noqa: F401 -- intentional public helper
    select_template,
)
from validate_report import (
    detect_language as detect_report_language,
)
from validate_report import (
    validate_markdown,
    validate_rewild_receipt,
)

LANG_CHOICES = ("auto", "en", "zh-CN", "zh-HK")
SAFE_TAGS = {
    "a", "b", "blockquote", "br", "code", "del", "div", "em", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre",
    "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul",
}
SUPPRESSED_CONTENT_TAGS = {
    "script", "style", "template", "noscript", "iframe", "object", "embed"
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
MIN_COVER_SHORT_EDGE = 600
MIN_COVER_LONG_EDGE = 1000

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
        self.suppressed_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SUPPRESSED_CONTENT_TAGS:
            self.suppressed_depth += 1
            return
        if self.suppressed_depth:
            return
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
        if tag in SUPPRESSED_CONTENT_TAGS:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in SUPPRESSED_CONTENT_TAGS:
            self.suppressed_depth = max(0, self.suppressed_depth - 1)
            return
        if self.suppressed_depth:
            return
        if tag in SAFE_TAGS and tag not in {"br", "hr", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.suppressed_depth:
            return
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self.suppressed_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if self.suppressed_depth:
            return
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

        raw_path = (
            url2pathname(unquote(parsed.path))
            if parsed.scheme == "file"
            else unquote(parsed.path)
        )
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
    detected = detect_report_language(text)
    return "zh-CN" if detected == "zh" else detected


def plain_text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def trim_summary(value, limit=145):
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(".,;:，。；：")
    return f"{shortened}…"


def build_toc_html(html_body, lang="en", template="executive"):
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
    for item_index, match in enumerate(sections, 1):
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
            f'<span class="toc-number" data-toc-index="{item_index:02d}"></span>'
            f'<div class="toc-copy">{title_html}'
            f'<span class="toc-summary">{safe_summary}</span></div>'
            f"{page_html}</div>"
        )

    if template in {
        "maison",
        "blueprint",
        "terrain",
        "orbit",
        "sunbeam",
        "current",
        "apricot",
    }:
        chrome = {
            "en": {
                "register": "Editorial register",
                "maison_statement": "Context, evidence, character, and choice.",
                "input": "Input",
                "structure": "Structure",
                "decision": "Decision",
                "field_index": "Field index / evidence terrain",
                "orientation": "Orientation / evidence to action",
                "bright_path": "Bright path / evidence to possibility",
                "flow_path": "Flow map / signal to action",
                "people_path": "People lens / context to choice",
            },
            "zh-CN": {
                "register": "编辑脉络",
                "maison_statement": "背景、证据、特征与选择。",
                "input": "输入",
                "structure": "结构",
                "decision": "决策",
                "field_index": "田野索引 / 证据地形",
                "orientation": "阅读方位 / 从证据到行动",
                "bright_path": "明亮路径 / 从证据到可能性",
                "flow_path": "流动地图 / 从信号到行动",
                "people_path": "人的视角 / 从情境到选择",
            },
            "zh-HK": {
                "register": "編輯脈絡",
                "maison_statement": "背景、證據、特徵與選擇。",
                "input": "輸入",
                "structure": "結構",
                "decision": "決策",
                "field_index": "田野索引 / 證據地形",
                "orientation": "閱讀方位 / 由證據到行動",
                "bright_path": "明亮路徑 / 由證據到可能性",
                "flow_path": "流動地圖 / 由訊號到行動",
                "people_path": "人的視角 / 由情境到選擇",
            },
        }[lang]
        special = {
            "maison": {
                "class": "toc-maison maison-toc-editorial",
                "marker": (
                    '<div class="maison-toc-note">'
                    f'<span>{html.escape(chrome["register"])}</span>'
                    f'<strong>{html.escape(chrome["maison_statement"])}</strong>'
                    "</div>"
                ),
            },
            "blueprint": {
                "class": "toc-blueprint",
                "marker": (
                    '<div class="blueprint-toc-map">'
                    f'<span>{html.escape(chrome["input"])}</span><i></i>'
                    f'<span>{html.escape(chrome["structure"])}</span><i></i>'
                    f'<span>{html.escape(chrome["decision"])}</span>'
                    "</div>"
                ),
            },
            "terrain": {
                "class": "toc-terrain",
                "marker": (
                    '<div class="terrain-toc-map">'
                    '<img src="'
                    + html.escape(
                        bundled_template_image_data_uri("terrain"), quote=True
                    )
                    + f'" alt=""><span>{html.escape(chrome["field_index"])}</span></div>'
                ),
            },
            "orbit": {
                "class": "toc-orbit",
                "marker": (
                    '<div class="orbit-toc-field">'
                    '<span class="orbit-toc-ring"></span>'
                    f'<strong>{html.escape(chrome["orientation"])}</strong>'
                    "</div>"
                ),
            },
            "sunbeam": {
                "class": "toc-sunbeam",
                "marker": (
                    '<div class="sunbeam-toc-system">'
                    '<span class="sunbeam-toc-ring"></span>'
                    f'<strong>{html.escape(chrome["bright_path"])}</strong>'
                    "</div>"
                ),
            },
            "current": {
                "class": "toc-current",
                "marker": (
                    '<div class="current-toc-system">'
                    '<span class="current-toc-line"></span>'
                    f'<strong>{html.escape(chrome["flow_path"])}</strong>'
                    "</div>"
                ),
            },
            "apricot": {
                "class": "toc-apricot",
                "marker": (
                    '<div class="apricot-toc-system">'
                    '<span class="apricot-toc-dot"></span>'
                    f'<strong>{html.escape(chrome["people_path"])}</strong>'
                    "</div>"
                ),
            },
        }[template]
        pages = []
        chunk_size = {
            "maison": 6,
            "blueprint": 8,
            "terrain": 6,
            "orbit": 8,
            "sunbeam": 6,
            "current": 6,
            "apricot": 6,
        }[template]
        chunks = [
            items[index : index + chunk_size]
            for index in range(0, len(items), chunk_size)
        ]
        for page_index, chunk in enumerate(chunks):
            is_first = page_index == 0
            pages.append(
                f'<section class="toc-page {special["class"]}'
                + ("" if is_first else " toc-special-cont")
                + '">'
                f'<div class="toc-kicker">{html.escape(kicker)} / {page_index + 1:02d}</div>'
                f'<h2 class="toc-title">{html.escape(toc_title)}</h2>'
                + (
                    f'<p class="toc-intro">{html.escape(toc_intro)}</p>'
                    if is_first
                    else ""
                )
                + special["marker"]
                + f'<div class="toc-list">{"".join(chunk)}</div>'
                + "</section>"
            )
        return "".join(pages)

    if template == "horizon":
        horizon_labels = {
            "en": {
                "continued": "Contents / continued",
                "route": "Field route / research sequence",
                "statement": (
                    "Evidence becomes useful when the route to judgment is visible."
                ),
                "protocol": "Reading protocol",
                "protocol_title": (
                    "Begin with the brief. Use each conclusion as a decision gate."
                ),
                "reading_time": "Decision path / source to action",
            },
            "zh-CN": {
                "continued": "目录 / 续",
                "route": "研究路径 / 章节顺序",
                "statement": "证据的价值，来自清晰可见的判断路径。",
                "protocol": "阅读方式",
                "protocol_title": "先读摘要，再把每项结论当成一个决策关口。",
                "reading_time": "决策路径 / 从证据到行动",
            },
            "zh-HK": {
                "continued": "目錄 / 續",
                "route": "研究路徑 / 章節次序",
                "statement": "證據的價值，來自清晰可見的判斷路徑。",
                "protocol": "閱讀方式",
                "protocol_title": "先讀摘要，再把每項結論視為一個決策關口。",
                "reading_time": "決策路徑 / 由證據到行動",
            },
        }[lang]
        pages = []
        chunks = [items[index : index + 8] for index in range(0, len(items), 8)]
        for page_index, chunk in enumerate(chunks):
            is_first = page_index == 0
            title_text = toc_title if is_first else horizon_labels["continued"]
            chrome = ""
            if is_first:
                chrome = (
                    '<div class="horizon-toc-band">'
                    f'<span class="horizon-toc-route">{html.escape(horizon_labels["route"])}</span>'
                    f'<strong>{html.escape(horizon_labels["statement"])}</strong>'
                    '<span class="horizon-toc-scale"></span>'
                    "</div>"
                    '<div class="horizon-reading-card">'
                    f'<span>{html.escape(horizon_labels["protocol"])}</span>'
                    f'<strong>{html.escape(horizon_labels["protocol_title"])}</strong>'
                    f'<small>{html.escape(horizon_labels["reading_time"])}</small>'
                    "</div>"
                )
            pages.append(
                '<section class="toc-page toc-horizon'
                + ("" if is_first else " toc-horizon-cont")
                + '">'
                f'<div class="toc-kicker">02{f".{page_index + 1}" if page_index else ""}</div>'
                f'<h2 class="toc-title">{html.escape(title_text)}</h2>'
                + (
                    f'<p class="toc-intro">{html.escape(toc_intro)}</p>'
                    if is_first
                    else ""
                )
                + f'<div class="toc-list">{"".join(chunk)}</div>'
                + chrome
                + "</section>"
            )
        return "".join(pages)

    return (
        '<section class="toc-page">'
        f'<div class="toc-kicker">{html.escape(kicker)}</div>'
        f'<h2 class="toc-title">{html.escape(toc_title)}</h2>'
        f'<p class="toc-intro">{html.escape(toc_intro)}</p>'
        f'<div class="toc-list">{"".join(items)}</div>'
        "</section>"
    )


def build_horizon_feature_html(
    html_body,
    lang,
    image_src,
    label_overrides=None,
    *,
    decorative_image=False,
):
    """Move the opening section into Horizon's photographic feature page."""
    heading = re.search(
        r'<h2\s+id="([^"]+)"[^>]*>(.*?)</h2>',
        html_body,
        re.DOTALL,
    )
    if not heading:
        return "", html_body

    next_heading = re.search(r"<h2\b", html_body[heading.end() :])
    section_end = (
        heading.end() + next_heading.start()
        if next_heading
        else len(html_body)
    )
    section = html_body[heading.end() : section_end]

    insight = re.search(
        r'<aside class="insight-panel">(.*?)</aside>',
        section,
        re.DOTALL,
    )
    card_html = insight.group(1) if insight else ""
    section_without_insight = (
        section[: insight.start()] + section[insight.end() :]
        if insight
        else section
    )
    narrative = re.search(r"<p>(.*?)</p>", section_without_insight, re.DOTALL)
    narrative_html = narrative.group(0) if narrative else ""
    remaining_section = (
        section_without_insight[: narrative.start()]
        + section_without_insight[narrative.end() :]
        if narrative
        else section_without_insight
    )
    if not card_html:
        card_html = narrative_html
        narrative_html = ""
    insight_class = (
        "horizon-feature-insight horizon-feature-insight-long"
        if len(plain_text(card_html)) > 180
        else "horizon-feature-insight"
    )

    labels = {
        "en": {
            "running": "Field note 03 / decision signals",
            "descriptor": "A field view of the evidence shaping this report.",
            "figure": "Fig. 03A / decision horizon",
            "observation": "Primary observation",
            "caption": (
                "The horizon is used as a field metaphor: verified evidence "
                "meets unresolved uncertainty."
            ),
            "terrain": "Reading the terrain",
            "path": "Report path",
        },
        "zh-CN": {
            "running": "研究记录 03 / 决策信号",
            "descriptor": "从证据出发，观察这份报告所讨论的变化。",
            "figure": "图 03A / 决策边界",
            "observation": "核心观察",
            "caption": "以地平线作比喻：已核实的证据，在这里遇上尚未解决的不确定性。",
            "terrain": "阅读现场",
            "path": "报告路径",
        },
        "zh-HK": {
            "running": "研究記錄 03 / 決策訊號",
            "descriptor": "由證據出發，觀察這份報告所討論的變化。",
            "figure": "圖 03A / 決策邊界",
            "observation": "核心觀察",
            "caption": "以地平線作比喻：已核實的證據，在這裏遇上尚未解決的不確定性。",
            "terrain": "閱讀現場",
            "path": "報告路徑",
        },
    }[lang]
    if label_overrides:
        labels.update(label_overrides)

    later_headings = [
        plain_text(item)
        for item in re.findall(
            r'<h2\s+id="[^"]+"[^>]*>(.*?)</h2>',
            html_body[heading.end() :],
            re.DOTALL,
        )[:3]
    ]
    path_items = "".join(
        '<li><span>'
        f"{index:02d}"
        "</span><strong>"
        f"{html.escape(title)}"
        "</strong></li>"
        for index, title in enumerate(later_headings, 1)
    )

    safe_image = html.escape(image_src, quote=True)
    figure_label_html = (
        ""
        if decorative_image
        else f'<div class="horizon-feature-figure-label">{html.escape(labels["figure"])}</div>'
    )
    caption_html = (
        ""
        if decorative_image
        else f'<p class="horizon-feature-caption">{html.escape(labels["caption"])}</p>'
    )
    feature_html = (
        '<section class="horizon-feature-page">'
        f'<div class="horizon-feature-running">{html.escape(labels["running"])}</div>'
        '<div class="horizon-feature-heading-row">'
        f'<h2 id="{html.escape(heading.group(1), quote=True)}">'
        f"{heading.group(2)}</h2>"
        f'<p>{html.escape(labels["descriptor"])}</p>'
        "</div>"
        f"{figure_label_html}"
        '<div class="horizon-feature-photo">'
        f'<img src="{safe_image}" alt="">'
        '<span class="horizon-feature-datum"></span>'
        "</div>"
        f'<aside class="{insight_class}">'
        f'<span>{html.escape(labels["observation"])}</span>'
        f"{card_html}</aside>"
        f"{caption_html}"
        '<div class="horizon-feature-lower">'
        '<div class="horizon-feature-narrative">'
        f'<h3>{html.escape(labels["terrain"])}</h3>'
        f"{narrative_html}</div>"
        '<div class="horizon-feature-path">'
        f'<span>{html.escape(labels["path"])}</span>'
        f"<ol>{path_items}</ol>"
        "</div></div>"
        "</section>"
    )
    remaining_html = (
        html_body[: heading.start()]
        + remaining_section
        + html_body[section_end:]
    )
    return feature_html, remaining_html


def build_reference_feature_html(
    html_body,
    lang,
    template,
    image_src,
    *,
    decorative_image=False,
):
    """Build the supplied editorial opener while preserving report content."""
    overrides = {
        "maison": {
            "en": {
                "running": "Editorial note 03 / market character",
                "descriptor": "An editorial synthesis of context, evidence, and choice.",
                "figure": "Plate 03A / category landscape",
                "caption": "The image establishes the lived setting in which the evidence must work.",
                "terrain": "Reading the character",
                "path": "Decision agenda",
            },
            "zh-CN": {
                "running": "编辑观察 03 / 市场特征",
                "descriptor": "把背景、证据与选择放在同一个编辑视角下。",
                "figure": "图版 03A / 品类现场",
                "caption": "图像呈现证据真正发挥作用的现实场景。",
                "terrain": "理解市场特征",
                "path": "决策议程",
            },
            "zh-HK": {
                "running": "編輯觀察 03 / 市場特徵",
                "descriptor": "把背景、證據與選擇放在同一個編輯視角下。",
                "figure": "圖版 03A / 品類現場",
                "caption": "圖像呈現證據真正發揮作用的現實場景。",
                "terrain": "理解市場特徵",
                "path": "決策議程",
            },
        },
        "blueprint": {
            "en": {
                "running": "System note 03 / decision architecture",
                "descriptor": "A structural view of inputs, mechanisms, and decisions.",
                "figure": "Datum 03A / operating system",
                "caption": "The blueprint makes the route from evidence to action inspectable.",
                "terrain": "How the system works",
                "path": "Control points",
            },
            "zh-CN": {
                "running": "系统记录 03 / 决策架构",
                "descriptor": "拆开来看输入、机制与决策如何相互作用。",
                "figure": "基准 03A / 运营系统",
                "caption": "蓝图让证据如何走向行动变得清晰可查。",
                "terrain": "系统如何运作",
                "path": "关键控制点",
            },
            "zh-HK": {
                "running": "系統記錄 03 / 決策架構",
                "descriptor": "拆開來看輸入、機制與決策如何互相作用。",
                "figure": "基準 03A / 營運系統",
                "caption": "藍圖讓證據如何走向行動變得清晰可查。",
                "terrain": "系統如何運作",
                "path": "關鍵控制點",
            },
        },
        "terrain": {
            "en": {
                "running": "Field note 03 / evidence terrain",
                "descriptor": "A place-based synthesis of the evidence shaping the report.",
                "figure": "Plate 03A / surveyed terrain",
                "caption": "The field view connects verified evidence to the place it describes.",
                "terrain": "Reading the terrain",
                "path": "Field bearings",
            },
            "zh-CN": {
                "running": "田野记录 03 / 证据地形",
                "descriptor": "从具体地点出发，整理影响本报告的证据。",
                "figure": "图版 03A / 调研地形",
                "caption": "现场视角把核实过的证据与它所描述的地方连在一起。",
                "terrain": "读懂地形",
                "path": "研究方位",
            },
            "zh-HK": {
                "running": "田野記錄 03 / 證據地形",
                "descriptor": "由具體地點出發，整理影響本報告的證據。",
                "figure": "圖版 03A / 調研地形",
                "caption": "現場視角把核實過的證據與它所描述的地方連在一起。",
                "terrain": "讀懂地形",
                "path": "研究方位",
            },
        },
        "orbit": {
            "en": {
                "running": "Synthesis 03 / system signals",
                "descriptor": "A scientific view of interacting signals and decision effects.",
                "figure": "Figure 03A / signal field",
                "caption": "The field model shows how evidence, incentives, and authority interact.",
                "terrain": "Reading the system",
                "path": "Action sequence",
            },
            "zh-CN": {
                "running": "综合分析 03 / 系统信号",
                "descriptor": "从科学视角观察信号如何互动并影响决策。",
                "figure": "图 03A / 信号场",
                "caption": "场模型展示证据、激励与权限如何相互作用。",
                "terrain": "读懂系统",
                "path": "行动顺序",
            },
            "zh-HK": {
                "running": "綜合分析 03 / 系統訊號",
                "descriptor": "從科學視角觀察訊號如何互動並影響決策。",
                "figure": "圖 03A / 訊號場",
                "caption": "場模型展示證據、誘因與權限如何互相作用。",
                "terrain": "讀懂系統",
                "path": "行動次序",
            },
        },
        "sunbeam": {
            "en": {
                "running": "Bright note 03 / shared understanding",
                "descriptor": "A clear, energetic view of the evidence and the choices it opens.",
                "figure": "Signal 03A / evidence in motion",
                "caption": "The visual field turns complex evidence into a shared point of reference.",
                "terrain": "What changes now",
                "path": "Practical moves",
            },
            "zh-CN": {
                "running": "明亮观察 03 / 共同理解",
                "descriptor": "用清晰、有活力的方式呈现证据及其带来的选择。",
                "figure": "信号 03A / 流动中的证据",
                "caption": "视觉场把复杂证据变成大家都能理解的共同参照。",
                "terrain": "现在发生了什么变化",
                "path": "可行的下一步",
            },
            "zh-HK": {
                "running": "明亮觀察 03 / 共同理解",
                "descriptor": "用清晰、有活力的方式呈現證據，以及由此帶來的選擇。",
                "figure": "訊號 03A / 流動中的證據",
                "caption": "視覺場把複雜證據變成大家都容易理解的共同參照。",
                "terrain": "現在有甚麼改變",
                "path": "可行的下一步",
            },
        },
        "current": {
            "en": {
                "running": "Flow note 03 / signals in motion",
                "descriptor": "A fluid view of how evidence moves from signal to action.",
                "figure": "Flow 03A / decision current",
                "caption": "The route map shows where momentum builds, stalls, and changes direction.",
                "terrain": "Reading the current",
                "path": "Next moves",
            },
            "zh-CN": {
                "running": "流动观察 03 / 变化中的信号",
                "descriptor": "沿着一条清晰路径，看证据如何从信号走向行动。",
                "figure": "流向 03A / 决策水流",
                "caption": "路线图显示动力在哪里形成、停滞，以及转向。",
                "terrain": "看懂当前走向",
                "path": "下一步行动",
            },
            "zh-HK": {
                "running": "流動觀察 03 / 變化中的訊號",
                "descriptor": "沿着一條清晰路徑，看證據如何由訊號走向行動。",
                "figure": "流向 03A / 決策水流",
                "caption": "路線圖顯示動力在哪裏形成、停滯，以及轉向。",
                "terrain": "看懂當前走向",
                "path": "下一步行動",
            },
        },
        "apricot": {
            "en": {
                "running": "People note 03 / lived context",
                "descriptor": "A warm editorial view of people, evidence, and practical choice.",
                "figure": "Story 03A / human setting",
                "caption": "The scene keeps lived experience visible while the evidence is interpreted.",
                "terrain": "What the evidence means",
                "path": "Ways forward",
            },
            "zh-CN": {
                "running": "人物观察 03 / 真实情境",
                "descriptor": "以温暖的编辑视角理解人、证据与现实选择。",
                "figure": "故事 03A / 人的现场",
                "caption": "在解读证据时，画面让真实经历始终留在视野中。",
                "terrain": "这些证据意味着什么",
                "path": "接下来怎么走",
            },
            "zh-HK": {
                "running": "人物觀察 03 / 真實情境",
                "descriptor": "以溫暖的編輯視角理解人、證據與現實選擇。",
                "figure": "故事 03A / 人的現場",
                "caption": "解讀證據時，畫面讓真實經歷一直留在視野之內。",
                "terrain": "這些證據代表甚麼",
                "path": "接下來怎樣走",
            },
        },
    }[template][lang]
    feature_html, remaining_html = build_horizon_feature_html(
        html_body,
        lang,
        image_src,
        label_overrides=overrides,
        decorative_image=decorative_image,
    )

    def add_template_class(match):
        class_name = match.group(1)
        return f'class="horizon-{class_name} {template}-{class_name}"'

    feature_html = re.sub(
        r'class="horizon-([^"]+)"',
        add_template_class,
        feature_html,
    )
    return feature_html, remaining_html


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


def wrap_sources_section(html_body):
    """Mark the terminal bibliography so printed copies retain link targets."""
    headings = {
        "sources",
        "references",
        "source list",
        "参考资料",
        "资料来源",
        "來源",
        "參考資料",
        "資料來源",
    }
    matches = list(re.finditer(r"<h2\b[^>]*>(.*?)</h2>", html_body, re.DOTALL))
    for match in reversed(matches):
        if plain_text(match.group(1)).casefold() in headings:
            return (
                html_body[: match.start()]
                + '<section class="sources-section">'
                + html_body[match.start() :]
                + "</section>"
            )
    return html_body


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
    today = today or datetime.now().astimezone().date()
    if lang == "en":
        months = (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
        return f"{today.day:02d} {months[today.month - 1]} {today.year}"
    return f"{today.year}年{today.month}月{today.day}日"


def extract_report_meta(md_text):
    """Extract the first H1 and an optional immediate blockquote metadata line."""
    try:
        from validate_report import _mask_fenced_code
    except ImportError:
        from scripts.validate_report import _mask_fenced_code
    md_text = _mask_fenced_code(md_text)
    title = ""
    metadata_lines = []
    found_h1 = False
    collecting_metadata = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not found_h1:
            title = stripped[2:].strip()
            found_h1 = True
            continue
        if found_h1 and stripped.startswith(">"):
            collecting_metadata = True
            metadata_lines.append(stripped.lstrip(">").strip().rstrip())
            continue
        if collecting_metadata and stripped:
            break
        if found_h1 and stripped and not collecting_metadata:
            break
    date_pattern = re.compile(
        r"^(?:"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"\d{4}年\d{1,2}月\d{1,2}日|"
        r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|"
        r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}"
        r")$"
    )
    report_date = next(
        (value for value in metadata_lines if date_pattern.match(value)),
        metadata_lines[0] if metadata_lines else "",
    )
    return title, report_date


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
            "controlled": "受控文件 · 不得对外传阅",
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
            r"<blockquote>(?:(?!</blockquote>).)*"
            + re.escape(meta_line_html)
            + r"(?:(?!</blockquote>).)*</blockquote>",
            re.DOTALL,
        )
        html_body = meta_bq_pattern.sub("", html_body, count=1)

    html_body = transform_callouts(html_body)
    html_body = wrap_sources_section(html_body)
    toc_html = build_toc_html(html_body, lang, selected_template)

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
    art = cover_art_html(selected_template, cover_image)
    feature_html = ""
    if selected_template == "horizon":
        horizon_image = cover_image or bundled_horizon_image_data_uri()
        feature_html, html_body = build_horizon_feature_html(
            html_body,
            lang,
            horizon_image,
            decorative_image=cover_image is None,
        )
    elif selected_template in {
        "maison",
        "blueprint",
        "terrain",
        "orbit",
        "sunbeam",
        "current",
        "apricot",
    }:
        feature_image = (
            cover_image
            or bundled_template_image_data_uri(
                {
                    "blueprint": "orbit",
                    "sunbeam": "current",
                }.get(selected_template, selected_template)
            )
        )
        feature_html, html_body = build_reference_feature_html(
            html_body,
            lang,
            selected_template,
            feature_image,
            decorative_image=cover_image is None,
        )

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

    if selected_template == "horizon":
        cover_brand = (
            '<span class="horizon-firm-mark"><i></i>'
            "<b>Alexandria</b></span>"
        )
        cover_series = "<span>Deep Research / 02</span>"
    else:
        cover_brand = "<span>Alexandria / Advisory</span>"
        cover_series = (
            f'<span>{html.escape(TEMPLATES[selected_template].display_name)} / '
            f"{html.escape(report_date)}</span>"
        )

    cover_html = (
        f'<section class="{" ".join(cover_classes)}">'
        f"{art}"
        f'<div class="cover-topline">{cover_brand}{cover_series}</div>'
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
        f"<title>{html.escape(title)}</title>"
        f'<meta name="author" content="{html.escape(prepared_by, quote=True)}">'
        f'<meta name="description" content="'
        f'{html.escape(subtitle or localized["deep_research"], quote=True)}">'
        f"<style>{css}</style></head><body>"
        f'<div class="report template-{selected_template}" '
        f'data-template="{selected_template}">'
        f"{cover_html}{toc_html}{feature_html}"
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
    try:
        from PIL import Image, UnidentifiedImageError
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Cover-image validation needs Pillow, installed with WeasyPrint."
        ) from exc
    try:
        with Image.open(candidate) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Cover image could not be decoded: {candidate}") from exc
    short_edge, long_edge = sorted((width, height))
    if (
        short_edge < MIN_COVER_SHORT_EDGE
        or long_edge < MIN_COVER_LONG_EDGE
    ):
        raise ValueError(
            "Cover image resolution is too low for professional PDF output: "
            f"{width}x{height}; minimum edges are "
            f"{MIN_COVER_SHORT_EDGE}x{MIN_COVER_LONG_EDGE} pixels."
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


def validate_content_for_render(input_path, ledger_path, receipt_path, lang):
    """Reject rendering unless the exact report and ledger passed content review."""
    if not ledger_path:
        raise ValueError(
            "An evidence ledger is required for the Content quality gate."
        )
    if not receipt_path:
        raise ValueError(
            "A Content quality gate receipt is required. "
            "Run scripts/content_gate.py first."
        )
    receipt_path = Path(receipt_path)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Content quality receipt could not be read: {exc}") from exc
    expected_lang = receipt.get("report_lang") if lang == "auto" else lang
    errors = validate_content_receipt(
        input_path,
        ledger_path,
        receipt,
        expected_lang=expected_lang,
    )
    if errors:
        raise ValueError("Content quality production gate failed: " + " ".join(errors))


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
    ledger=None,
    content_receipt=None,
    keep_html=False,
    force=False,
):
    """Render one Markdown file and return the output PDF path."""
    input_path, output_path = validate_paths(input_path, output_path, force=force)
    validate_rewild_for_render(input_path, rewild_receipt, lang)
    validate_content_for_render(input_path, ledger, content_receipt, lang)
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
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}-",
        suffix=".pdf",
        dir=output_path.parent,
        delete=False,
    ) as temp_handle:
        temp_path = Path(temp_handle.name)
    try:
        HTML(
            string=rendered_html,
            base_url=input_path.parent.resolve(),
            url_fetcher=make_url_fetcher(input_path.parent),
        ).write_pdf(temp_path, pdf_tags=True)
        temp_path.replace(output_path)
        os.chmod(output_path, 0o644)
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
        "--ledger",
        required=True,
        help="evidence ledger bound to the exact final report",
    )
    parser.add_argument(
        "--content-receipt",
        required=True,
        help="passing Content quality receipt bound to the report and ledger",
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
            ledger=args.ledger,
            content_receipt=args.content_receipt,
            keep_html=args.keep_html,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
