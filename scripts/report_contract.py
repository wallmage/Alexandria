"""Shared language, length, and date policy for Alexandria reports."""

import html
import re
import unicodedata
from datetime import date

TRADITIONAL_MARKERS = frozenset(
    "這個為與報發後裡麼還說對時國學術據點體現關於會開"
)
SIMPLIFIED_MARKERS = frozenset(
    "这个为与报发后里么还说对时国学术据点体现关于会开"
)

LENGTH_POLICIES = {
    "en": (7500, 15000, "words"),
    "zh-CN": (5000, 10000, "report-body characters"),
    "zh-HK": (5000, 10000, "report-body characters"),
}

ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

BIDI_CONTROL_CHARACTERS = frozenset(
    chr(codepoint)
    for codepoint in (
        0x061C,
        0x200E,
        0x200F,
        *range(0x202A, 0x202F),
        *range(0x2066, 0x206A),
    )
)

DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
CJK_VISIBLE_PUNCTUATION = frozenset(
    "，。！？；：、（）【】《》〈〉「」『』“”‘’"
)


def _is_default_ignorable(codepoint):
    return any(start <= codepoint <= end for start, end in DEFAULT_IGNORABLE_RANGES)


def forbidden_visible_control_characters(value):
    """Return bidi controls whose visual ordering cannot be safely inferred."""
    return sorted(
        {
            character
            for character in str(value or "")
            if character in BIDI_CONTROL_CHARACTERS
        }
    )


def canonical_visible_text(value):
    """Match text users see after entity decoding and ignorable removal."""
    decoded = html.unescape(str(value or ""))
    composed = unicodedata.normalize("NFC", decoded)
    normalized = "".join(
        character
        if character in CJK_VISIBLE_PUNCTUATION
        else unicodedata.normalize("NFKC", character)
        for character in composed
    )
    visible = []
    for character in normalized:
        category = unicodedata.category(character)
        codepoint = ord(character)
        if category == "Cf" or _is_default_ignorable(codepoint):
            continue
        if category == "Cc" and character not in "\t\n\r":
            visible.append(" ")
            continue
        visible.append(character)
    return "".join(visible)


def detect_language(text):
    """Return en, zh-CN, zh-HK, or zh for script-neutral Chinese."""
    han_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if han_count <= latin_count * 0.3:
        return "en"
    traditional = sum(text.count(char) for char in TRADITIONAL_MARKERS)
    simplified = sum(text.count(char) for char in SIMPLIFIED_MARKERS)
    if traditional == simplified:
        return "zh"
    return "zh-HK" if traditional > simplified else "zh-CN"


def report_length_policy(report_lang):
    """Return (minimum, maximum, unit) for one explicit report language."""
    try:
        return LENGTH_POLICIES[report_lang]
    except KeyError as exc:
        raise ValueError(f"Unsupported report language: {report_lang}") from exc


def localized_date(report_lang, day=None):
    """Format a report date without depending on the host process locale."""
    day = day or date.today()
    if report_lang == "en":
        return f"{day.day:02d} {ENGLISH_MONTHS[day.month - 1]} {day.year}"
    if report_lang in {"zh-CN", "zh-HK"}:
        return f"{day.year}年{day.month}月{day.day}日"
    raise ValueError(f"Unsupported report language: {report_lang}")
