"""Visual systems and deterministic template selection for Alexandria PDFs."""

import re
from dataclasses import dataclass


TEMPLATE_CHOICES = ("auto", "executive", "spectrum", "atlas", "horizon")


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    display_name: str
    accent: str
    dark: str
    muted: str
    pale: str
    display_serif: bool


TEMPLATES = {
    "executive": TemplateSpec(
        name="executive",
        display_name="Executive",
        accent="#16827c",
        dark="#123047",
        muted="#657483",
        pale="#edf3f4",
        display_serif=True,
    ),
    "spectrum": TemplateSpec(
        name="spectrum",
        display_name="Spectrum",
        accent="#4f46e5",
        dark="#191919",
        muted="#626262",
        pale="#f2f3ff",
        display_serif=False,
    ),
    "atlas": TemplateSpec(
        name="atlas",
        display_name="Atlas",
        accent="#2f7448",
        dark="#173d2a",
        muted="#748176",
        pale="#eef2ec",
        display_serif=True,
    ),
    "horizon": TemplateSpec(
        name="horizon",
        display_name="Horizon",
        accent="#0b63f6",
        dark="#0b0e14",
        muted="#617083",
        pale="#eef4ff",
        display_serif=False,
    ),
}


SPECTRUM_TERMS = {
    "ai", "artificial intelligence", "automation", "biotech", "blockchain",
    "cloud", "crypto", "cyber", "digital", "future", "innovation",
    "internet", "product", "robot", "robotics", "semiconductor", "software",
    "startup", "technology", "科技", "技术", "人工智能", "机器人", "機械人",
    "軟件", "软件", "创新", "創新", "产品", "產品", "数字", "數碼", "未来",
    "未來",
}

ATLAS_TERMS = {
    "anthropology", "archaeology", "architecture", "art", "biography",
    "climate", "culture", "ecology", "environment", "field", "geography",
    "heritage", "history", "landscape", "literature", "nature", "ocean",
    "person", "place", "psychology", "river", "science", "society",
    "人物", "传记", "傳記", "历史", "歷史", "文化", "艺术", "藝術", "地理",
    "环境", "環境", "气候", "氣候", "生态", "生態", "科学", "科學", "社会",
    "社會", "文学", "文學",
}

EXECUTIVE_TERMS = {
    "bank", "business", "company", "competition", "economy", "finance",
    "governance", "industry", "investment", "law", "leadership", "market",
    "organization", "policy", "regulation", "strategy", "公司", "企业", "企業",
    "商业", "商業", "市场", "市場", "金融", "投资", "投資", "政策", "法规",
    "法規", "产业", "產業", "战略", "策略", "组织", "組織", "管理",
}

HORIZON_TERMS = {
    "adaptation", "city", "climate", "climate risk", "defense", "energy",
    "geopolitics", "infrastructure", "logistics", "macro", "resilience",
    "security", "supply chain", "transport", "urban", "water",
    "基础设施", "基礎設施", "气候", "氣候", "能源", "韧性", "韌性", "供应链",
    "供應鏈", "地缘政治", "地緣政治", "物流", "城市", "交通", "水资源",
    "水資源", "安全",
}


def topic_match_count(subject_text, terms):
    """Count English terms as words and CJK terms as meaningful substrings."""
    score = 0
    for term in terms:
        if term.isascii():
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
            score += bool(re.search(pattern, subject_text))
        else:
            score += term in subject_text
    return score


def select_template(subject_text, requested="auto"):
    """Select an explicit template or adapt predictably from the report subject."""
    if requested not in TEMPLATE_CHOICES:
        raise ValueError(
            f"Unknown template '{requested}'. Choose from: {', '.join(TEMPLATE_CHOICES)}"
        )
    if requested != "auto":
        return requested

    normalized = subject_text.casefold()
    scores = {
        "executive": topic_match_count(normalized, EXECUTIVE_TERMS),
        "spectrum": topic_match_count(normalized, SPECTRUM_TERMS),
        "atlas": topic_match_count(normalized, ATLAS_TERMS),
        "horizon": topic_match_count(normalized, HORIZON_TERMS),
    }
    highest = max(scores.values())
    if highest == 0:
        return "executive"
    winners = [name for name, score in scores.items() if score == highest]
    return winners[0] if len(winners) == 1 else "executive"


