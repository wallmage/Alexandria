"""Visual systems and deterministic template selection for Alexandria PDFs."""

import base64
import hashlib
import html
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
    "sunbeam",
    "current",
    "apricot",
)

FONT_ROOT = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Optional bundled CJK faces. Alexandria cannot redistribute Apple's PingFang
# or Songti, and no OFL CJK face is vendored by default because a full Noto
# CJK pair is ~40MB. Drop the files below into assets/fonts/ and every zh
# render becomes host-independent; without them the host stack is used and
# scripts/pdf_quality.check_cjk_fonts() fails loudly if the render mixes
# Simplified and Traditional faces. See references/pdf-production.md.
CJK_FONT_FILES = {
    "zh-CN": ("Alexandria CJK SC", "AlexandriaCJK-SC.ttf"),
    "zh-HK": ("Alexandria CJK TC", "AlexandriaCJK-TC.ttf"),
}


def bundled_cjk_font_path(lang):
    """Return the bundled CJK font file for a locale, or None."""
    entry = CJK_FONT_FILES.get(lang)
    if not entry:
        return None
    path = FONT_ROOT / entry[1]
    return path if path.is_file() else None


def bundled_cjk_font_family(lang):
    """Return the bundled CJK family name for a locale, or None."""
    entry = CJK_FONT_FILES.get(lang)
    if entry and bundled_cjk_font_path(lang):
        return entry[0]
    return None


def _cjk_font_faces():
    faces = []
    for family, filename in CJK_FONT_FILES.values():
        path = FONT_ROOT / filename
        if not path.is_file():
            continue
        faces.append(
            "@font-face {\n"
            f'    font-family: "{family}";\n'
            f'    src: url("{path.as_uri()}") format("truetype");\n'
            "    font-weight: 100 900;\n"
            "    font-style: normal;\n"
            "}\n"
        )
    return "".join(faces)


BUNDLED_FONT_CSS = f"""
@font-face {{
    font-family: "Alexandria Sans";
    src: url("{(FONT_ROOT / "SourceSans3.ttf").as_uri()}") format("truetype");
    font-weight: 200 900;
    font-style: normal;
}}
@font-face {{
    font-family: "Alexandria Serif";
    src: url("{(FONT_ROOT / "SourceSerif4.ttf").as_uri()}") format("truetype");
    font-weight: 200 900;
    font-style: normal;
}}
@font-face {{
    font-family: "Alexandria Mono";
    src: url("{(FONT_ROOT / "SourceCodePro.ttf").as_uri()}") format("truetype");
    font-weight: 200 900;
    font-style: normal;
}}
{_cjk_font_faces()}"""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    display_name: str
    accent: str
    accent_text: str
    dark: str
    muted: str
    pale: str
    display_serif: bool


