"""Visual systems and deterministic template selection for Alexandria PDFs."""

import base64
import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


TEMPLATE_CHOICES = (
    "auto",
    "executive",
    "spectrum",
    "atlas",
    "horizon",
    "maison",
    "blueprint",
    "terrain",
    "orbit",
)


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
    "maison": TemplateSpec(
        name="maison",
        display_name="Maison",
        accent="#b39a61",
        dark="#1a1a1a",
        muted="#55514b",
        pale="#f4f2ef",
        display_serif=True,
    ),
    "blueprint": TemplateSpec(
        name="blueprint",
        display_name="Blueprint",
        accent="#4a9fd8",
        dark="#1a1a1a",
        muted="#666666",
        pale="#f7f8fa",
        display_serif=False,
    ),
    "terrain": TemplateSpec(
        name="terrain",
        display_name="Terrain",
        accent="#2d5e3a",
        dark="#1b3a28",
        muted="#4a6b52",
        pale="#f5f3ee",
        display_serif=False,
    ),
    "orbit": TemplateSpec(
        name="orbit",
        display_name="Orbit",
        accent="#0062ff",
        dark="#1a1a1a",
        muted="#4b5563",
        pale="#f7f8fa",
        display_serif=False,
    ),
}


SPECTRUM_TERMS = {
    "app", "brand", "consumer tech", "creator", "digital", "ecommerce",
    "entertainment", "future", "gaming", "innovation", "internet", "media",
    "platform", "product", "social", "startup", "streaming", "web3",
    "应用", "應用", "品牌", "消费科技", "消費科技", "创作者", "創作者",
    "数字", "數碼", "电商", "電商", "娱乐", "娛樂", "游戏", "遊戲",
    "创新", "創新", "互联网", "互聯網", "媒体", "媒體", "平台", "产品",
    "產品", "社交", "初创", "初創", "未来", "未來",
}