def cover_art_html(template, cover_image=None):
    """Return decorative, non-text cover elements for one visual system."""
    image = (
        f'<img class="cover-photo" src="{cover_image}" alt="">'
        if cover_image
        else ""
    )
    if template == "executive":
        return """
        <div class="cover-art executive-art" aria-hidden="true">
            <span class="executive-rail"></span>
            <span class="executive-cross cross-a"></span>
            <span class="executive-cross cross-b"></span>
            <span class="executive-orbit"></span>
            <span class="executive-scale scale-a"></span>
            <span class="executive-scale scale-b"></span>
            <span class="executive-scale scale-c"></span>
        </div>
        """
    if template == "spectrum":
        return """
        <div class="cover-art spectrum-art" aria-hidden="true">
            <span class="ribbon ribbon-blue"></span>
            <span class="ribbon ribbon-violet"></span>
            <span class="ribbon ribbon-lime"></span>
            <span class="ribbon ribbon-orchid"></span>
            <span class="spectrum-target"><i></i></span>
        </div>
        """
    if template == "atlas":
        return f"""
        <div class="cover-art atlas-art" aria-hidden="true">
            {image}
            <span class="atlas-terrain"></span>
            <span class="atlas-bearing bearing-a"></span>
            <span class="atlas-bearing bearing-b"></span>
            <span class="atlas-axis axis-x"></span>
            <span class="atlas-axis axis-y"></span>
        </div>
        """
    return f"""
    <div class="cover-art horizon-art" aria-hidden="true">
        {image}
        <span class="horizon-landscape"></span>
        <span class="horizon-orbit orbit-a"></span>
        <span class="horizon-orbit orbit-b"></span>
        <span class="horizon-axis"></span>
        <span class="horizon-ticks"></span>
    </div>
    """