TEMPLATES = {
    "executive": TemplateSpec(
        name="executive",
        display_name="Executive",
        accent="#16827c",
        accent_text="#147772",
        dark="#123047",
        muted="#657483",
        pale="#edf3f4",
        display_serif=True,
    ),
    "spectrum": TemplateSpec(
        name="spectrum",
        display_name="Spectrum",
        accent="#4f46e5",
        accent_text="#4f46e5",
        dark="#191919",
        muted="#626262",
        pale="#f2f3ff",
        display_serif=False,
    ),
    "atlas": TemplateSpec(
        name="atlas",
        display_name="Atlas",
        accent="#2f7448",
        accent_text="#2f7448",
        dark="#173d2a",
        muted="#687469",
        pale="#eef2ec",
        display_serif=True,
    ),
    "horizon": TemplateSpec(
        name="horizon",
        display_name="Horizon",
        accent="#0b63f6",
        accent_text="#0b63f6",
        dark="#0b0e14",
        muted="#617083",
        pale="#eef4ff",
        display_serif=False,
    ),
    "maison": TemplateSpec(
        name="maison",
        display_name="Maison",
        accent="#b39a61",
        accent_text="#766329",
        dark="#1a1a1a",
        muted="#55514b",
        pale="#f4f2ef",
        display_serif=True,
    ),
    "blueprint": TemplateSpec(
        name="blueprint",
        display_name="Blueprint",
        accent="#4a9fd8",
        accent_text="#17638d",
        dark="#1a1a1a",
        muted="#666666",
        pale="#f7f8fa",
        display_serif=False,
    ),
    "terrain": TemplateSpec(
        name="terrain",
        display_name="Terrain",
        accent="#2d5e3a",
        accent_text="#2d5e3a",
        dark="#1b3a28",
        muted="#4a6b52",
        pale="#f5f3ee",
        display_serif=False,
    ),
    "orbit": TemplateSpec(
        name="orbit",
        display_name="Orbit",
        accent="#0062ff",
        accent_text="#0062ff",
        dark="#1a1a1a",
        muted="#4b5563",
        pale="#f7f8fa",
        display_serif=False,
    ),
    "sunbeam": TemplateSpec(
        name="sunbeam",
        display_name="Sunbeam",
        accent="#ff6b35",
        accent_text="#a93612",
        dark="#151515",
        muted="#6e6a63",
        pale="#fff2c7",
        display_serif=True,
    ),
    "current": TemplateSpec(
        name="current",
        display_name="Current",
        accent="#ff5c00",
        accent_text="#a63c00",
        dark="#1a1a1a",
        muted="#666666",
        pale="#fff4ec",
        display_serif=False,
    ),
    "apricot": TemplateSpec(
        name="apricot",
        display_name="Apricot",
        accent="#ff9800",
        accent_text="#8f5000",
        dark="#1a1a1a",
        muted="#6e6a63",
        pale="#fff3e6",
        display_serif=True,
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

SUNBEAM_TERMS = {
    "civic participation", "community education", "community initiative",
    "creative economy", "entrepreneurship", "public engagement", "social impact",
    "youth", "youth development", "青年", "青年发展", "青年發展", "创业",
    "創業", "社区教育", "社區教育", "公众参与", "公眾參與", "社会影响",
    "社會影響", "创意经济", "創意經濟",
}

CURRENT_TERMS = {
    "change management", "circular economy", "customer journey",
    "future of work", "innovation program", "mobility", "service innovation",
    "service operations", "work redesign", "变革管理", "變革管理", "循环经济",
    "循環經濟", "客户旅程", "客戶旅程", "未来工作", "未來工作", "创新项目",
    "創新項目", "出行", "流动性", "流動性", "服务创新", "服務創新",
}

APRICOT_TERMS = {
    "care", "caregiving", "community health", "employee experience",
    "lifelong learning", "mental health", "people and culture", "public health",
    "workplace culture", "照护", "照護", "照顾", "照顧", "社区健康",
    "社區健康", "员工体验", "員工體驗", "终身学习", "終身學習", "心理健康",
    "人才与文化", "人才與文化", "公共卫生", "公共衞生", "职场文化", "職場文化",
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
    "sunbeam": SUNBEAM_TERMS,
    "current": CURRENT_TERMS,
    "apricot": APRICOT_TERMS,
}


def topic_match_count(subject_text, terms):
    """Count English terms as words and CJK terms as meaningful substrings."""
    score = 0
    for term in terms:
        if term.isascii():
            escaped = re.escape(term)
            if term.endswith("y") and len(term) > 1 and term[-2] not in "aeiou":
                inflected = re.escape(term[:-1]) + r"(?:y|ies)"
            elif not term.endswith("s"):
                inflected = escaped + r"(?:s|es)?"
            else:
                inflected = escaped
            pattern = rf"(?<![a-z0-9])(?:{inflected})(?![a-z0-9])"
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


# Templates that ship their own licensed photograph. Everything else draws a
# generated plate in its own visual language rather than borrowing one.
BUNDLED_TEMPLATE_IMAGES = {
    "horizon": "horizon-landscape.jpg",
    "maison": "maison-interior.jpeg",
    "terrain": "terrain-aerial.jpeg",
    "orbit": "orbit-scientific.jpeg",
    "current": "current-ribbon.jpeg",
    "apricot": "apricot-workshop.jpeg",
}


@lru_cache(maxsize=12)
def bundled_template_image_data_uri(template):
    """Return a bundled editorial image as a portable embedded JPEG."""
    filenames = BUNDLED_TEMPLATE_IMAGES
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
    safe_cover_image = html.escape(str(cover_image), quote=True) if cover_image else None
    image = (
        f'<img class="cover-photo" src="{safe_cover_image}" alt="">'
        if safe_cover_image
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
        photo = safe_cover_image or bundled_template_image_data_uri("maison")
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
            <span class="blueprint-node node-a"></span>
            <span class="blueprint-node node-b"></span>
            <span class="blueprint-node node-c"></span>
            <span class="blueprint-ruler"></span>
        </div>
        """
    if template == "terrain":
        photo = safe_cover_image or bundled_template_image_data_uri("terrain")
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
    if template == "sunbeam":
        return """
        <div class="cover-art sunbeam-art" aria-hidden="true">
            <span class="sunbeam-black-field"></span>
            <span class="sunbeam-orange-field"></span>
            <span class="sunbeam-yellow-field"></span>
            <span class="sunbeam-motif">
                <i class="sunbeam-ring"></i>
                <i class="sunbeam-needle"></i>
            </span>
        </div>
        """
    if template == "current":
        return """
        <div class="cover-art current-art" aria-hidden="true">
            <span class="current-grid"></span>
            <svg class="current-flow-map" viewBox="0 0 595 842"
                 preserveAspectRatio="none" role="presentation">
                <defs>
                    <linearGradient id="current-a" x1="0" y1="1" x2="1" y2="0">
                        <stop offset="0" stop-color="#ff5c00"/>
                        <stop offset=".5" stop-color="#ff8533"/>
                        <stop offset="1" stop-color="#ffb380"/>
                    </linearGradient>
                    <linearGradient id="current-b" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0" stop-color="#ffb380"/>
                        <stop offset=".55" stop-color="#ff8533"/>
                        <stop offset="1" stop-color="#ff5c00"/>
                    </linearGradient>
                </defs>
                <path fill="url(#current-a)" opacity=".94"
                      d="M595 88c-90 15-115 77-189 109-92 40-135 99-117 178 23 98 153 128 306 216v151c-158-104-348-156-376-311-25-136 44-228 156-278 99-44 127-97 220-115z"/>
                <path fill="url(#current-b)" opacity=".82"
                      d="M595 229c-102 9-186 49-201 116-18 76 58 114 201 160v89c-170-45-280-118-269-220 12-101 124-171 269-193z"/>
                <path fill="url(#current-a)" opacity=".86"
                      d="M595 645c-102-45-204-88-260-151-47-53-61-108-47-157-41 69-39 150 12 217 62 82 171 128 295 208z"/>
                <path fill="#fffdf8" opacity=".92"
                      d="M595 356c-90-13-141-1-167 30-21 26-8 52 25 76-31-23-64-52-57-87 10-51 85-83 199-71z"/>
            </svg>
            <span class="current-node"></span>
        </div>
        """
    if template == "apricot":
        photo = safe_cover_image or bundled_template_image_data_uri("apricot")
        return f"""
        <div class="cover-art apricot-art" aria-hidden="true">
            <span class="apricot-spine"></span>
            <img class="cover-photo apricot-photo" src="{photo}" alt="">
            <span class="apricot-photo-wash"></span>
            <span class="apricot-orbit"></span>
        </div>
        """
    horizon_image = safe_cover_image or bundled_template_image_data_uri("horizon")
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
    /* 26mm top margin with the running head centred in it: the header sits
       ~13mm off the trim edge and clears the first body baseline by ~12mm on
       every page. vertical-align:bottom parked it against the text block and
       collided with body copy on roughly half the pages.
       scripts/pdf_quality.py asserts the measured gap. */
    margin: 26mm 18mm 19mm 18mm;

    @top-left {
        content: "ALEXANDRIA  /  DEEP RESEARCH";
        font-family: __FONT_SANS__;
        font-size: 7pt;
        font-weight: 700;
        letter-spacing: 1.25pt;
        color: __DARK__;
        vertical-align: middle;
    }
    @top-right {
        content: "__HEADER__";
        font-family: __FONT_SANS__;
        font-size: 7pt;
        letter-spacing: 0.65pt;
        color: __MUTED__;
        vertical-align: middle;
    }
    @bottom-left {
        content: "__FOOTER__";
        font-family: __FONT_SANS__;
        font-size: 6.6pt;
        letter-spacing: 0.7pt;
        color: __MUTED__;
        vertical-align: top;
    }
    @bottom-right {
        content: "__PAGE_LABEL__ " counter(page) "__PAGE_SUFFIX__";
        font-family: __FONT_SANS__;
        font-size: 7.5pt;
        font-weight: 700;
        color: __DARK__;
        vertical-align: top;
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
    margin: 26mm 18mm 19mm 18mm;
    @top-left { content: "ALEXANDRIA  /  REPORT CONTENTS"; }
    @top-right { content: "__TEMPLATE_NAME__"; }
}

@page sources {
    @top-left { content: "ALEXANDRIA  /  SOURCES"; }
    @top-right { content: "__HEADER__"; }
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

/* ---- CJK setting -------------------------------------------------------
   Chinese text is not Latin text at a different size. Justified setting with
   a slightly looser leading and a wider optical measure reads correctly;
   line-break: strict plus the CJK punctuation rules below approximate 避头尾
   (no line may open with a closing bracket or a full stop, none may end with
   an opening bracket). text-spacing adds the Latin-CJK quarter space where
   the renderer supports it and is ignored where it does not. */
html[lang^="zh"] body {
    font-size: 10.6pt;
    line-height: 1.78;
    text-align: justify;
    text-justify: inter-character;
    line-break: strict;
    word-break: normal;
    overflow-wrap: break-word;
    text-spacing: trim-start allow-end trim-adjacent ideograph-alpha
        ideograph-numeric;
    hanging-punctuation: allow-end;
}
html[lang^="zh"] p,
html[lang^="zh"] li,
html[lang^="zh"] td,
html[lang^="zh"] th {
    line-break: strict;
    text-spacing: trim-start allow-end trim-adjacent ideograph-alpha
        ideograph-numeric;
}
html[lang^="zh"] h1,
html[lang^="zh"] h2,
html[lang^="zh"] h3,
html[lang^="zh"] h4 {
    /* Display sizes stay ragged-right: justification opens ugly rivers in a
       two-line CJK heading. Negative Latin tracking is wrong for CJK. */
    text-align: left;
    letter-spacing: 0;
    line-break: strict;
}
html[lang^="zh"] h1 { font-size: 26pt; line-height: 1.28; }
html[lang^="zh"] h2 { font-size: 19.5pt; line-height: 1.34; }
html[lang^="zh"] code,
html[lang^="zh"] pre {
    line-break: auto;
    text-align: left;
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
    color: __ACCENT_TEXT__;
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
    color: __ACCENT_TEXT__;
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

.toc-page {
    counter-reset: tocitem;
}

.toc-entry {
    counter-increment: tocitem;
    display: grid;
    grid-template-columns: 12mm 1fr 12mm;
    gap: 4mm;
    align-items: start;
    padding: 3.1mm 0 2.7mm;
    border-bottom: 0.45pt solid __RULE__;
    break-inside: avoid;
}

.toc-number::before {
    content: attr(data-toc-index);
    font-size: 7.5pt;
    font-weight: 800;
    letter-spacing: 0.7pt;
    color: __ACCENT_TEXT__;
}

.toc-entry-title {
    display: block;
    font-size: 11.5pt;
    font-weight: 700;
    line-height: 1.25;
    color: __DARK__;
    text-decoration: none;
}

.toc-page-number {
    text-align: right;
    font-size: 10.5pt;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
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
    break-after: avoid;
    break-inside: avoid;
    font-family: __FONT_DISPLAY__;
    font-size: 28pt;
    line-height: 1.08;
    letter-spacing: -0.65pt;
    color: __DARK__;
}

h2 {
    /* Padding, not margin: a top margin collapses to zero at a page break and
       drops the accent rule flush under the running header. */
    margin: 4mm 0 4mm;
    padding: 7mm 0 3.5mm;
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
    color: __ACCENT_TEXT__;
}

p {
    margin: 1.8mm 0;
    /* A three-line CJK remnant can carry under 100 characters and consume an
       otherwise empty page. Keep a full reading block on both sides of a
       paragraph break; normal short paragraphs remain indivisible. */
    orphans: 8;
    widows: 8;
}

/* Only paragraphs the HTML step certified as short enough are set as ledes;
   see is_lede_paragraph() in md_to_pdf.py. A lede never breaks across pages. */
h1 + p.section-lede,
h2 + p.section-lede {
    margin-bottom: 5mm;
    max-width: 126mm;
    font-size: 11.4pt;
    line-height: 1.48;
    color: __MUTED__;
    break-inside: avoid;
    orphans: 3;
    widows: 3;
}

strong, b {
    color: __DARK__;
    font-weight: 700;
}

a {
    color: __LINK__;
    text-decoration: underline;
    text-decoration-thickness: 0.4pt;
    text-underline-offset: 1.2pt;
}
/* Mid-word breaking belongs to raw URLs only, never to link titles. */
a[href]::after,
.sources-section a[href] {
    overflow-wrap: anywhere;
}
.source-ref {
    margin-left: 0.3mm;
    font-size: 6.6pt;
    font-weight: 600;
    letter-spacing: 0.15pt;
    color: __ACCENT_TEXT__;
    text-decoration: none;
    vertical-align: super;
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
    display: block;
    box-sizing: border-box;
    width: 100%;
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
    white-space: nowrap;
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

.insight-panel a {
    color: __LINK_ON_DARK__;
}

.insight-panel .source-ref {
    color: __LINK_ON_DARK__;
}

.takeaway-band {
    margin: 7mm 0;
    padding: 5.5mm 7mm;
    background: __TAKEAWAY__;
    color: __ON_ACCENT__;
    font-size: 11pt;
    font-weight: 600;
}

.takeaway-band a,
.takeaway-band strong,
.takeaway-band b,
.takeaway-band .source-ref {
    color: inherit;
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

tr,
td,
th {
    break-inside: avoid;
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
    padding: 0.2mm 0.7mm;
    margin: 0 -0.2mm;
    background: __PALE__;
    color: __DARK__;
    font-size: 9pt;
    /* Short inline code is a single token to the reader; never break it. */
    white-space: nowrap;
}

pre code {
    white-space: inherit;
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

.sources-section {
    counter-reset: sourceitem;
    /* The bibliography always opens its own page. */
    page-break-before: always;
    page: sources;
}
.sources-section ul,
.sources-section ol {
    margin: 3mm 0;
    padding-left: 0;
}
.sources-section li {
    counter-increment: sourceitem;
    list-style: none;
    /* Hanging indent: wrapped title lines align with the title, not with the
       [nn] marker, so the marker column stays a column. */
    margin: 0 0 4mm;
    padding-left: 9mm;
    text-indent: -9mm;
    break-inside: avoid;
}
.sources-section li::before {
    content: "[" counter(sourceitem, decimal-leading-zero) "]\\2003";
    color: __ACCENT_TEXT__;
    font-family: __FONT_MONO__;
    font-size: 7pt;
}
.sources-section a[href] {
    text-decoration: none;
}
.sources-section a[href^="http"]::after {
    /* display:block already opens the line; a literal \\A here would inject a
       phantom blank line and group each URL with the NEXT entry. */
    content: attr(href);
    display: block;
    margin-top: 0.6mm;
    text-indent: 0;
    color: __MUTED__;
    font-family: __FONT_MONO__;
    font-size: 6.8pt;
    line-height: 1.3;
    overflow-wrap: anywhere;
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
    min-height: 232mm;
    page-break-after: always;
    color: __TEXT__;
}
/* The opener is a single designed page. Without this the lower grid spills a
   couple of orphaned list items onto an otherwise blank sheet. */
.horizon-feature-lower,
.horizon-feature-narrative,
.horizon-feature-path {
    break-inside: avoid;
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
    color: __ACCENT_TEXT__;
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
    height: 78mm;
    overflow: hidden;
    background: __PALE__;
}

/* Generated plate used by templates that ship no photograph of their own. */
.feature-plate {
    position: absolute;
    inset: 0;
    display: block;
}
.feature-plate i {
    position: absolute;
    display: block;
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
    color: __ACCENT_TEXT__;
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
/* Deliberately three plain graduated rules: an abstract mark, not a scale.
   The measurement-node terminals were removed because nothing calibrated
   them. */
.executive-scale.scale-b { width: 26mm; }
.executive-scale.scale-c { width: 18mm; }
.scale-a { top: 132mm; }
.scale-b { top: 150mm; }
.scale-c { top: 168mm; }
.template-executive .toc-title,
.template-executive h1,
.template-executive h2 {
    font-weight: 600;
}
.template-executive .report-body {
    max-width: 159mm;
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
        linear-gradient(to right, rgba(79,70,229,0.025) 0.35pt, transparent 0.35pt),
        linear-gradient(to bottom, rgba(79,70,229,0.02) 0.35pt, transparent 0.35pt);
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
.template-spectrum .report-body {
    padding-left: 5mm;
    border-left: 1.2mm solid #6f35f2;
    background-image: linear-gradient(
        90deg,
        rgba(201,255,23,0.08),
        transparent 18mm
    );
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
.template-atlas .report-body {
    max-width: 148mm;
    font-family: __FONT_DISPLAY__;
    line-height: 1.7;
}
.template-atlas .report-body table,
.template-atlas .report-body code {
    font-family: __FONT_SANS__;
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
.template-horizon .report-body {
    border-left: 1.2mm solid #0062ff;
    padding-left: 7mm;
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
    height: 88mm;
}
.maison-art .maison-photo {
    opacity: 1;
}
.maison-photo-shade {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        to bottom,
        rgba(0,0,0,0.48),
        rgba(0,0,0,0.12) 58%,
        rgba(0,0,0,0.36)
    );
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
    position: absolute;
    left: 17mm;
    right: 17mm;
    top: 104mm;
    width: auto;
    margin: 0;
    text-align: center;
}
.template-maison .cover-kicker {
    margin-bottom: 6mm;
    color: __ACCENT_TEXT__;
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
    color: __ACCENT_TEXT__;
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
.toc-maison.toc-special-cont .toc-title {
    margin: 4mm 0 8mm;
    font-size: 28pt;
    letter-spacing: -0.6pt;
}
.toc-maison.toc-special-cont .maison-toc-note {
    display: none;
}
.toc-maison.toc-special-cont .toc-list {
    margin: 0;
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
.template-maison .report-body {
    max-width: 142mm;
    font-family: __FONT_DISPLAY__;
    font-size: 10.6pt;
    line-height: 1.72;
}
.template-maison .report-body code,
.template-maison .report-body table {
    font-family: __FONT_SANS__;
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
    background: #fff;
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
    /* 17mm..185mm x 111mm..255mm == 7 x 6 modules on the 24mm cover grid. */
    inset: 111mm 25mm 42mm 17mm;
    border: 0.7pt solid #4a9fd8;
}
.blueprint-datum {
    position: absolute;
    border: 0.7pt solid #4a9fd8;
}
.datum-a { left: 24mm; top: 24mm; width: 48mm; height: 48mm; }
.datum-b { right: 24mm; bottom: 24mm; width: 48mm; height: 48mm; }
.blueprint-axis {
    position: absolute;
    background: #4a9fd8;
}
.blueprint-axis-x { left: 0; top: 72mm; width: 100%; height: 0.5pt; }
.blueprint-axis-y { left: 96mm; top: 0; width: 0.5pt; height: 100%; }
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
/* Centred on the (24,24), (96,72) and (144,120) datum intersections. */
.node-a { left: 14.5mm; top: 14.5mm; }
.node-b { left: 86.5mm; top: 62.5mm; }
.node-c { left: 134.5mm; top: 110.5mm; }
.blueprint-ruler {
    position: absolute;
    left: 0;
    right: 0;
    bottom: -9mm;
    height: 3mm;
    border-top: 0.6pt solid #4a9fd8;
}
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
    background: #fff;
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
    background: #fff;
}
/* Generated opener plate: the datum grid the template is named for, with an
   orthographic construction snapped to a 13mm module. Blueprint ships no
   photograph, and borrowing Orbit's was both dishonest and off-subject. */
.template-blueprint .horizon-feature-photo {
    border: 0.7pt solid #4a9fd8;
    background: #f7fbfe;
}
.template-blueprint .feature-plate {
    background: transparent;
}
.template-blueprint .feature-plate i:nth-child(1) {
    left: 26mm;
    top: 13mm;
    width: 52mm;
    height: 52mm;
    border: 0.7pt solid #4a9fd8;
}
.template-blueprint .feature-plate i:nth-child(2) {
    left: 91mm;
    top: 26mm;
    width: 39mm;
    height: 39mm;
    border: 0.7pt solid #4a9fd8;
    border-radius: 50%;
}
.template-blueprint .feature-plate i:nth-child(3) {
    left: 0;
    top: 39mm;
    width: 100%;
    height: 0.5pt;
    background: rgba(74,159,216,0.85);
}
.template-blueprint .feature-plate i:nth-child(4) {
    left: 65mm;
    top: 0;
    width: 0.5pt;
    height: 100%;
    background: rgba(74,159,216,0.85);
}
.blueprint-feature-insight {
    margin-right: 0;
    background: #1a1a1a;
    border-radius: 0;
}
.template-blueprint h1,
.template-blueprint h2,
.template-blueprint h3 {
    font-weight: 720;
}
.template-blueprint .report-body {
    padding-left: 8mm;
    border-left: 0.5pt solid rgba(74,159,216,0.55);
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
    background: linear-gradient(
        to bottom,
        rgba(10,32,19,0.46),
        rgba(15,45,28,0.38) 48%,
        rgba(15,45,28,0.72)
    );
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
    text-shadow: 0 0.5mm 1.2mm rgba(0,0,0,0.55);
}
.template-terrain .cover-kicker {
    color: #fff;
    text-shadow: 0 0.5mm 1.2mm rgba(0,0,0,0.55);
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
.toc-terrain.toc-chunk-01 .terrain-toc-map img { object-position: 50% 24%; }
.toc-terrain.toc-chunk-02 .terrain-toc-map img { object-position: 28% 58%; }
.toc-terrain.toc-chunk-03 .terrain-toc-map img { object-position: 74% 72%; }
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
.template-terrain .report-body {
    padding-left: 6mm;
    border-left: 1mm solid #2d5e3a;
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
    border: 0.6pt solid rgba(255,255,255,0.09);
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
    border: 0.6pt solid rgba(255,255,255,0.09);
    border-radius: 50%;
    z-index: 0;
}
.toc-orbit .toc-list {
    position: relative;
    z-index: 3;
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
.template-orbit .report-body {
    padding-right: 6mm;
    border-right: 0.7mm solid #0062ff;
    background-image:
        radial-gradient(circle at 100% 0, rgba(0,98,255,0.09), transparent 24mm);
}
""",
    "sunbeam": """
@page toc {
    margin: 17mm;
    background: #fffdf8;
    @top-left { content: "ALEXANDRIA  /  BRIGHT FIELD"; border: 0; }
    @top-right { content: "SUNBEAM"; border: 0; }
}
.template-sunbeam .cover {
    padding: 16mm 18mm;
    background: #151515;
    color: #fffdf8;
}
.sunbeam-black-field {
    position: absolute;
    inset: 0 0 47% 0;
    background: #151515;
}
.sunbeam-orange-field {
    position: absolute;
    inset: 53% 0 20% 0;
    background: #ff6b35;
}
.sunbeam-yellow-field {
    position: absolute;
    inset: 80% 0 0;
    background: #ffd84d;
}
.sunbeam-motif {
    position: absolute;
    right: 17mm;
    top: 179mm;
    width: 38mm;
    height: 38mm;
    border-radius: 50%;
    background: #151515;
}
.sunbeam-ring {
    position: absolute;
    inset: 6mm;
    border: 1.1pt solid #ffd84d;
    border-radius: 50%;
}
.sunbeam-needle {
    position: absolute;
    left: 18.5mm;
    top: -12mm;
    width: 1.2pt;
    height: 62mm;
    background: #fffdf8;
    transform: rotate(28deg);
    transform-origin: center;
}
.template-sunbeam .cover-topline {
    border: 0;
    color: #fffdf8;
}
.template-sunbeam .cover-topline span:first-child {
    color: #ffd84d;
}
.template-sunbeam .cover-copy {
    width: 172mm;
    margin-top: 38mm;
}
.template-sunbeam .cover-kicker {
    color: __ACCENT_TEXT__;
}
.template-sunbeam .cover h1,
.template-sunbeam .cover-title-accent {
    display: block;
    max-width: 172mm;
    margin: 0;
    padding: 0;
    background: transparent;
    color: #fffdf8;
    font-size: 43pt;
    font-weight: 600;
    line-height: 0.98;
}
.template-sunbeam .cover-title-accent {
    color: #ffd84d;
}
.template-sunbeam .cover .subtitle {
    width: 127mm;
    color: #d7d3cb;
}
.template-sunbeam .cover-record {
    bottom: 12mm;
    padding: 0;
    border: 0;
}
.template-sunbeam .cover-record .meta-cell {
    flex-basis: 48mm;
}
.template-sunbeam .meta-label {
    color: #6d5a28;
}
.template-sunbeam .meta-value,
.template-sunbeam .confidential-stamp {
    color: #151515;
}
.template-sunbeam .cover-confidential-note {
    bottom: 4mm;
    color: #6d5a28;
}
.toc-sunbeam {
    position: relative;
    color: #151515;
}
.toc-sunbeam::before {
    content: "";
    position: absolute;
    z-index: 0;
    left: -17mm;
    right: -17mm;
    top: -17mm;
    height: 66mm;
    background: #ff6b35;
}
.toc-sunbeam > * {
    position: relative;
    z-index: 1;
}
.toc-sunbeam .toc-kicker {
    color: #151515;
}
.toc-sunbeam .toc-title {
    margin-top: 3mm;
    font-size: 39pt;
    color: #151515;
}
.toc-sunbeam .toc-intro {
    width: 110mm;
    margin-bottom: 19mm;
    border: 0;
    color: #151515;
}
.sunbeam-toc-system {
    position: absolute;
    right: 0;
    top: 60mm;
    width: 46mm;
    height: 46mm;
    padding: 12mm 5mm 0;
    box-sizing: border-box;
    border-radius: 50%;
    background: #151515;
    color: #ffd84d;
    text-align: center;
}
.sunbeam-toc-ring {
    position: absolute;
    inset: 5mm;
    border: 0.7pt solid #ff6b35;
    border-radius: 50%;
}
.sunbeam-toc-system strong {
    position: relative;
    font-family: __FONT_MONO__;
    font-size: 6.1pt;
    line-height: 1.3;
    letter-spacing: 0.6pt;
    text-transform: uppercase;
}
.toc-sunbeam .toc-list {
    width: 126mm;
}
.toc-sunbeam .toc-entry {
    grid-template-columns: 11mm 1fr 10mm;
    border-color: #d5cec2;
}
.toc-sunbeam .toc-number::before,
.toc-sunbeam .toc-page-number {
    color: __ACCENT_TEXT__;
}
/* Generated opener plate. Sunbeam ships no photograph of its own, and the
   mobility ribbon it used to borrow from Current had nothing to do with
   education, youth or civic work. The double-position colour stops the old
   rule used were dropped by the renderer, which is why the plate printed as a
   flat pale rectangle. */
.sunbeam-feature-photo {
    height: 66mm;
    background: linear-gradient(
        180deg,
        #ff6b35 0%,
        #ff6b35 58%,
        #ffd84d 58%,
        #ffd84d 100%
    );
}
.template-sunbeam .feature-plate i {
    border-radius: 50%;
}
.template-sunbeam .feature-plate i:nth-child(1) {
    right: 22mm;
    top: 11mm;
    width: 34mm;
    height: 34mm;
    background: #151515;
}
.template-sunbeam .feature-plate i:nth-child(2) {
    right: 12mm;
    top: 1mm;
    width: 54mm;
    height: 54mm;
    border: 0.9pt solid #151515;
}
.template-sunbeam .feature-plate i:nth-child(3) {
    right: 2mm;
    top: -9mm;
    width: 74mm;
    height: 74mm;
    border: 0.6pt solid rgba(21,21,21,0.45);
}
.template-sunbeam .feature-plate i:nth-child(4) {
    left: 21mm;
    bottom: 9mm;
    width: 15mm;
    height: 15mm;
    background: #fff2c7;
}
/* Sunbeam draws its own opener plate; it never showed a photograph, and it
   no longer loads Current's into the PDF either. */
.sunbeam-feature-photo img {
    display: none;
}
.sunbeam-feature-datum {
    left: 21mm;
    top: 14mm;
    width: 50mm;
    height: 0.8pt;
    background: #151515;
    transform: rotate(-18deg);
}
.sunbeam-feature-insight {
    width: 95mm;
    margin: -22mm 10mm 0 auto;
    background: #151515;
    box-shadow: none;
}
.sunbeam-feature-insight > span {
    color: #ffd84d;
}
.sunbeam-feature-lower {
    grid-template-columns: 1fr 61mm;
}
.sunbeam-feature-path {
    padding: 5mm;
    background: #ffd84d;
}
.template-sunbeam h1,
.template-sunbeam h2,
.template-sunbeam h3 {
    color: #151515;
}
.template-sunbeam .metric-card {
    border-top-color: #ff6b35;
    background: #ffd84d;
}
.template-sunbeam .insight-panel {
    background: #151515;
}
.template-sunbeam .takeaway-band {
    background: #ff6b35;
}
.template-sunbeam .report-body {
    padding-left: 6mm;
    border-left: 2mm solid #ffd84d;
}
""",
    "current": """
@page toc {
    margin: 17mm;
    background: #fffdf8;
    @top-left { content: "ALEXANDRIA  /  FLOW MAP"; border: 0; }
    @top-right { content: "CURRENT"; border: 0; }
}
.template-current .cover {
    padding: 16mm 18mm;
    border-left: 2.4mm solid #ff5c00;
    background: #fffdf8;
}
.current-grid {
    position: absolute;
    inset: 0;
    background:
        linear-gradient(rgba(26,26,26,.055) 0.5pt, transparent 0.5pt),
        linear-gradient(90deg, rgba(26,26,26,.055) 0.5pt, transparent 0.5pt);
    background-size: 22mm 22mm;
}
.current-flow-map {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
}
.current-node {
    position: absolute;
    right: 26mm;
    bottom: 56mm;
    width: 13mm;
    height: 13mm;
    border: 4mm solid #fffdf8;
    border-radius: 50%;
    background: #ff5c00;
    box-shadow: 0 0 0 1.2pt #ff5c00;
}
.template-current .cover-topline {
    border: 0;
}
.template-current .cover-copy {
    width: 129mm;
    margin-top: 42mm;
    padding: 8mm 8mm 9mm;
    box-sizing: border-box;
    background: rgba(255,253,248,.93);
}
.template-current .cover h1,
.template-current .cover-title-accent {
    display: block;
    margin: 0;
    padding: 0;
    background: transparent;
    color: #1a1a1a;
    font-family: __FONT_SANS__;
    font-size: 39pt;
    font-weight: 760;
    line-height: 0.98;
}
.template-current .cover-title-accent {
    color: __ACCENT_TEXT__;
}
.template-current .cover .subtitle {
    color: #555;
}
.template-current .cover-record {
    right: 74mm;
    bottom: 13mm;
    padding: 6mm;
    border: 0;
    background: rgba(255,253,248,.94);
}
.template-current .cover-confidential-note {
    bottom: 5mm;
}
.toc-current {
    position: relative;
}
.toc-current::after {
    content: "";
    position: absolute;
    z-index: 0;
    right: -17mm;
    top: -17mm;
    width: 52mm;
    height: 264mm;
    background: linear-gradient(165deg, #ffb380 0 29%, #ff8533 29% 61%, #ff5c00 61%);
    clip-path: polygon(48% 0,100% 0,100% 100%,4% 100%,38% 69%,12% 38%);
}
.toc-current > * {
    position: relative;
    z-index: 1;
}
.toc-current .toc-title {
    font-family: __FONT_SANS__;
    font-size: 41pt;
    font-weight: 760;
}
.toc-current .toc-intro,
.toc-current .toc-list {
    width: 136mm;
}
.current-toc-system {
    width: 136mm;
    margin: -4mm 0 7mm;
    font-family: __FONT_MONO__;
    font-size: 6.5pt;
    letter-spacing: 0.8pt;
    text-transform: uppercase;
    color: __ACCENT_TEXT__;
}
.current-toc-line {
    display: inline-block;
    width: 48mm;
    height: 2mm;
    margin-right: 4mm;
    border-radius: 2mm;
    vertical-align: middle;
    background: linear-gradient(90deg, #ff5c00, #ffb380);
}
.toc-current .toc-entry-title {
    font-size: 12pt;
}
.current-feature-photo {
    height: 72mm;
    background: #fff4ec;
}
.current-feature-photo img {
    object-fit: cover;
}
.current-feature-insight {
    width: 98mm;
    margin: -25mm 8mm 0 auto;
    border-radius: 3mm;
    background: linear-gradient(120deg, #ff5c00, #ff8533);
    box-shadow: 0 2mm 7mm rgba(255,92,0,.24);
}
.current-feature-insight > span {
    color: #fff;
}
.current-feature-lower {
    grid-template-columns: 1fr 61mm;
}
.current-feature-path {
    padding: 5mm;
    border-radius: 3mm;
    background: #fff4ec;
}
.template-current h1,
.template-current h2,
.template-current h3 {
    font-family: __FONT_SANS__;
    font-weight: 740;
}
.template-current h2 {
    border-bottom-color: #ff5c00;
}
.template-current .metric-card,
.template-current .insight-panel,
.template-current .takeaway-band {
    border-radius: 3mm;
}
.template-current .insight-panel,
.template-current .takeaway-band {
    background: linear-gradient(120deg, #ff5c00, #ff8533);
}
.template-current .report-body {
    padding-left: 5mm;
    border-left: 1mm solid #ff5c00;
    background-image:
        linear-gradient(rgba(255,92,0,0.035) 0.35pt, transparent 0.35pt);
    background-size: 100% 8mm;
}
""",
    "apricot": """
@page toc {
    margin: 17mm;
    background: #fffdf8;
    @top-left { content: "ALEXANDRIA  /  PEOPLE & CONTEXT"; border: 0; }
    @top-right { content: "APRICOT"; border: 0; }
}
.template-apricot .cover {
    padding: 17mm 18mm;
    border-left: 3mm solid #ff9800;
    background: #fffdf8;
}
.apricot-spine {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3mm;
    background: #ff9800;
}
.apricot-photo {
    position: absolute;
    right: 0;
    top: 0;
    width: 47%;
    height: 100%;
    object-fit: cover;
}
.apricot-photo-wash {
    position: absolute;
    right: 0;
    top: 0;
    width: 47%;
    height: 100%;
    background: linear-gradient(90deg, #fffdf8 0, transparent 23%, rgba(255,152,0,.13));
}
.apricot-orbit {
    position: absolute;
    right: 20mm;
    bottom: 26mm;
    width: 52mm;
    height: 52mm;
    border: 0.8pt solid rgba(255,255,255,.84);
    border-radius: 50%;
}
.apricot-orbit::after {
    content: "";
    position: absolute;
    inset: 9mm;
    border: 0.8pt solid rgba(255,152,0,.8);
    border-radius: 50%;
}
.template-apricot .cover-topline {
    width: 47%;
}
.template-apricot .cover-copy {
    width: 91mm;
    margin-top: 48mm;
}
.template-apricot .cover-kicker {
    color: __ACCENT_TEXT__;
}
.template-apricot .cover h1,
.template-apricot .cover-title-accent {
    display: block;
    margin: 0;
    padding: 0;
    background: transparent;
    color: #1a1a1a;
    font-size: 38pt;
    font-weight: 600;
    line-height: 1;
}
.template-apricot .cover-title-accent {
    color: __ACCENT_TEXT__;
}
.template-apricot .cover .subtitle {
    width: 83mm;
    font-size: 11pt;
}
.template-apricot .cover-record {
    right: 109mm;
    bottom: 17mm;
    gap: 3mm;
    padding-top: 5mm;
    border-color: #ff9800;
}
.template-apricot .cover-record .meta-cell {
    flex-basis: 72mm;
}
.template-apricot .cover-confidential-note {
    right: 109mm;
}
.toc-apricot {
    position: relative;
}
.toc-apricot::before {
    content: "";
    position: absolute;
    z-index: 0;
    left: -17mm;
    top: -17mm;
    width: 42mm;
    height: 264mm;
    background: #ff9800;
}
.toc-apricot > * {
    position: relative;
    z-index: 1;
}
.toc-apricot .toc-kicker,
.toc-apricot .toc-title,
.toc-apricot .toc-intro,
.toc-apricot .toc-list,
.apricot-toc-system {
    margin-left: 19mm;
}
.toc-apricot .toc-title {
    font-size: 40pt;
    font-weight: 600;
}
.toc-apricot .toc-intro {
    width: 122mm;
}
.apricot-toc-system {
    margin-bottom: 5mm;
    font-family: __FONT_MONO__;
    font-size: 6.4pt;
    letter-spacing: .8pt;
    text-transform: uppercase;
    color: __ACCENT_TEXT__;
}
.apricot-toc-dot {
    display: inline-block;
    width: 5mm;
    height: 5mm;
    margin-right: 3mm;
    border: 1pt solid #ff9800;
    border-radius: 50%;
    vertical-align: middle;
}
.toc-apricot .toc-entry-title {
    font-family: __FONT_DISPLAY__;
    font-size: 13pt;
    font-weight: 600;
}
.apricot-feature-photo {
    height: 84mm;
    border-left: 3mm solid #ff9800;
}
.apricot-feature-photo img {
    object-position: center 38%;
}
.apricot-feature-insight {
    width: 91mm;
    background: #ff9800;
    box-shadow: 0 2mm 7mm rgba(255,152,0,.2);
}
.apricot-feature-insight > span {
    color: #fff;
}
.apricot-feature-lower {
    grid-template-columns: 1fr 64mm;
}
.apricot-feature-path {
    padding: 5mm;
    background: #fff3e6;
}
.template-apricot h1,
.template-apricot h2,
.template-apricot h3 {
    font-weight: 600;
}
.template-apricot .metric-card {
    border-top-color: #ff9800;
    background: #fff3e6;
}
.template-apricot .insight-panel {
    background: #ff9800;
}
.template-apricot .takeaway-band {
    background: #ffb04a;
}
.template-apricot .report-body {
    padding-right: 6mm;
    border-right: 1mm solid #ff9800;
    font-family: __FONT_DISPLAY__;
    line-height: 1.7;
}
.template-apricot .report-body table,
.template-apricot .report-body code {
    font-family: __FONT_SANS__;
}
""",
}


# Text colour carried on the accent fill (takeaway band). White where the
# accent is dark enough to hold it at >= 4.5:1, otherwise the template's own
# dark ink. Derived once with scripts.pdf_quality.adjust_to_contrast and pinned
# here so the CSS stays deterministic; scripts/pdf_quality.py re-verifies every
# pair on every run.
ON_ACCENT = {
    "executive": "#ffffff",
    "spectrum": "#ffffff",
    "atlas": "#ffffff",
    "horizon": "#ffffff",
    "maison": "#1a1a1a",
    "blueprint": "#1a1a1a",
    "terrain": "#ffffff",
    "orbit": "#ffffff",
    "sunbeam": "#151515",
    "current": "#1a1a1a",
    "apricot": "#1a1a1a",
}

# Link ink on white and on the template's pale panel, >= 4.75:1 on both. This
# is deliberately a separate token from the decorative accent: the accent may
# stay bright, the link may not.
LINK_ON_LIGHT = {
    "executive": "#147772",
    "spectrum": "#4f46e5",
    "atlas": "#2f7448",
    "horizon": "#0b61f1",
    "maison": "#7a6942",
    "blueprint": "#36749f",
    "terrain": "#2d5e3a",
    "orbit": "#0061fd",
    "sunbeam": "#b34b26",
    "current": "#bf4500",
    "apricot": "#9d5e00",
}

# Link ink inside the dark insight panel, >= 4.75:1 on __DARK__.
LINK_ON_DARK = {
    "executive": "#58a6a1",
    "spectrum": "#7d76ec",
    "atlas": "#83ac92",
    "horizon": "#2d79f7",
    "maison": "#b39a61",
    "blueprint": "#4a9fd8",
    "terrain": "#8ca793",
    "orbit": "#3482ff",
    "sunbeam": "#ff6b35",
    "current": "#ff5c00",
    "apricot": "#ff9800",
}

BODY_TEXT = {
    "atlas": "#233a2b",
    "terrain": "#233a2b",
    "maison": "#2b2926",
    "sunbeam": "#1a1a1a",
    "current": "#1a1a1a",
    "apricot": "#1a1a1a",
}

RULE_COLORS = {
    "executive": "#c8d3d8",
    "spectrum": "#d9dce5",
    "atlas": "#cad4c8",
    "horizon": "#d7dee8",
    "maison": "#d8d2c8",
    "blueprint": "#d8e7f0",
    "terrain": "#d6ddd0",
    "orbit": "#d8e2f2",
    "sunbeam": "#d5cec2",
    "current": "#ddd8d0",
    "apricot": "#d9d4ce",
}

ROW_COLORS = {
    "atlas": "#f5f7f3",
    "terrain": "#f5f3ee",
    "maison": "#f4f2ef",
    "blueprint": "#f7f8fa",
    "orbit": "#f7f8fa",
    "sunbeam": "#fff8e3",
    "current": "#fff7f2",
    "apricot": "#fcfaf7",
}

INSIGHT_ACCENT = {
    "executive": "#7fd6cf",
    "spectrum": "#c9ff17",
    "atlas": "#b9d5bf",
    "horizon": "#dbeaff",
    "maison": "#e6d9bc",
    "blueprint": "#d9effc",
    "terrain": "#a8ccaf",
    "orbit": "#dbe7ff",
    "sunbeam": "#ffd84d",
    "current": "#fff4ec",
    "apricot": "#fff3e6",
}


def css_color_tokens(template):
    """Return every colour-valued CSS token for one template.

    Pure data: scripts/pdf_quality.py consumes this to prove WCAG contrast for
    all eleven templates without rendering anything.
    """
    spec = TEMPLATES[template]
    return {
        "__ACCENT__": spec.accent,
        "__ACCENT_TEXT__": spec.accent_text,
        "__DARK__": spec.dark,
        "__MUTED__": spec.muted,
        "__PALE__": spec.pale,
        "__TEXT__": BODY_TEXT.get(template, "#172330"),
        "__ON_ACCENT__": ON_ACCENT[template],
        "__LINK__": LINK_ON_LIGHT[template],
        "__LINK_ON_DARK__": LINK_ON_DARK[template],
        "__RULE__": RULE_COLORS[template],
        "__ROW__": ROW_COLORS.get(template, "#f6f8f9"),
        "__INSIGHT_ACCENT__": INSIGHT_ACCENT[template],
        "__TAKEAWAY__": spec.accent,
        # The band label shares the body ink; hierarchy comes from size,
        # weight and letterspacing rather than from a washed-out tint.
        "__TAKEAWAY_ACCENT__": ON_ACCENT[template],
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
        "__INSIGHT_LABEL__": insight_label,
        "__TAKEAWAY_LABEL__": takeaway_label,
        **css_color_tokens(template),
    }
    shared_feature = (
        SHARED_REFERENCE_FEATURE_CSS
        if template
        in {
            "maison",
            "blueprint",
            "terrain",
            "orbit",
            "sunbeam",
            "current",
            "apricot",
        }
        else ""
    )
    css = (
        BUNDLED_FONT_CSS
        + COMMON_CSS
        + shared_feature
        + TEMPLATE_CSS[template]
        + RESPONSIVE_COVER_CSS
    )
    for placeholder, value in values.items():
        css = css.replace(placeholder, value)
    unresolved = sorted(set(re.findall(r"__[A-Z_]+__", css)))
    if unresolved:
        raise ValueError(
            f"Unresolved CSS placeholders for template {template}: "
            + ", ".join(unresolved)
        )
    return css