ATLAS_TERMS = {
    "anthropology", "archaeology", "architecture", "art", "biography",
    "culture", "field", "geography",
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

MAISON_TERMS = {
    "beauty", "consumer brand", "fashion", "food", "hospitality", "hotel",
    "interior", "luxury", "premium", "real estate", "restaurant", "retail",
    "service design", "travel", "wellness", "美妆", "美妝", "消费品牌",
    "消費品牌", "时尚", "時尚", "餐饮", "餐飲", "酒店", "室内", "室內",
    "奢侈品", "高端", "房地产", "房地產", "零售", "服务设计", "服務設計",
    "旅游", "旅遊", "健康生活",
}

BLUEPRINT_TERMS = {
    "architecture", "capability", "delivery model", "engineering",
    "enterprise transformation", "governance", "implementation",
    "operating model", "operations", "organization design", "process",
    "program management", "system design", "transformation", "workflow",
    "架构", "架構", "能力建设", "能力建設", "交付模式", "工程",
    "企业转型", "企業轉型", "治理", "实施", "實施", "运营模式", "營運模式",
    "运营", "營運", "组织设计", "組織設計", "流程", "项目管理", "項目管理",
    "系统设计", "系統設計", "转型", "轉型", "工作流",
}

TERRAIN_TERMS = {
    "agriculture", "biodiversity", "conservation", "ecosystem", "ecology",
    "environment", "forestry", "land use", "natural resources", "ocean",
    "rural", "soil", "watershed", "wetland", "wildlife", "农业", "農業",
    "生物多样性", "生物多樣性", "保育", "生态系统", "生態系統", "生态",
    "生態", "环境", "環境", "林业", "林業", "土地利用", "自然资源",
    "自然資源", "海洋", "乡村", "鄉村", "土壤", "流域", "湿地", "濕地",
    "野生动物", "野生動物",
}

ORBIT_TERMS = {
    "advanced computing", "aerospace", "ai", "artificial intelligence",
    "automation", "biotech", "cloud", "cyber", "data science", "deep tech",
    "machine learning", "quantum", "robot", "robotics", "semiconductor",
    "software infrastructure", "space", "人工智能", "自动化", "自動化",
    "生物科技", "云计算", "雲端運算", "网络安全", "網絡安全", "数据科学",
    "數據科學", "深科技", "机器学习", "機器學習", "量子", "机器人",
    "機械人", "半导体", "半導體", "软件基础设施", "軟件基礎設施", "航天",
}


TEMPLATE_TERM_SETS = {
    "executive": EXECUTIVE_TERMS,
    "spectrum": SPECTRUM_TERMS,
    "atlas": ATLAS_TERMS,
    "horizon": HORIZON_TERMS,
    "maison": MAISON_TERMS,
    "blueprint": BLUEPRINT_TERMS,
    "terrain": TERRAIN_TERMS,
    "orbit": ORBIT_TERMS,
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
        name: topic_match_count(normalized, terms)
        for name, terms in TEMPLATE_TERM_SETS.items()
    }
    highest = max(scores.values())
    if highest == 0:
        digest = hashlib.sha256(normalized.encode("utf-8")).digest()
        names = tuple(TEMPLATES)
        return names[int.from_bytes(digest[:2], "big") % len(names)]
    winners = [name for name, score in scores.items() if score == highest]
    if len(winners) == 1:
        return winners[0]
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return winners[int.from_bytes(digest[:2], "big") % len(winners)]


def select_adaptive_companion(subject_text):
    """Choose a non-default companion for the default two-PDF workflow."""
    selected = select_template(subject_text, "auto")
    if selected != "executive":
        return selected
    normalized = subject_text.casefold()
    candidates = tuple(name for name in TEMPLATES if name != "executive")
    scores = {
        name: topic_match_count(normalized, TEMPLATE_TERM_SETS[name])
        for name in candidates
    }
    highest = max(scores.values())
    winners = [name for name, score in scores.items() if score == highest]
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return winners[int.from_bytes(digest[:2], "big") % len(winners)]


@lru_cache(maxsize=8)
def bundled_template_image_data_uri(template):
    """Return a bundled editorial image as a portable embedded JPEG."""
    filenames = {
        "horizon": "horizon-landscape.jpg",
        "maison": "maison-interior.jpeg",
        "terrain": "terrain-aerial.jpeg",
        "orbit": "orbit-scientific.jpeg",
    }
    if template not in filenames:
        raise ValueError(f"Template '{template}' has no bundled image.")
    image_path = Path(__file__).resolve().parent.parent / "assets" / filenames[template]
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def bundled_horizon_image_data_uri():
    """Compatibility wrapper for Horizon's bundled landscape."""
    return bundled_template_image_data_uri("horizon")


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
    if template == "maison":
        photo = cover_image or bundled_template_image_data_uri("maison")
        return f"""
        <div class="cover-art maison-art" aria-hidden="true">
            <img class="cover-photo maison-photo" src="{photo}" alt="">
            <span class="maison-photo-shade"></span>
            <span class="maison-sector">GLOBAL PERSPECTIVE · RESEARCH SERIES</span>
            <span class="maison-folio">01</span>
        </div>
        """
    if template == "blueprint":
        return """
        <div class="cover-art blueprint-art" aria-hidden="true">
            <span class="blueprint-datum datum-a"></span>
            <span class="blueprint-datum datum-b"></span>
            <span class="blueprint-axis blueprint-axis-x"></span>
            <span class="blueprint-axis blueprint-axis-y"></span>
            <span class="blueprint-node node-a">A</span>
            <span class="blueprint-node node-b">B</span>
            <span class="blueprint-node node-c">C</span>
            <span class="blueprint-ruler"></span>
        </div>
        """
    if template == "terrain":
        photo = cover_image or bundled_template_image_data_uri("terrain")
        return f"""
        <div class="cover-art terrain-art" aria-hidden="true">
            <img class="cover-photo terrain-aerial" src="{photo}" alt="">
            <span class="terrain-wash"></span>
            <span class="terrain-grid"></span>
            <span class="terrain-contour contour-a"></span>
            <span class="terrain-contour contour-b"></span>
            <span class="terrain-datum">DATUM WGS 84 / ELEV. 1,274 M</span>
        </div>
        """
    if template == "orbit":
        return """
        <div class="cover-art orbit-art" aria-hidden="true">
            <span class="orbit-field"></span>
            <span class="orbit-ring ring-a"></span>
            <span class="orbit-ring ring-b"></span>
            <span class="orbit-ring ring-c"></span>
            <span class="orbit-vector"></span>
            <span class="orbit-node orbit-node-a">A</span>
            <span class="orbit-node orbit-node-b">B</span>
            <span class="orbit-node orbit-node-c">C</span>
            <span class="orbit-ruler"></span>
        </div>
        """
    horizon_image = cover_image or bundled_template_image_data_uri("horizon")
    return f"""
    <div class="cover-art horizon-art" aria-hidden="true">
        <img class="cover-photo" src="{horizon_image}" alt="">
        <span class="horizon-tonal-wash"></span>
        <span class="horizon-landscape"></span>
        <span class="horizon-figure-label">FIG. 01 / FIELD SYSTEMS / 37.8°N</span>
        <span class="horizon-orbit orbit-a"></span>
        <span class="horizon-orbit orbit-b"></span>
        <span class="horizon-diagonal"></span>
        <span class="horizon-axis"></span>
        <span class="horizon-ticks"></span>
        <span class="horizon-cover-folio">01 / 03</span>
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
    top: 143mm;
    height: 154mm;
}
.cover.cover-title-very-long.cover-horizon .horizon-art {
    top: 159mm;
    height: 138mm;
}
.cover.cover-title-long.cover-horizon .cover-copy {
    left: 16mm;
    top: 30mm;
    width: 178mm;
    margin: 0;
}
.cover.cover-title-long.cover-horizon h1,
.cover.cover-title-long.cover-horizon .cover-title-accent {
    font-size: 34pt !important;
    line-height: 1.01 !important;
}
.cover.cover-title-very-long.cover-horizon .cover-copy {
    left: 16mm;
    top: 27mm;
    width: 178mm;
    margin: 0;
}
.cover.cover-title-very-long.cover-horizon h1,
.cover.cover-title-very-long.cover-horizon .cover-title-accent {
    font-size: 28pt !important;
    line-height: 1.02 !important;
}
.cover.cover-title-long.cover-horizon .cover-record {
    top: 124mm;
}
.cover.cover-title-very-long.cover-horizon .cover-record {
    top: 140mm;
}
.cover.cover-meta-long .meta-value {
    font-size: 8.8pt;
    line-height: 1.22;
}
.cover.cover-horizon.cover-meta-3 .cover-record,
.cover.cover-horizon.cover-meta-4 .cover-record {
    left: auto;
    right: 16mm;
    top: 106mm;
    bottom: auto;
    width: 74mm;
    height: 78mm;
    flex-direction: column;
    flex-wrap: nowrap;
    gap: 2.2mm;
    padding: 5.5mm 6mm;
}
.cover.cover-horizon.cover-meta-3 .cover-record .meta-cell,
.cover.cover-horizon.cover-meta-4 .cover-record .meta-cell {
    flex: 0 0 auto;
}
.cover.cover-horizon.cover-meta-long .cover-record {
    left: auto;
}
.cover.cover-title-long.cover-horizon.cover-meta-3 .cover-record,
.cover.cover-title-long.cover-horizon.cover-meta-4 .cover-record {
    top: 120mm;
}
.cover.cover-title-very-long.cover-horizon.cover-meta-3 .cover-record,
.cover.cover-title-very-long.cover-horizon.cover-meta-4 .cover-record {
    top: 136mm;
}
"""

SHARED_REFERENCE_FEATURE_CSS = """
.toc-special-cont {
    page-break-before: always;
}
.horizon-feature-page {
    page: horizonfeature;
    position: relative;
    min-height: 245mm;
    page-break-after: always;
    color: __TEXT__;
}
.horizon-feature-running,
.horizon-feature-figure-label,
.horizon-feature-insight > span,
.horizon-feature-path > span {
    font-family: __FONT_MONO__;
    font-size: 6.8pt;
    font-weight: 700;
    letter-spacing: 1.1pt;
    text-transform: uppercase;
    color: __ACCENT__;
}
.horizon-feature-heading-row {
    display: grid;
    grid-template-columns: 1fr 48mm;
    gap: 12mm;
    align-items: end;
    margin: 8mm 0 8mm;
}
.horizon-feature-heading-row h2 {
    margin: 0;
    padding: 0;
    border: 0;
    font-size: 31pt;
    line-height: 1.04;
}
.horizon-feature-heading-row h2::before {
    display: none;
}
.horizon-feature-heading-row p {
    margin: 0;
    font-size: 9.4pt;
    line-height: 1.45;
    color: __MUTED__;
}
.horizon-feature-figure-label {
    margin: 0 0 2.5mm;
    color: __MUTED__;
}
.horizon-feature-photo {
    position: relative;
    height: 85mm;
    overflow: hidden;
    background: __PALE__;
}
.horizon-feature-photo img {
    width: 100%;
    height: 100%;
    margin: 0;
    border: 0;
    object-fit: cover;
}
.horizon-feature-datum {
    position: absolute;
    left: 9mm;
    top: 0;
    width: 2mm;
    height: 22mm;
    background: __ACCENT__;
}
.horizon-feature-insight {
    position: relative;
    z-index: 2;
    width: 82mm;
    min-height: 38mm;
    box-sizing: border-box;
    margin: -30mm 9mm 0 auto;
    padding: 6mm 7mm;
    background: __DARK__;
    color: #fff;
    box-shadow: 0 3mm 8mm rgba(0,0,0,0.22);
}
.horizon-feature-insight p {
    margin: 3mm 0 0;
    font-family: __FONT_DISPLAY__;
    font-size: 16pt;
    line-height: 1.18;
}
.horizon-feature-insight-long p {
    font-size: 12.5pt;
}
.horizon-feature-caption {
    width: 100mm;
    margin: 3mm 0 0;
    font-family: __FONT_MONO__;
    font-size: 6.3pt;
    line-height: 1.45;
    color: __MUTED__;
}
.horizon-feature-lower {
    display: grid;
    grid-template-columns: 1fr 67mm;
    gap: 14mm;
    margin-top: 10mm;
}
.horizon-feature-narrative h3 {
    margin: 0 0 4mm;
    font-size: 17pt;
}
.horizon-feature-narrative p {
    margin: 0;
    font-size: 9.2pt;
    line-height: 1.55;
}
.horizon-feature-path ol {
    margin: 3mm 0 0;
    padding: 0;
    list-style: none;
}
.horizon-feature-path li {
    display: grid;
    grid-template-columns: 8mm 1fr;
    gap: 2mm;
    padding: 2.3mm 0;
    border-bottom: 0.5pt solid __RULE__;
}
.horizon-feature-path li span {
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    color: __ACCENT__;
}
.horizon-feature-path li strong {
    font-size: 8.2pt;
    line-height: 1.3;
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
@page toc {
    margin: 18mm;
    @top-left {
        content: "DEEP RESEARCH  /  NAVIGATION";
        border-bottom: 0;
        color: #4b5563;
        font-family: __FONT_MONO__;
        font-size: 6.5pt;
        letter-spacing: 1pt;
    }
    @top-right {
        content: "ALEXANDRIA";
        border-bottom: 0;
        color: #9ca3af;
        font-family: __FONT_MONO__;
        font-size: 6.5pt;
        letter-spacing: 1pt;
    }
}

@page horizonfeature {
    margin: 18mm 18mm 17mm;
    @top-left {
        content: "FIELD NOTE 03  /  DECISION SIGNALS";
        border-bottom: 0;
        color: #4b5563;
        font-family: __FONT_MONO__;
        font-size: 6.5pt;
        letter-spacing: 1pt;
    }
    @top-right {
        content: "ALEXANDRIA  /  DEEP RESEARCH";
        border-bottom: 0;
        color: #9ca3af;
        font-family: __FONT_MONO__;
        font-size: 6.5pt;
        letter-spacing: 0.8pt;
    }
}

.template-horizon .cover {
    padding: 15mm 16mm 0;
}
.template-horizon .cover-topline {
    height: 8mm;
    padding: 0;
    border: 0;
    font-family: __FONT_MONO__;
    font-size: 6.7pt;
    letter-spacing: 1pt;
}
.horizon-firm-mark {
    display: flex;
    align-items: center;
    gap: 2.5mm;
    font-family: __FONT_SANS__;
    font-size: 9pt;
    font-weight: 500;
    letter-spacing: 0.8pt;
}
.horizon-firm-mark i {
    position: relative;
    display: inline-block;
    width: 6mm;
    height: 6mm;
    border-radius: 0.6mm;
    background: #101318;
}
.horizon-firm-mark i::after {
    content: "";
    position: absolute;
    left: 2.35mm;
    top: 1.1mm;
    width: 1.3mm;
    height: 3.8mm;
    border-radius: 0.3mm;
    background: #0062ff;
}
.horizon-firm-mark b {
    color: #101318;
    font-weight: 500;
    text-transform: uppercase;
}
.template-horizon .cover-copy {
    position: absolute;
    left: 16mm;
    top: 34mm;
    width: 168mm;
    margin: 0;
}
.template-horizon .cover-kicker {
    margin-bottom: 8mm;
    font-family: __FONT_MONO__;
    font-size: 7.2pt;
    font-weight: 600;
    letter-spacing: 1.35pt;
    color: #0062ff;
}
.template-horizon .cover h1 {
    max-width: 166mm;
    font-size: 44pt;
    line-height: 0.98;
    font-weight: 650;
    letter-spacing: -1.55pt;
    color: #101318;
}
.template-horizon .cover-title-accent {
    padding: 0;
    background: transparent;
    color: #101318;
    font-size: 44pt;
    line-height: 0.98;
    font-weight: 650;
    letter-spacing: -1.55pt;
}
.template-horizon .cover .subtitle {
    max-width: 112mm;
    margin-top: 10mm;
    color: #4b5563;
    font-size: 12.5pt;
    line-height: 1.42;
}
.template-horizon .cover-record {
    left: auto;
    right: 16mm;
    top: 110mm;
    bottom: auto;
    width: 58mm;
    height: 70mm;
    display: flex;
    flex-direction: column;
    flex-wrap: nowrap;
    justify-content: space-between;
    gap: 3mm;
    box-sizing: border-box;
    padding: 7mm 6.5mm 6mm;
    background: #0062ff;
    border: 0;
    border-radius: 1.6mm;
    box-shadow: 0 4mm 8mm rgba(16, 19, 24, 0.34);
}
.template-horizon .cover-record .meta-cell {
    flex: 0 0 auto;
    min-width: 0;
    max-width: 100%;
}
.template-horizon .cover-record .meta-label {
    margin-bottom: 1.2mm;
    color: rgba(255,255,255,0.72);
    font-family: __FONT_MONO__;
    font-size: 5.8pt;
    letter-spacing: 1pt;
}
.template-horizon .cover-record .meta-value {
    color: #fff;
    font-family: __FONT_SANS__;
    font-size: 11pt;
    line-height: 1.12;
    font-weight: 650;
}
.template-horizon .cover-meta-3 .cover-record,
.template-horizon .cover-meta-4 .cover-record {
    left: auto;
    right: 16mm;
    top: 106mm;
    bottom: auto;
    width: 74mm;
    height: 78mm;
    display: flex;
    flex-direction: column;
    flex-wrap: nowrap;
    gap: 2.2mm;
    padding: 5.5mm 6mm;
}
.template-horizon .cover-meta-3 .cover-record .meta-cell,
.template-horizon .cover-meta-4 .cover-record .meta-cell {
    flex: 0 0 auto;
}
.template-horizon .confidential-stamp {
    border-color: rgba(255,255,255,0.8);
    color: #fff;
    font-size: 6.2pt;
}
.template-horizon .cover-confidential-note {
    left: 16mm;
    bottom: 10mm;
    color: rgba(255,255,255,0.85);
    font-family: __FONT_MONO__;
    font-size: 5.8pt;
    z-index: 4;
}
.horizon-art {
    top: 129mm;
    height: 168mm;
    background: #182d3a;
}
.horizon-art .cover-photo {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    border: 0;
    object-fit: cover;
    opacity: 1;
}
.horizon-tonal-wash {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        180deg,
        rgba(16,19,24,0.02) 0%,
        rgba(16,19,24,0.06) 42%,
        rgba(16,19,24,0.64) 100%
    );
}
.horizon-landscape {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        164deg,
        transparent 0 61%,
        rgba(8,17,24,0.12) 61.3% 66%,
        rgba(8,17,24,0.34) 66.4%
    );
}
.horizon-figure-label,
.horizon-cover-folio {
    position: absolute;
    color: rgba(255,255,255,0.82);
    font-family: __FONT_MONO__;
    font-size: 5.7pt;
    font-weight: 600;
    letter-spacing: 0.9pt;
    text-transform: uppercase;
}
.horizon-figure-label {
    left: 16mm;
    top: 9mm;
}
.horizon-cover-folio {
    right: 16mm;
    bottom: 11mm;
}
.horizon-orbit {
    position: absolute;
    left: -8mm;
    bottom: 6mm;
    width: 102mm;
    height: 102mm;
    border: 0.45pt solid rgba(255,255,255,0.28);
    border-radius: 50%;
}
.orbit-b {
    left: 13mm;
    bottom: 17mm;
    width: 76mm;
    height: 76mm;
    border-color: rgba(255,255,255,0.20);
}
.horizon-diagonal {
    position: absolute;
    left: 10mm;
    bottom: 55mm;
    width: 96mm;
    height: 0.45pt;
    background: rgba(255,255,255,0.25);
    transform: rotate(-28deg);
    transform-origin: left center;
}
.horizon-axis {
    position: absolute;
    left: 16mm;
    right: 16mm;
    bottom: 7mm;
    height: 0.45pt;
    background: rgba(255,255,255,0.38);
}
.horizon-ticks {
    position: absolute;
    left: 16mm;
    right: 16mm;
    bottom: 5.5mm;
    height: 3mm;
    background: repeating-linear-gradient(
        to right,
        rgba(255,255,255,0.56) 0 0.45pt,
        transparent 0.45pt 14mm
    );
}

.toc-horizon {
    position: relative;
    box-sizing: border-box;
    height: 261mm;
    min-height: 261mm;
    padding: 0 0 61mm;
}
.toc-horizon .toc-kicker {
    margin-top: 7mm;
    font-family: __FONT_MONO__;
    font-size: 7pt;
    font-weight: 650;
    letter-spacing: 0.7pt;
    color: #0062ff;
}
.toc-horizon .toc-title {
    width: 102mm;
    margin: 4mm 0 12mm;
    font-size: 44pt;
    line-height: 0.96;
    font-weight: 650;
    letter-spacing: -1.45pt;
    color: #101318;
}
.toc-horizon .toc-intro {
    position: absolute;
    right: 0;
    top: 10mm;
    width: 60mm;
    margin: 0;
    padding: 0;
    border: 0;
    color: #4b5563;
    font-size: 9pt;
    line-height: 1.42;
}
.toc-horizon .toc-list::before {
    content: "RESEARCH SEQUENCE";
    display: block;
    margin-bottom: 3mm;
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 5.5pt;
    font-weight: 650;
    letter-spacing: 1pt;
}
.toc-horizon .toc-entry {
    display: grid;
    grid-template-columns: 9mm 1fr 9mm;
    gap: 4mm;
    align-items: center;
    min-height: 14mm;
    padding: 2.2mm 0;
    border-bottom: 0.45pt solid #edf0f4;
}
.toc-horizon .toc-number::before {
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 6.3pt;
}
.toc-horizon .toc-entry:first-child .toc-number::before {
    color: #0062ff;
}
.toc-horizon .toc-copy {
    display: grid;
    grid-template-columns: 55mm 1fr;
    gap: 5mm;
    align-items: center;
}
.toc-horizon .toc-entry-title {
    font-size: 10.5pt;
    line-height: 1.14;
    font-weight: 650;
    color: #101318;
}
.toc-horizon .toc-summary {
    margin: 0;
    max-width: none;
    color: #4b5563;
    font-size: 6.5pt;
    line-height: 1.3;
}
.toc-horizon .toc-page-number {
    font-family: __FONT_MONO__;
    font-size: 6.7pt;
    color: #101318;
}
.horizon-toc-band {
    position: absolute;
    left: -18mm;
    right: -18mm;
    bottom: 0;
    height: 58mm;
    box-sizing: border-box;
    padding: 12mm 18mm;
    overflow: hidden;
    background: linear-gradient(100deg, #0048c7, #0062ff);
    color: #fff;
}
.horizon-toc-band::before {
    content: "";
    position: absolute;
    left: 8mm;
    bottom: -20mm;
    width: 62mm;
    height: 62mm;
    border: 0.45pt solid rgba(255,255,255,0.18);
    border-radius: 50%;
}
.horizon-toc-route {
    display: block;
    margin-bottom: 5mm;
    color: rgba(255,255,255,0.72);
    font-family: __FONT_MONO__;
    font-size: 5.7pt;
    font-weight: 650;
    letter-spacing: 1pt;
    text-transform: uppercase;
}
.horizon-toc-band strong {
    position: relative;
    z-index: 1;
    display: block;
    width: 88mm;
    color: #fff;
    font-size: 19pt;
    line-height: 1.08;
    font-weight: 650;
    letter-spacing: -0.45pt;
}
.horizon-toc-scale {
    position: absolute;
    left: 18mm;
    right: 18mm;
    bottom: 9mm;
    height: 3mm;
    border-top: 0.45pt solid rgba(255,255,255,0.38);
    background: repeating-linear-gradient(
        to right,
        rgba(255,255,255,0.55) 0 0.45pt,
        transparent 0.45pt 16mm
    );
}
.horizon-reading-card {
    position: absolute;
    right: 0;
    bottom: 28mm;
    z-index: 2;
    width: 66mm;
    min-height: 48mm;
    box-sizing: border-box;
    padding: 6mm;
    border-radius: 1.6mm;
    background: #fff;
    box-shadow: 0 4mm 9mm rgba(16,19,24,0.22);
}
.horizon-reading-card span,
.horizon-reading-card small {
    display: block;
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 5.5pt;
    font-weight: 650;
    letter-spacing: 0.9pt;
    text-transform: uppercase;
}
.horizon-reading-card strong {
    display: block;
    margin: 4mm 0 5mm;
    color: #101318;
    font-size: 12pt;
    line-height: 1.22;
    font-weight: 650;
}
.horizon-reading-card small {
    color: #0062ff;
}
.toc-horizon-cont {
    padding-bottom: 0;
}
.toc-horizon-cont .toc-title {
    margin-bottom: 15mm;
    font-size: 31pt;
}

.horizon-feature-page {
    page: horizonfeature;
    position: relative;
    box-sizing: border-box;
    height: 260mm;
    page-break-after: always;
    color: #39424e;
}
.horizon-feature-running {
    display: none;
}
.horizon-feature-heading-row {
    display: grid;
    grid-template-columns: 1fr 52mm;
    gap: 15mm;
    align-items: start;
    margin-top: 8mm;
}
.horizon-feature-heading-row h2 {
    margin: 0;
    padding: 0;
    border: 0;
    font-size: 31pt;
    line-height: 1.02;
    font-weight: 650;
    letter-spacing: -0.9pt;
    color: #101318;
}
.horizon-feature-heading-row h2::before {
    display: none;
}
.horizon-feature-heading-row p {
    margin: 2mm 0 0;
    color: #4b5563;
    font-size: 8.3pt;
    line-height: 1.48;
}
.horizon-feature-figure-label {
    margin-top: 25mm;
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 5.5pt;
    font-weight: 650;
    letter-spacing: 0.9pt;
    text-transform: uppercase;
}
.horizon-feature-photo {
    position: relative;
    width: 210mm;
    height: 92mm;
    margin: 4mm -18mm 0;
    overflow: hidden;
    background: #182d3a;
}
.horizon-feature-photo img {
    width: 100%;
    height: 100%;
    margin: 0;
    border: 0;
    object-fit: cover;
    filter: saturate(0.72) brightness(0.78);
}
.horizon-feature-photo::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
        180deg,
        rgba(16,19,24,0.02),
        rgba(16,19,24,0.30)
    );
}
.horizon-feature-datum {
    position: absolute;
    left: 18mm;
    top: 0;
    z-index: 2;
    width: 2mm;
    height: 21mm;
    background: #0062ff;
}
.horizon-feature-insight {
    position: absolute;
    top: 105mm;
    right: 0;
    z-index: 3;
    width: 78mm;
    min-height: 49mm;
    box-sizing: border-box;
    padding: 6mm;
    border-radius: 1.6mm;
    background: #fff;
    box-shadow: 0 4mm 10mm rgba(16,19,24,0.24);
}
.horizon-feature-insight > span {
    display: block;
    margin-bottom: 4mm;
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 5.5pt;
    font-weight: 650;
    letter-spacing: 0.9pt;
    text-transform: uppercase;
}
.horizon-feature-insight p {
    margin: 0;
    color: #101318;
    font-size: 13pt;
    line-height: 1.18;
    font-weight: 650;
}
.horizon-feature-insight-long p {
    font-size: 10.6pt;
    line-height: 1.22;
}
.horizon-feature-insight strong {
    color: inherit;
}
.horizon-feature-caption {
    width: 88mm;
    margin: 4mm 0 0;
    color: #4b5563;
    font-family: __FONT_MONO__;
    font-size: 5.4pt;
    line-height: 1.45;
}
.horizon-feature-lower {
    display: grid;
    grid-template-columns: 1fr 52mm;
    gap: 15mm;
    margin-top: 15mm;
}
.horizon-feature-narrative h3 {
    margin: 0 0 5mm;
    color: #101318;
    font-size: 16pt;
    font-weight: 650;
}
.horizon-feature-narrative p {
    margin: 0;
    color: #39424e;
    font-size: 7.9pt;
    line-height: 1.5;
}
.horizon-feature-path > span {
    display: block;
    margin-bottom: 4mm;
    color: #9ca3af;
    font-family: __FONT_MONO__;
    font-size: 5.5pt;
    font-weight: 650;
    letter-spacing: 0.9pt;
    text-transform: uppercase;
}
.horizon-feature-path ol {
    margin: 0;
    padding: 0;
    list-style: none;
}
.horizon-feature-path li {
    display: grid;
    grid-template-columns: 8mm 1fr;
    gap: 3mm;
    margin: 0;
    padding: 3mm 0;
    border-bottom: 0.45pt solid #d9dee5;
}
.horizon-feature-path li span {
    color: #0062ff;
    font-family: __FONT_MONO__;
    font-size: 6pt;
    font-weight: 650;
}
.horizon-feature-path li strong {
    color: #101318;
    font-size: 7pt;
    line-height: 1.25;
    font-weight: 650;
}

.template-horizon h1,
.template-horizon h2,
.template-horizon h3 {
    font-weight: 650;
}
.template-horizon h2::before {
    width: 1.6mm;
    height: 7mm;
    border: 0;
    background: #0062ff;
}
.template-horizon .metric-card {
    border: 0;
    border-radius: 1.6mm;
    background: #fff;
    box-shadow: 0 3mm 7mm rgba(16,19,24,0.14);
}
.template-horizon .insight-panel,
.template-horizon .takeaway-band {
    border-radius: 1.6mm;
    background: #0062ff;
    box-shadow: 0 3mm 7mm rgba(16,19,24,0.16);
}
.template-horizon img {
    border-left: 2mm solid #0062ff;
}
""",
    "maison": """
@page toc {
    margin: 17mm 17mm 18mm;
    background: #f4f2ef;
    @top-left { content: "ALEXANDRIA  /  EDITORIAL RESEARCH"; border: 0; }
    @top-right { content: "MAISON"; border: 0; }
}
.template-maison .cover {
    padding: 16mm 17mm;
    background: #f4f2ef;
}
.template-maison .cover-topline {
    color: #fff;
    border-color: rgba(255,255,255,0.48);
}
.maison-art {
    inset: 0 0 auto;
    height: 96mm;
}
.maison-art .maison-photo {
    opacity: 1;
}
.maison-photo-shade {
    position: absolute;
    inset: 0;
    background: linear-gradient(to bottom, rgba(0,0,0,0.28), transparent 58%, rgba(0,0,0,0.22));
}
.maison-sector,
.maison-folio {
    position: absolute;
    bottom: 7mm;
    z-index: 2;
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    letter-spacing: 1.1pt;
    color: #fff;
}
.maison-sector { left: 17mm; }
.maison-folio { right: 17mm; font-size: 8pt; }
.template-maison .cover-copy {
    width: 176mm;
    margin: 97mm auto 0;
    text-align: center;
}
.template-maison .cover-kicker {
    margin-bottom: 6mm;
    color: #b39a61;
}
.template-maison .cover h1,
.template-maison .cover-title-accent {
    display: block;
    padding: 0;
    background: transparent;
    color: #1a1a1a;
    font-size: 42pt;
    font-weight: 500;
    line-height: 0.98;
}
.template-maison .cover .subtitle {
    max-width: 128mm;
    margin: 7mm auto 0;
    font-size: 11pt;
}
.template-maison .cover-record {
    left: 17mm;
    right: 17mm;
    bottom: 15mm;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    border-color: #c9c1b5;
}
.template-maison .cover-record .meta-cell {
    min-width: 0;
}
.toc-maison {
    position: relative;
    background: #f4f2ef;
}
.toc-maison .toc-title {
    margin: 0 0 10mm -2mm;
    font-size: 63pt;
    font-weight: 500;
    letter-spacing: -2pt;
}
.toc-maison .toc-intro {
    width: 44mm;
    border: 0;
    font-family: __FONT_DISPLAY__;
    font-size: 12pt;
}
.maison-toc-note {
    position: absolute;
    left: 0;
    top: 82mm;
    width: 48mm;
    min-height: 94mm;
    padding-top: 5mm;
    border-top: 0.7pt solid #b39a61;
}
.maison-toc-note span,
.maison-toc-note strong {
    display: block;
}
.maison-toc-note span {
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    letter-spacing: 1pt;
    text-transform: uppercase;
    color: #b39a61;
}
.maison-toc-note strong {
    margin-top: 5mm;
    font-family: __FONT_DISPLAY__;
    font-size: 16pt;
    line-height: 1.25;
}
.toc-maison .toc-list {
    margin: -18mm 0 0 62mm;
}
.toc-maison .toc-entry {
    grid-template-columns: 10mm 1fr 10mm;
}
.toc-maison .toc-entry-title {
    font-family: __FONT_DISPLAY__;
    font-size: 15pt;
    font-weight: 500;
}
.maison-feature-photo {
    filter: saturate(0.78) contrast(0.95);
}
.maison-feature-insight {
    background: #1a1a1a;
}
.template-maison h1,
.template-maison h2,
.template-maison h3 {
    font-weight: 500;
}
.template-maison .insight-panel {
    background: #1a1a1a;
}
""",
    "blueprint": """
@page toc {
    margin: 17mm;
    @top-left { content: "ALEXANDRIA  /  SYSTEM MAP"; border: 0; }
    @top-right { content: "BLUEPRINT"; border: 0; }
}
.template-blueprint .cover {
    padding: 15mm 17mm;
    background:
        linear-gradient(to right, rgba(74,159,216,0.10) 0.35pt, transparent 0.35pt),
        linear-gradient(to bottom, rgba(74,159,216,0.08) 0.35pt, transparent 0.35pt),
        #fff;
    background-size: 24mm 24mm;
}
.template-blueprint .cover-copy {
    width: 170mm;
    margin-top: 26mm;
}
.template-blueprint .cover h1,
.template-blueprint .cover-title-accent {
    padding: 0;
    background: transparent;
    color: #1a1a1a;
    font-size: 38pt;
    font-weight: 760;
    line-height: 1.02;
}
.template-blueprint .cover-title-accent {
    display: inline-block;
    margin-top: 3mm;
    padding: 2mm 4mm;
    background: #1a1a1a;
    color: #fff;
}
.template-blueprint .cover .subtitle {
    width: 116mm;
}
.blueprint-art {
    inset: 105mm 17mm 42mm;
    border: 0.7pt solid #4a9fd8;
}
.blueprint-datum {
    position: absolute;
    border: 0.7pt solid #4a9fd8;
}
.datum-a { left: 14mm; top: 18mm; width: 48mm; height: 42mm; }
.datum-b { right: 14mm; bottom: 18mm; width: 54mm; height: 45mm; }
.blueprint-axis {
    position: absolute;
    background: #4a9fd8;
}
.blueprint-axis-x { left: 0; top: 50%; width: 100%; height: 0.5pt; }
.blueprint-axis-y { left: 50%; top: 0; width: 0.5pt; height: 100%; }
.blueprint-node {
    position: absolute;
    width: 19mm;
    height: 19mm;
    padding-top: 5mm;
    box-sizing: border-box;
    border: 0.7pt solid #4a9fd8;
    border-radius: 50%;
    background: #fff;
    text-align: center;
    font-family: __FONT_MONO__;
    font-size: 7pt;
    color: #1a1a1a;
}
.node-a { left: 22mm; top: 29mm; }
.node-b { left: 78mm; top: 63mm; }
.node-c { right: 24mm; bottom: 31mm; }
.blueprint-ruler,
.orbit-ruler {
    position: absolute;
    left: 8mm;
    right: 8mm;
    bottom: 6mm;
    height: 3mm;
    border-top: 0.6pt solid #4a9fd8;
    background: repeating-linear-gradient(to right, #4a9fd8 0 0.5pt, transparent 0.5pt 7mm);
}
.template-blueprint .cover-record {
    background: #fff;
}
.toc-blueprint {
    background:
        linear-gradient(to right, rgba(74,159,216,0.08) 0.35pt, transparent 0.35pt),
        linear-gradient(to bottom, rgba(74,159,216,0.07) 0.35pt, transparent 0.35pt);
    background-size: 30mm 30mm;
}
.toc-blueprint .toc-title {
    font-size: 43pt;
    font-weight: 760;
}
.blueprint-toc-map {
    display: grid;
    grid-template-columns: auto 1fr auto 1fr auto;
    gap: 3mm;
    align-items: center;
    margin: 0 0 8mm;
    padding: 4mm;
    border: 0.7pt solid #4a9fd8;
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    letter-spacing: 0.8pt;
}
.blueprint-toc-map i {
    height: 0.5pt;
    background: #4a9fd8;
}
.blueprint-feature-page {
    background:
        linear-gradient(to right, rgba(74,159,216,0.07) 0.35pt, transparent 0.35pt),
        #fff;
    background-size: 30mm 30mm;
}
.blueprint-feature-photo {
    border: 0.7pt solid #4a9fd8;
    filter: grayscale(1) contrast(1.1);
}
.blueprint-feature-photo img {
    width: 195%;
    max-width: none;
    object-position: left center;
}
.blueprint-feature-insight {
    background: #1a1a1a;
    border-radius: 0;
}
.template-blueprint h1,
.template-blueprint h2,
.template-blueprint h3 {
    font-weight: 720;
}
""",
    "terrain": """
@page toc {
    margin: 17mm;
    background: #f5f3ee;
    @top-left { content: "ALEXANDRIA  /  FIELD INDEX"; border: 0; }
    @top-right { content: "TERRAIN"; border: 0; }
}
.template-terrain .cover {
    padding: 16mm 17mm;
    background: #f5f3ee;
}
.terrain-art {
    inset: 0 0 auto;
    height: 166mm;
    background: #1b3a28;
}
.terrain-art .terrain-aerial {
    opacity: 1;
}
.terrain-wash {
    position: absolute;
    inset: 0;
    background: linear-gradient(to bottom, rgba(15,45,28,0.12), rgba(15,45,28,0.64));
}
.terrain-grid {
    position: absolute;
    inset: 0;
    background:
        linear-gradient(to right, rgba(255,255,255,0.22) 0.4pt, transparent 0.4pt),
        linear-gradient(to bottom, rgba(255,255,255,0.18) 0.4pt, transparent 0.4pt);
    background-size: 40mm 40mm;
}
.terrain-contour {
    position: absolute;
    border: 0.7pt solid rgba(255,255,255,0.55);
    border-radius: 50%;
}
.contour-a { left: 18mm; bottom: 13mm; width: 68mm; height: 68mm; }
.contour-b { left: 31mm; bottom: 26mm; width: 42mm; height: 42mm; }
.terrain-datum {
    position: absolute;
    left: 17mm;
    bottom: 8mm;
    font-family: __FONT_MONO__;
    font-size: 6.2pt;
    letter-spacing: 0.9pt;
    color: #fff;
}
.template-terrain .cover-topline {
    color: #fff;
    border-color: rgba(255,255,255,0.5);
}
.template-terrain .cover-copy {
    width: 174mm;
    margin-top: 28mm;
}
.template-terrain .cover h1,
.template-terrain .cover-title-accent {
    display: block;
    padding: 0;
    background: transparent;
    color: #fff;
    font-size: 39pt;
    font-weight: 650;
}
.template-terrain .cover .subtitle {
    max-width: 126mm;
    color: #e6eee7;
}
.template-terrain .cover-record {
    bottom: 17mm;
    padding: 8mm;
    border: 0;
    background: #f5f3ee;
}
.toc-terrain .toc-title {
    font-size: 42pt;
    color: #1b3a28;
}
.terrain-toc-map {
    position: relative;
    height: 50mm;
    margin: 0 0 7mm;
    overflow: hidden;
    background: #1b3a28;
}
.terrain-toc-map img {
    width: 100%;
    height: 100%;
    margin: 0;
    border: 0;
    object-fit: cover;
    opacity: 0.64;
}
.terrain-toc-map span {
    position: absolute;
    left: 5mm;
    top: 5mm;
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    letter-spacing: 1pt;
    color: #fff;
}
.toc-terrain .toc-entry-title {
    font-size: 12.5pt;
    color: #1b3a28;
}
.terrain-feature-photo {
    border-bottom: 3mm solid #1b3a28;
}
.terrain-feature-insight {
    background: #1b3a28;
}
.template-terrain h1,
.template-terrain h2,
.template-terrain h3 {
    color: #1b3a28;
}
""",
    "orbit": """
@page toc {
    margin: 17mm;
    @top-left { content: "ALEXANDRIA  /  ORIENTATION"; border: 0; }
    @top-right { content: "ORBIT"; border: 0; }
}
.template-orbit .cover {
    padding: 15mm 17mm;
    background: #fff;
}
.template-orbit .cover-copy {
    width: 176mm;
    margin-top: 26mm;
}
.template-orbit .cover h1,
.template-orbit .cover-title-accent {
    display: block;
    padding: 0;
    background: transparent;
    color: #1a1a1a;
    font-size: 40pt;
    font-weight: 760;
    line-height: 1;
}
.template-orbit .cover .subtitle {
    max-width: 122mm;
    font-size: 11pt;
}
.orbit-art {
    inset: 116mm 0 57mm;
}
.orbit-field {
    position: absolute;
    inset: 0;
    background: #0062ff;
}
.orbit-ring {
    position: absolute;
    border: 0.65pt solid rgba(255,255,255,0.58);
    border-radius: 50%;
}
.ring-a { left: 20mm; top: 12mm; width: 88mm; height: 88mm; }
.ring-b { left: 39mm; top: 31mm; width: 50mm; height: 50mm; }
.ring-c { right: 22mm; top: 14mm; width: 72mm; height: 72mm; }
.orbit-vector {
    position: absolute;
    left: 15mm;
    top: 50%;
    width: 176mm;
    height: 0.6pt;
    background: rgba(255,255,255,0.62);
    transform: rotate(-13deg);
}
.orbit-node {
    position: absolute;
    width: 8mm;
    height: 8mm;
    padding-top: 2mm;
    box-sizing: border-box;
    border-radius: 50%;
    background: #fff;
    text-align: center;
    font-family: __FONT_MONO__;
    font-size: 6pt;
    color: #0062ff;
}
.orbit-node-a { left: 32mm; top: 26mm; }
.orbit-node-b { left: 91mm; top: 61mm; }
.orbit-node-c { right: 39mm; top: 32mm; }
.orbit-art .orbit-ruler {
    border-color: rgba(255,255,255,0.74);
    background: repeating-linear-gradient(to right, #fff 0 0.5pt, transparent 0.5pt 8mm);
}
.template-orbit .cover-record {
    bottom: 14mm;
}
.toc-orbit {
    position: relative;
    background: #0062ff;
}
.toc-orbit::before {
    content: "";
    position: absolute;
    z-index: 0;
    left: 0;
    top: 0;
    bottom: 0;
    width: 37%;
    background: #fff;
}
.toc-orbit::after {
    content: "";
    position: absolute;
    z-index: 0;
    right: 14mm;
    bottom: 20mm;
    width: 78mm;
    height: 78mm;
    border: 0.6pt solid rgba(255,255,255,0.46);
    border-radius: 50%;
}
.toc-orbit > * {
    position: relative;
    z-index: 1;
}
.toc-orbit .toc-kicker,
.toc-orbit .toc-title,
.toc-orbit .toc-intro {
    width: 55mm;
}
.toc-orbit .toc-title {
    font-size: 40pt;
}
.orbit-toc-field {
    position: absolute;
    right: 8mm;
    top: 24mm;
    width: 91mm;
    height: 49mm;
    color: #fff;
}
.orbit-toc-field strong {
    position: relative;
    z-index: 2;
    font-family: __FONT_MONO__;
    font-size: 7pt;
    letter-spacing: 1pt;
}
.orbit-toc-ring {
    position: absolute;
    right: 0;
    top: -11mm;
    width: 50mm;
    height: 50mm;
    border: 0.6pt solid rgba(255,255,255,0.6);
    border-radius: 50%;
}
.toc-orbit .toc-list {
    margin-left: 61mm;
    color: #fff;
}
.toc-orbit .toc-entry {
    border-color: rgba(255,255,255,0.38);
    padding: 2.5mm 0 2mm;
}
.toc-orbit .toc-entry-title,
.toc-orbit .toc-page-number {
    color: #fff;
}
.toc-orbit .toc-summary {
    margin-top: 0.6mm;
    font-size: 7.5pt;
    line-height: 1.25;
    color: #dbe7ff;
}
.orbit-feature-photo {
    border: 0;
}
.orbit-feature-photo img {
    width: 195%;
    max-width: none;
    object-position: left center;
}
.orbit-feature-insight {
    background: #0062ff;
    border-radius: 1.5mm;
}
.template-orbit h1,
.template-orbit h2,
.template-orbit h3 {
    font-weight: 720;
}
.template-orbit .insight-panel,
.template-orbit .takeaway-band {
    background: #0062ff;
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
        "__TEXT__": {
            "atlas": "#233a2b",
            "terrain": "#233a2b",
            "maison": "#2b2926",
        }.get(template, "#172330"),
        "__LINK__": spec.accent,
        "__RULE__": {
            "executive": "#c8d3d8",
            "spectrum": "#d9dce5",
            "atlas": "#cad4c8",
            "horizon": "#d7dee8",
            "maison": "#d8d2c8",
            "blueprint": "#d8e7f0",
            "terrain": "#d6ddd0",
            "orbit": "#d8e2f2",
        }[template],
        "__ROW__": {
            "atlas": "#f5f7f3",
            "terrain": "#f5f3ee",
            "maison": "#f4f2ef",
            "blueprint": "#f7f8fa",
            "orbit": "#f7f8fa",
        }.get(template, "#f6f8f9"),
        "__INSIGHT_LABEL__": insight_label,
        "__INSIGHT_ACCENT__": {
            "executive": "#7fd6cf",
            "spectrum": "#c9ff17",
            "atlas": "#b9d5bf",
            "horizon": "#dbeaff",
            "maison": "#e6d9bc",
            "blueprint": "#d9effc",
            "terrain": "#a8ccaf",
            "orbit": "#dbe7ff",
        }[template],
        "__TAKEAWAY_LABEL__": takeaway_label,
        "__TAKEAWAY__": spec.accent,
        "__TAKEAWAY_ACCENT__": {
            "executive": "#d7fffb",
            "spectrum": "#d9ff39",
            "atlas": "#d9eadc",
            "horizon": "#dbeaff",
            "maison": "#f2e8d2",
            "blueprint": "#d9effc",
            "terrain": "#d6e4d8",
            "orbit": "#dbe7ff",
        }[template],
    }
    css = COMMON_CSS
    for placeholder, value in values.items():
        css = css.replace(placeholder, value)
    shared_feature = (
        SHARED_REFERENCE_FEATURE_CSS
        if template in {"maison", "blueprint", "terrain", "orbit"}
        else ""
    )
    return css + shared_feature + TEMPLATE_CSS[template] + RESPONSIVE_COVER_CSS