COMMON_CSS = """
@page {
    size: A4;
    margin: 21mm 18mm 19mm 18mm;

    @top-left {
        content: "ALEXANDRIA  /  DEEP RESEARCH";
        font-family: __FONT_SANS__;
        font-size: 7pt;
        font-weight: 700;
        letter-spacing: 1.25pt;
        color: __DARK__;
        border-bottom: 0.6pt solid __RULE__;
        padding-bottom: 3.2mm;
    }
    @top-right {
        content: "__HEADER__";
        font-family: __FONT_SANS__;
        font-size: 7pt;
        letter-spacing: 0.65pt;
        color: __MUTED__;
        border-bottom: 0.6pt solid __RULE__;
        padding-bottom: 3.2mm;
    }
    @bottom-left {
        content: "__FOOTER__";
        font-family: __FONT_SANS__;
        font-size: 6.6pt;
        letter-spacing: 0.7pt;
        color: __MUTED__;
        border-top: 0.5pt solid __RULE__;
        padding-top: 2.8mm;
    }
    @bottom-right {
        content: "__PAGE_LABEL__ " counter(page) "__PAGE_SUFFIX__";
        font-family: __FONT_SANS__;
        font-size: 7.5pt;
        font-weight: 700;
        color: __DARK__;
        border-top: 0.5pt solid __RULE__;
        padding-top: 2.8mm;
    }
}

@page :first {
    margin: 0;
    @top-left { content: none; }
    @top-right { content: none; }
    @bottom-left { content: none; }
    @bottom-right { content: none; }
}

@page toc {
    margin: 18mm;
    @top-left { content: "ALEXANDRIA  /  REPORT CONTENTS"; }
    @top-right { content: "__TEMPLATE_NAME__"; }
}

html, body {
    margin: 0;
    padding: 0;
}

body {
    font-family: __FONT_SANS__;
    font-size: 10.2pt;
    line-height: 1.62;
    color: __TEXT__;
    text-align: left;
}

.report {
    color: __TEXT__;
}

.cover {
    position: relative;
    box-sizing: border-box;
    width: 210mm;
    height: 297mm;
    padding: 18mm 18mm 16mm;
    overflow: hidden;
    page-break-after: always;
    background: #fff;
}

.cover-art {
    position: absolute;
    inset: 0;
    z-index: 0;
    overflow: hidden;
}

.cover-topline,
.cover-copy,
.cover-record,
.cover-confidential-note {
    position: relative;
    z-index: 2;
}

.cover-topline {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 5mm;
    border-bottom: 0.65pt solid __RULE__;
    font-family: __FONT_SANS__;
    font-size: 7.2pt;
    font-weight: 700;
    letter-spacing: 1.2pt;
    text-transform: uppercase;
    color: __DARK__;
}

.cover-copy {
    width: 77%;
    margin-top: 31mm;
}

.cover-kicker {
    margin-bottom: 8mm;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.55pt;
    text-transform: uppercase;
    color: __ACCENT__;
}

.cover h1 {
    margin: 0;
    padding: 0;
    border: 0;
    page-break-before: avoid;
    font-family: __FONT_DISPLAY__;
    font-size: 38pt;
    line-height: 1.03;
    letter-spacing: -1.1pt;
    font-weight: 700;
    color: __DARK__;
}

.cover-title-accent {
    display: table;
    margin-top: 4mm;
    padding: 3mm 5mm 4mm;
    max-width: 100%;
    box-sizing: border-box;
    font-family: __FONT_DISPLAY__;
    font-size: 27pt;
    line-height: 1.02;
    font-weight: 700;
}

.cover .subtitle {
    margin-top: 9mm;
    max-width: 125mm;
    font-size: 13pt;
    line-height: 1.45;
    color: __MUTED__;
}

.cover-record {
    position: absolute;
    left: 18mm;
    right: 18mm;
    bottom: 18mm;
    display: flex;
    flex-wrap: wrap;
    column-gap: 10mm;
    row-gap: 5mm;
    padding-top: 7mm;
    border-top: 0.8pt solid __DARK__;
}

.cover-record .meta-cell {
    flex: 1 1 72mm;
    min-width: 0;
    max-width: none;
    overflow-wrap: anywhere;
}

.meta-label {
    display: block;
    margin-bottom: 2mm;
    font-size: 6.8pt;
    font-weight: 700;
    letter-spacing: 1.1pt;
    text-transform: uppercase;
    color: __MUTED__;
}

.meta-value {
    display: block;
    font-size: 10.4pt;
    font-weight: 600;
    line-height: 1.28;
    color: __DARK__;
    overflow-wrap: anywhere;
}

.confidential-stamp {
    display: inline-block;
    padding: 1.5mm 2.7mm;
    border: 0.75pt solid __ACCENT__;
    font-size: 7.3pt;
    font-weight: 800;
    letter-spacing: 0.8pt;
    text-transform: uppercase;
    color: __DARK__;
}

.cover-confidential-note {
    position: absolute;
    left: 18mm;
    bottom: 8mm;
    font-size: 6.3pt;
    letter-spacing: 0.7pt;
    text-transform: uppercase;
    color: __MUTED__;
}

.toc-page {
    page: toc;
    page-break-after: always;
    min-height: 245mm;
}

.toc-kicker {
    margin-top: 10mm;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 1.5pt;
    text-transform: uppercase;
    color: __ACCENT__;
}

.toc-title {
    margin: 4mm 0 3mm;
    padding: 0;
    border: 0;
    page-break-before: avoid;
    font-family: __FONT_DISPLAY__;
    font-size: 31pt;
    line-height: 1.05;
    letter-spacing: -0.7pt;
    color: __DARK__;
}

.toc-intro {
    width: 74%;
    margin-bottom: 11mm;
    padding-bottom: 7mm;
    border-bottom: 0.7pt solid __RULE__;
    font-size: 10.5pt;
    line-height: 1.45;
    color: __MUTED__;
}

.toc-list {
    counter-reset: tocitem;
}

.toc-entry {
    counter-increment: tocitem;
    display: grid;
    grid-template-columns: 12mm 1fr 12mm;
    gap: 4mm;
    align-items: start;
    padding: 4.2mm 0 3.6mm;
    border-bottom: 0.45pt solid __RULE__;
    break-inside: avoid;
}

.toc-number::before {
    content: counter(tocitem, decimal-leading-zero);
    font-size: 7.5pt;
    font-weight: 800;
    letter-spacing: 0.7pt;
    color: __ACCENT__;
}

.toc-entry-title {
    display: block;
    font-size: 11.5pt;
    font-weight: 700;
    line-height: 1.25;
    color: __DARK__;
    text-decoration: none;
}

.toc-summary {
    display: block;
    margin-top: 1.2mm;
    max-width: 118mm;
    font-size: 8.2pt;
    line-height: 1.35;
    color: __MUTED__;
}

.toc-page-number {
    text-align: right;
    font-size: 8pt;
    font-weight: 700;
    color: __DARK__;
}

.toc-page-number::after {
    content: target-counter(attr(href), page);
}

.report-body {
    color: __TEXT__;
}

h1 {
    margin: 0 0 8mm;
    padding: 16mm 0 5mm;
    border-bottom: 1.4pt solid __DARK__;
    page-break-before: always;
    font-family: __FONT_DISPLAY__;
    font-size: 28pt;
    line-height: 1.08;
    letter-spacing: -0.65pt;
    color: __DARK__;
}

h2 {
    margin: 11mm 0 4mm;
    padding: 0 0 3.5mm;
    border-bottom: 0.8pt solid __RULE__;
    break-after: avoid;
    font-family: __FONT_DISPLAY__;
    font-size: 21pt;
    line-height: 1.12;
    letter-spacing: -0.35pt;
    color: __DARK__;
}

h2::before {
    content: "";
    display: block;
    width: 12mm;
    margin-bottom: 3mm;
    border-top: 2.2pt solid __ACCENT__;
}

h3 {
    margin: 8mm 0 2.5mm;
    break-after: avoid;
    font-size: 13pt;
    line-height: 1.25;
    font-weight: 700;
    color: __DARK__;
}

h4 {
    margin: 6mm 0 2mm;
    break-after: avoid;
    font-size: 10.5pt;
    font-weight: 800;
    letter-spacing: 0.35pt;
    text-transform: uppercase;
    color: __ACCENT__;
}

p {
    margin: 1.8mm 0;
    orphans: 3;
    widows: 3;
}

h1 + p,
h2 + p {
    margin-bottom: 5mm;
    max-width: 150mm;
    font-size: 11.4pt;
    line-height: 1.48;
    color: __MUTED__;
}

strong, b {
    color: __DARK__;
    font-weight: 700;
}

a {
    color: __LINK__;
    text-decoration: none;
    overflow-wrap: anywhere;
}

ul, ol {
    margin: 3mm 0;
    padding-left: 7mm;
}

li {
    margin: 1.5mm 0;
    padding-left: 1.2mm;
}

blockquote {
    margin: 6mm 0;
    padding: 5mm 6mm;
    background: __PALE__;
    color: __TEXT__;
    font-family: __FONT_DISPLAY__;
    font-size: 12pt;
    line-height: 1.45;
    break-inside: avoid;
}

blockquote p {
    margin: 0;
}

.metric-card,
.insight-panel,
.takeaway-band {
    break-inside: avoid;
}

.metric-card {
    display: inline-block;
    box-sizing: border-box;
    width: 54mm;
    margin: 5mm 0;
    padding: 5mm;
    background: __PALE__;
    vertical-align: top;
}

.metric-card p {
    margin: 0;
    color: __MUTED__;
    font-size: 8.5pt;
    line-height: 1.35;
}

.metric-value {
    margin-bottom: 2mm;
    font-family: __FONT_DISPLAY__;
    font-size: 27pt;
    font-weight: 700;
    line-height: 1;
    color: __DARK__;
}

.insight-panel {
    margin: 6mm 0;
    padding: 6mm 7mm;
    background: __DARK__;
    color: #fff;
    font-family: __FONT_DISPLAY__;
    font-size: 13pt;
    line-height: 1.42;
}

.insight-panel::before {
    content: "__INSIGHT_LABEL__";
    display: block;
    margin-bottom: 2.3mm;
    font-family: __FONT_SANS__;
    font-size: 6.8pt;
    font-weight: 800;
    letter-spacing: 1.1pt;
    text-transform: uppercase;
    color: __INSIGHT_ACCENT__;
}

.insight-panel p {
    margin: 0;
    color: inherit;
}

.insight-panel strong,
.insight-panel b {
    color: inherit;
}

.takeaway-band {
    margin: 7mm 0;
    padding: 5.5mm 7mm;
    background: __TAKEAWAY__;
    color: #fff;
    font-size: 11pt;
    font-weight: 600;
}

.takeaway-band::before {
    content: "__TAKEAWAY_LABEL__";
    display: block;
    margin-bottom: 2mm;
    font-size: 6.8pt;
    font-weight: 800;
    letter-spacing: 1.1pt;
    text-transform: uppercase;
    color: __TAKEAWAY_ACCENT__;
}

.takeaway-band p {
    margin: 0;
}

table {
    width: 100%;
    margin: 6mm 0;
    border-collapse: collapse;
    font-size: 8.8pt;
    line-height: 1.4;
    break-inside: auto;
}

thead {
    display: table-header-group;
}

thead th {
    padding: 3mm;
    background: __DARK__;
    color: #fff;
    text-align: left;
    font-size: 7.7pt;
    font-weight: 800;
    letter-spacing: 0.35pt;
}

tbody td {
    padding: 2.8mm 3mm;
    border-bottom: 0.45pt solid __RULE__;
    vertical-align: top;
}

tbody tr:nth-child(even) {
    background: __ROW__;
}

code {
    font-family: __FONT_MONO__;
    padding: 0.4mm 1.2mm;
    background: __PALE__;
    color: __DARK__;
    font-size: 9pt;
}

pre {
    margin: 5mm 0;
    padding: 4mm;
    border: 0.5pt solid __RULE__;
    background: __PALE__;
    font-family: __FONT_MONO__;
    font-size: 8.2pt;
    line-height: 1.45;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

pre code {
    padding: 0;
    background: transparent;
}

img {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 6mm auto;
}

hr {
    margin: 7mm 0;
    border: 0;
    border-top: 0.55pt solid __RULE__;
}
"""


