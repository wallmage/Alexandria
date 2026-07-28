"""Shared language, length, and date policy for Alexandria reports."""

import re
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