RESPONSIVE_COVER_CSS = """
.cover.cover-title-long .cover-copy {
    width: 82%;
    margin-top: 19mm;
}
.cover.cover-title-long h1,
.cover.cover-title-long .cover-title-accent {
    font-size: 29pt !important;
    line-height: 1.04 !important;
}
.cover.cover-title-long .subtitle {
    margin-top: 5mm;
    font-size: 10.5pt;
    line-height: 1.38;
}
.cover.cover-title-very-long .cover-copy {
    width: 88%;
    margin-top: 12mm;
}
.cover.cover-title-very-long h1,
.cover.cover-title-very-long .cover-title-accent {
    font-size: 23pt !important;
    line-height: 1.05 !important;
}
.cover.cover-title-very-long .cover-kicker {
    margin-bottom: 5mm;
}
.cover.cover-title-very-long .subtitle {
    margin-top: 4mm;
    max-width: 150mm;
    font-size: 9.5pt;
    line-height: 1.32;
}
.cover.cover-title-long.cover-atlas .atlas-art {
    top: 151mm;
    height: 146mm;
}
.cover.cover-title-very-long.cover-atlas .atlas-art {
    top: 174mm;
    height: 123mm;
}
.cover.cover-title-long.cover-horizon .horizon-art {
    top: 163mm;
    height: 134mm;
}
.cover.cover-title-very-long.cover-horizon .horizon-art {
    top: 181mm;
    height: 116mm;
}
.cover.cover-meta-long .meta-value {
    font-size: 8.8pt;
    line-height: 1.22;
}
.cover.cover-horizon.cover-meta-3 .cover-record,
.cover.cover-horizon.cover-meta-4 .cover-record {
    left: 84mm;
    right: 18mm;
    bottom: 33mm;
    flex-direction: row;
    flex-wrap: wrap;
    column-gap: 6mm;
    row-gap: 5mm;
}
.cover.cover-horizon.cover-meta-3 .cover-record .meta-cell,
.cover.cover-horizon.cover-meta-4 .cover-record .meta-cell {
    flex: 1 1 43mm;
}
.cover.cover-horizon.cover-meta-long .cover-record {
    left: 82mm;
}
"""


TEMPLATE_CSS = {
    "executive": """
.template-executive .cover {
    border-left: 3mm solid #16827c;
}
.template-executive .cover-title-accent {
    background: #123047;
    color: #fff;
}
.executive-rail {
    position: absolute;
    right: 31mm;
    top: 111mm;
    width: 0.6pt;
    height: 76mm;
    background: #a8c4ca;
}
.executive-cross {
    position: absolute;
    width: 18mm;
    height: 18mm;
}
.executive-cross::before,
.executive-cross::after {
    content: "";
    position: absolute;
    background: #16827c;
}
.executive-cross::before {
    left: 9mm;
    top: 0;
    width: 0.6pt;
    height: 18mm;
}
.executive-cross::after {
    left: 0;
    top: 9mm;
    width: 18mm;
    height: 0.6pt;
}
.cross-a { right: 18mm; top: 16mm; }
.cross-b { right: 26mm; bottom: 16mm; transform: scale(0.7); }
.executive-orbit {
    position: absolute;
    right: 32mm;
    top: 63mm;
    width: 35mm;
    height: 35mm;
    border-top: 0.6pt solid #a8c4ca;
    border-right: 0.6pt solid #a8c4ca;
    border-radius: 0 35mm 0 0;
}
.executive-scale {
    position: absolute;
    right: 24mm;
    width: 34mm;
    height: 8mm;
    border-bottom: 0.55pt solid #a8c4ca;
}
.executive-scale::after {
    content: "";
    position: absolute;
    right: 0;
    bottom: -2.1mm;
    width: 4mm;
    height: 4mm;
    border: 0.7pt solid #16827c;
    border-radius: 50%;
    background: #fff;
}
.scale-a { top: 132mm; }
.scale-b { top: 150mm; }
.scale-c { top: 168mm; }
.template-executive .toc-title,
.template-executive h1,
.template-executive h2 {
    font-weight: 600;
}
""",
    "spectrum": """
.template-spectrum .cover {
    border-left: 0.5pt solid #d9dce5;
}
.template-spectrum .cover-copy {
    width: 64%;
}
.template-spectrum .cover h1 {
    font-size: 35pt;
    line-height: 1.08;
    font-weight: 500;
}
.template-spectrum .cover-title-accent {
    padding: 0;
    background: transparent;
    color: #191919;
    font-size: 35pt;
    font-weight: 500;
}
.template-spectrum .cover-record {
    padding: 7mm;
    background: #191919;
    border: 0;
    border-radius: 3mm;
}
.template-spectrum .cover-record .meta-label {
    color: #a7a7a7;
}
.template-spectrum .cover-record .meta-value {
    color: #fff;
}
.template-spectrum .confidential-stamp {
    border: 0;
    background: #c9ff17;
    color: #191919;
}
.ribbon {
    position: absolute;
    top: -28mm;
    right: -18mm;
    width: 18mm;
    height: 218mm;
    border-radius: 20mm;
    opacity: 0.82;
    transform-origin: center;
}
.ribbon-blue {
    right: 28mm;
    background: #1769ff;
    transform: rotate(17deg);
}
.ribbon-violet {
    right: 44mm;
    background: #6f35f2;
    transform: rotate(-24deg);
}
.ribbon-lime {
    right: 4mm;
    background: #c9ff17;
    transform: rotate(15deg);
}
.ribbon-orchid {
    right: 60mm;
    background: #d83fe9;
    transform: rotate(-33deg);
}
.spectrum-target {
    position: absolute;
    right: 23mm;
    bottom: 70mm;
    width: 20mm;
    height: 20mm;
    border: 3mm solid #1769ff;
    border-right-color: #c9ff17;
    border-bottom-color: #d83fe9;
    border-radius: 50%;
    background: #fff;
}
.spectrum-target i {
    position: absolute;
    left: 5mm;
    top: 5mm;
    width: 10mm;
    height: 10mm;
    border-radius: 50%;
    background: #191919;
}
.template-spectrum .toc-page {
    background-image:
        linear-gradient(to right, rgba(79,70,229,0.07) 0.35pt, transparent 0.35pt),
        linear-gradient(to bottom, rgba(79,70,229,0.045) 0.35pt, transparent 0.35pt);
    background-size: 33mm 33mm;
}
.template-spectrum h2::before {
    width: 8mm;
    border-top-width: 3pt;
    border-radius: 2mm;
}
.template-spectrum .insight-panel {
    border-radius: 2.5mm;
}
.template-spectrum .takeaway-band {
    background: linear-gradient(110deg, #b727cf, #1557e8);
    border-radius: 2.5mm;
}
.template-spectrum .metric-card {
    background: #191919;
    border-radius: 2.5mm;
}
.template-spectrum .metric-card p {
    color: #c8c8c8;
}
.template-spectrum .metric-value {
    color: #fff;
}
""",
    "atlas": """
.template-atlas .cover-copy {
    width: 76%;
    margin-top: 26mm;
}
.template-atlas .cover h1 {
    font-size: 35pt;
    font-weight: 600;
    color: #173d2a;
}
.template-atlas .cover-title-accent {
    padding: 0;
    background: transparent;
    color: #173d2a;
    font-size: 35pt;
    font-weight: 600;
}
.template-atlas .cover-record {
    left: 18mm;
    right: 18mm;
    bottom: 17mm;
    padding: 7mm;
    background: #173d2a;
    border: 0;
    border-radius: 2mm;
}
.template-atlas .cover-record .meta-label {
    color: #aebcaf;
}
.template-atlas .cover-record .meta-value {
    color: #fff;
}
.template-atlas .confidential-stamp {
    border: 0;
    background: #2f7448;
    color: #fff;
}
.atlas-art {
    top: 128mm;
    height: 169mm;
    background: #173d2a;
}
.cover-photo {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0.72;
}
.atlas-terrain {
    position: absolute;
    inset: 0;
    background:
        radial-gradient(ellipse at 18% 38%, transparent 0 16mm, rgba(238,242,236,0.2) 16.4mm 16.9mm, transparent 17.2mm),
        radial-gradient(ellipse at 78% 63%, transparent 0 25mm, rgba(238,242,236,0.18) 25.4mm 26mm, transparent 26.3mm),
        linear-gradient(135deg, rgba(47,116,72,0.45), rgba(23,61,42,0.86));
}
.atlas-bearing {
    position: absolute;
    right: 21mm;
    bottom: 42mm;
    width: 54mm;
    height: 54mm;
    border-top: 0.6pt solid rgba(255,255,255,0.62);
    border-right: 0.6pt solid rgba(255,255,255,0.62);
    border-radius: 0 54mm 0 0;
}
.bearing-b {
    right: 28mm;
    bottom: 49mm;
    width: 40mm;
    height: 40mm;
    opacity: 0.65;
}
.atlas-axis {
    position: absolute;
    background: rgba(255,255,255,0.54);
}
.axis-x {
    right: 18mm;
    bottom: 68mm;
    width: 72mm;
    height: 0.45pt;
}
.axis-y {
    right: 54mm;
    bottom: 31mm;
    width: 0.45pt;
    height: 72mm;
}
.template-atlas .toc-entry-title,
.template-atlas h1,
.template-atlas h2,
.template-atlas h3 {
    font-weight: 600;
}
.template-atlas img {
    border-bottom: 2pt solid #2f7448;
}
.template-atlas .metric-card {
    border-radius: 2mm;
}
""",
    "horizon": """
.template-horizon .cover-copy {
    width: 74%;
    margin-top: 27mm;
}
.template-horizon .cover h1 {
    font-size: 36pt;
    line-height: 1.04;
    font-weight: 650;
    color: #0b0e14;
}
.template-horizon .cover-title-accent {
    padding: 0;
    background: transparent;
    color: #0b0e14;
    font-size: 36pt;
    font-weight: 650;
}
.template-horizon .cover-record {
    left: 116mm;
    right: 18mm;
    bottom: 51mm;
    display: flex;
    flex-direction: column;
    gap: 5mm;
    padding: 7mm;
    background: #0b63f6;
    border: 0;
    border-radius: 1.5mm;
    box-shadow: 0 3mm 7mm rgba(11,14,20,0.26);
}
.template-horizon .cover-record .meta-cell {
    flex: 0 1 auto;
    min-width: 0;
    max-width: none;
}
.template-horizon .cover-record .meta-label {
    margin-bottom: 1mm;
    color: #bdd6ff;
}
.template-horizon .cover-record .meta-value {
    color: #fff;
}
.template-horizon .confidential-stamp {
    border-color: #fff;
    color: #fff;
}
.template-horizon .cover-confidential-note {
    color: #fff;
}
.horizon-art {
    top: 146mm;
    height: 151mm;
    background:
        linear-gradient(180deg, rgba(93,143,191,0.92), rgba(25,45,63,0.62) 54%, rgba(8,17,24,0.96)),
        linear-gradient(120deg, #9ec6e1, #ebc879 62%, #182d3a);
}
.horizon-art .cover-photo {
    opacity: 0.78;
}
.horizon-landscape {
    position: absolute;
    inset: 0;
    background:
        linear-gradient(166deg, transparent 0 53%, rgba(10,23,31,0.18) 53.5% 58%, rgba(7,16,22,0.76) 58.5%),
        linear-gradient(13deg, transparent 0 72%, rgba(255,215,120,0.20) 72.5% 74%, transparent 74.5%);
}
.horizon-orbit {
    position: absolute;
    left: 20mm;
    bottom: 26mm;
    width: 64mm;
    height: 64mm;
    border: 0.55pt solid rgba(255,255,255,0.48);
    border-radius: 50%;
}
.orbit-b {
    left: 31mm;
    bottom: 15mm;
    width: 93mm;
    height: 93mm;
}
.horizon-axis {
    position: absolute;
    left: 18mm;
    right: 18mm;
    bottom: 17mm;
    height: 0.5pt;
    background: rgba(255,255,255,0.6);
}
.horizon-ticks {
    position: absolute;
    left: 18mm;
    right: 18mm;
    bottom: 15.5mm;
    height: 3mm;
    background: repeating-linear-gradient(
        to right,
        rgba(255,255,255,0.7) 0 0.45pt,
        transparent 0.45pt 13mm
    );
}
.template-horizon .toc-kicker,
.template-horizon .toc-number::before {
    color: #0b63f6;
}
.template-horizon .toc-intro {
    border-bottom: 3pt solid #0b63f6;
}
.template-horizon h1,
.template-horizon h2 {
    font-weight: 650;
}
.template-horizon h2::before {
    width: 2mm;
    height: 10mm;
    border: 0;
    background: #0b63f6;
}
.template-horizon .metric-card {
    border: 0.7pt solid #d7dee8;
    background: #fff;
    box-shadow: 0 2mm 5mm rgba(11,14,20,0.12);
}
.template-horizon .insight-panel,
.template-horizon .takeaway-band {
    background: #0b63f6;
    box-shadow: 0 2mm 5mm rgba(11,14,20,0.15);
}
.template-horizon img {
    border-left: 3pt solid #0b63f6;
}
""",
}


def build_css(
    template,
    *,
    font_sans,
    font_display,
    font_mono,
    header_text,
    page_label,
    page_suffix,
    footer_text,
    insight_label,
    takeaway_label,
):
    """Build complete CSS for the selected template."""
    spec = TEMPLATES[template]
    values = {
        "__FONT_SANS__": font_sans,
        "__FONT_DISPLAY__": font_display,
        "__FONT_MONO__": font_mono,
        "__HEADER__": header_text,
        "__FOOTER__": footer_text,
        "__PAGE_LABEL__": page_label,
        "__PAGE_SUFFIX__": page_suffix,
        "__TEMPLATE_NAME__": spec.display_name.upper(),
        "__ACCENT__": spec.accent,
        "__DARK__": spec.dark,
        "__MUTED__": spec.muted,
        "__PALE__": spec.pale,
        "__TEXT__": "#233a2b" if template == "atlas" else "#172330",
        "__LINK__": spec.accent,
        "__RULE__": {
            "executive": "#c8d3d8",
            "spectrum": "#d9dce5",
            "atlas": "#cad4c8",
            "horizon": "#d7dee8",
        }[template],
        "__ROW__": "#f6f8f9" if template != "atlas" else "#f5f7f3",
        "__INSIGHT_LABEL__": insight_label,
        "__INSIGHT_ACCENT__": {
            "executive": "#7fd6cf",
            "spectrum": "#c9ff17",
            "atlas": "#b9d5bf",
            "horizon": "#dbeaff",
        }[template],
        "__TAKEAWAY_LABEL__": takeaway_label,
        "__TAKEAWAY__": spec.accent,
        "__TAKEAWAY_ACCENT__": {
            "executive": "#d7fffb",
            "spectrum": "#d9ff39",
            "atlas": "#d9eadc",
            "horizon": "#dbeaff",
        }[template],
    }
    css = COMMON_CSS
    for placeholder, value in values.items():
        css = css.replace(placeholder, value)
    return css + TEMPLATE_CSS[template] + RESPONSIVE_COVER_CSS
