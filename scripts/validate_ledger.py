#!/usr/bin/env python3
"""Validate an Alexandria evidence ledger and its internal references."""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gate_severity import (  # noqa: E402, F401
    Finding,
    emit_findings,
    hard_errors,
    render_grouped,
    warning,
)

REFERENCES = Path(__file__).resolve().parents[1] / "references"
DEFAULT_SCHEMA = REFERENCES / "evidence-ledger.schema.json"
CLAIM_INPUT_SCHEMA = REFERENCES / "claim-input.schema.json"
FAMILIES = frozenset(
    {
        "ledger/quantity",
        "ledger/status",
        "ledger/direction",
        "ledger/schema",
        "ledger/source-ids",
        "ledger/https",
        "ledger/provenance",
        "ledger/key-claim",
        "ledger/portfolio",
        "ledger/coverage",
        "ledger/synthesis",
        "ledger/source-family",
        "ledger/derived",
        "ledger/person",
        "ledger/excluded-supports",
        "ledger/undated-reason",
        "ledger/host-conflict",
        "ledger/claim-input",
        "ledger/extract-length",
        "ledger/triangulation",
        "ledger/freshness",
        "ledger/reference",
    }
)


#: R29: lexical and semantic heuristics and ledger shape are not verbatim
#: fidelity, and the ledger is machine-written, so these are printed with
#: their fix and never block.
WARN_FAMILIES = frozenset(
    {"ledger/status", "ledger/direction", "ledger/schema", "ledger/quantity"}
)


def _ids_in(message):
    return re.findall(r"\b[CSP]\d+\b", str(message))


def _f(family, message, *, severity="hard", ids=None, fix="", remove=""):
    if family in WARN_FAMILIES:
        severity = "warn"
    return Finding(
        family=family,
        severity=severity,
        klass="A" if severity == "warn" else "F",
        ids=list(ids if ids is not None else _ids_in(message)),
        message=message,
        fix=fix,
        remove=remove if severity == "hard" else "",
    )


#: R28: a cross-reference is bookkeeping, not fabrication. Every legacy string
#: raised here is a WARN; the one hard case (a source_id no fetched source
#: carries) says so at its own call site.
def _ref(message, *, family="ledger/reference", severity="warn", ids=None, fix="", remove=""):
    if isinstance(message, Finding):
        return message
    text = str(message)
    if text.startswith("WARNING: "):
        severity = "warn"
        text = text[len("WARNING: "):]
    return _f(family, text, severity=severity, ids=ids, fix=fix, remove=remove)


def _as_legacy(items):
    out = []
    for item in items:
        if isinstance(item, Finding):
            out.append(warning(item.message) if item.severity == "warn" else item.message)
        else:
            out.append(item)
    return out


def _drop(claim_id):
    return f"alx claim drop {claim_id} --apply" if claim_id else ""
_CJK_SENTENCE_PUNCT = "，、！？：；。"
_NUMERIC_OR_LEGAL_CARRIER = re.compile(
    r"(?i)\d|percent|%|million|billion|thousand|dollar|usd|court|decree|"
    r"lawsuit|settlement|agreement|judgment|verdict|indict|charge|fine|"
    r"penalty|consent|判决|和解|协议|訴訟|诉讼|赔偿|賠償"
)
_CJK_PROSE_MIN = 20
_LATIN_PROSE_MIN = 40
_CONTENT_REVIEW_SCHEMA_ID = (
    "https://github.com/wallmage/Alexandria/references/content-review.schema.json"
)

#: Days a time-sensitive record may lag the report date before it is stale.
FRESHNESS_WINDOW_DAYS = 30

#: R24: days as_of may run ahead of verified_at (UTC fetch vs local date).
AS_OF_DRIFT_DAYS = 1

#: Registrable-domain suffixes that occupy two labels.
MULTI_LABEL_SUFFIXES = frozenset(
    {
        "ac.uk", "co.uk", "gov.uk", "org.uk", "net.uk", "sch.uk",
        "co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp",
        "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
        "com.au", "net.au", "org.au", "gov.au", "edu.au",
        "com.hk", "org.hk", "gov.hk", "edu.hk",
        "com.tw", "org.tw", "gov.tw",
        "com.sg", "com.br", "com.mx", "com.tr", "com.ar",
        "co.in", "co.kr", "co.nz", "co.za", "co.il",
        "github.io", "gitlab.io", "readthedocs.io", "substack.com",
        "medium.com", "wordpress.com", "blogspot.com",
    }
)

#: Prose that genuinely explains a continuously updated, undated page.
CONTINUOUS_UPDATE_PATTERN = re.compile(
    r"(?i)continuous(?:ly)?[ -]updat|updated continuously|"
    r"living [a-z ]{0,24}(?:page|document|record|reference)|"
    r"rolling(?:ly)? updat|maintained in place|updated in place|"
    r"no publication date (?:is |was )?(?:shown|published|given|displayed)|"
    r"current release page|current version of the page|"
    r"持续更新|持續更新|滚动更新|滾動更新"
)

#: Claim prose that asserts something does not exist or was not found.
NEGATIVE_EXISTENCE_PATTERN = re.compile(
    r"(?i)"
    r"\bno\b[^.;]{0,60}\b(?:exists?|existed|appears? to exist|seems? to exist|"
    r"is available|are available|was available|is published|are published|"
    r"was published|were published|has been published|have been published|"
    r"is documented|is disclosed|is known|was found|were found|"
    r"could be found|was located|were located|could be located|"
    r"measures?|tracks?|reports?|benchmarks?)\b"
    r"|\bno\s+(?:published|public|independent|official|documented|verifiable|"
    r"credible|comparable|equivalent|third[- ]party|peer[- ]reviewed)\s+\w+"
    r"|\bnone\b[^.;]{0,40}\b(?:was|were|could be)\s+"
    r"(?:found|located|identified|published|available)\b"
    r"|\b(?:does|do|did)\s+not\s+(?:exist|appear to exist|publish|disclose)\b"
    r"|\b(?:we\s+|i\s+)?(?:found|located|identified)\s+no\b"
    r"|\bnothing\b[^.;]{0,40}\b(?:was|were|could be)\s+(?:found|located)\b"
    r"|\bnever\s+been\s+(?:published|disclosed|released|documented|measured)\b"
    r"|\bnot\s+publicly\s+(?:available|documented|disclosed|published)\b"
    r"|\blacks?\s+any\s+(?:public|published|independent|documented)\b"
    r"|\bno\s+(?:such|known)\s+\w+"
    r"|未找到|沒有找到|没有找到|找不到|未發現|未发现|并不存在|並不存在|"
    r"尚未公(?:布|開|开)|未(?:公開|公开)(?:過|过)?|沒有公(?:開|开)|没有公(?:開|开)"
)

#: Status assertions that must be evidenced, not appended to a faithful quote.
#: Each entry is (label, pattern in claim, pattern that would evidence it).
STATUS_ASSERTIONS = (
    ("patched", r"\b(?:since\s+)?patch(?:ed|es|ing)?\b",
     r"\b(?:patch(?:ed|es|ing)?|hotfix(?:es)?|fix(?:ed|es)?|"
     r"remediat(?:ed|ion)|resolved in|corrected in|addressed in)\b|"
     r"已修(?:复|復)"),
    ("unpatched", r"\b(?:unpatched|not patched|remains? unfixed)\b",
     r"unpatched|not patched|no patch|unfixed|未修(?:复|復)"),
    ("deprecated", r"\bdeprecat(?:ed|ion)\b",
     r"deprecat|superseded|legacy|no longer recommended"),
    ("discontinued", r"\b(?:discontinued|sunset|shut down|end[- ]of[- ]life)\b",
     r"discontinu|sunset|shut down|shutdown|end[- ]of[- ]life|retir"),
    ("recalled", r"\brecalled?\b", r"recall"),
    ("retracted", r"\bretract(?:ed|ion)\b", r"retract|withdraw"),
    ("settled", r"\bsettled?\b(?! (?:on|into))",
     r"settle|consent decree|resolution agreement"),
    ("acquired", r"\bacquired\b", r"acquir|acquisition|purchase[ds]?\b|bought"),
    ("approved", r"\bapproved\b",
     r"\b(?:approv(?:ed|al)|authoriz(?:ed|ation)|cleared|granted)\b"),
    ("banned", r"\b(?:banned|prohibited|outlawed)\b",
     r"ban(?:ned|s)?\b|prohibit|outlaw|forbidden"),
    ("certified", r"\b(?:certified|accredited)\b",
     r"certif|accredit|attestation|audit report"),
    ("open source", r"\bopen[- ]sourced?\b",
     r"open[- ]source|MIT licen|Apache-2|GPL|BSD licen|source available"),
)

DIRECTION_ASSERTIONS = (
    (
        "increase",
        r"\b(?:increase[ds]?|increasing|growth|grew|grown|rise|rose|risen|higher)\b|"
        r"增加|增長|增长|上升|提高",
        r"\b(?:increase[ds]?|increasing|growth|grew|grown|rise|rose|risen|higher)\b|"
        r"增加|增長|增长|上升|提高",
    ),
    (
        "decrease",
        r"\b(?:decrease[ds]?|decreasing|decline[ds]?|reduction|fell|fallen|lower)\b|"
        r"減少|减少|下降|降低",
        r"\b(?:decrease[ds]?|decreasing|decline[ds]?|reduction|fell|fallen|lower)\b|"
        r"減少|减少|下降|降低",
    ),
    (
        "above",
        r"\b(?:above|exceeded?)\b|高於|高于|超過|超过",
        r"\b(?:above|exceeded?)\b|高於|高于|超過|超过",
    ),
    (
        "below",
        r"\b(?:below|under)\b|低於|低于",
        r"\b(?:below|under)\b|低於|低于",
    ),
)


def mentions_person_alias(text, person):
    """Match a registered name or alias without substringing another word."""
    folded = str(text or "").casefold()
    aliases = person.get("aliases")
    aliases = aliases if isinstance(aliases, list) else []
    name = person.get("name")
    values = [name if isinstance(name, str) else None, *aliases]
    for value in values:
        alias = _text(value).casefold()
        if not alias:
            continue
        if alias.isascii():
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded):
                return True
        elif alias in folded:
            return True
    return False


def derive_person_ids(claim, people):
    """R15: recorded person_ids plus every registered person the claim names."""
    linked = claim.get("person_ids")
    linked = list(linked) if isinstance(linked, list) else []
    text = _text(claim.get("claim"))
    for person in people or ():
        if not isinstance(person, dict):
            continue
        person_id = person.get("person_id")
        if person_id and person_id not in linked and mentions_person_alias(text, person):
            linked.append(person_id)
    return linked


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "million": 1000000,
    "billion": 1000000000, "trillion": 1000000000000,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "dozen": 12, "half": 0,
}

#: Words that multiply the pending group rather than adding to it: "two dozen"
#: is 24 (not 14), "one hundred" is 100 (not 101), and "half a percent" is 0.5.
#: Their entry in _NUMBER_WORDS is an unused placeholder; the value here wins.
_GROUP_MULTIPLIERS = {"hundred": 100, "dozen": 12, "half": 0.5}

#: Number words that are also units of time or proportion. Read as a unit when
#: an article or "per" precedes them, so "half a second" is a duration rather
#: than an assertion that something equals two.
_ORDINAL_UNIT_WORDS = frozenset(
    {
        "second", "third", "quarter", "fourth", "fifth", "sixth",
        "seventh", "eighth", "ninth", "tenth",
    }
)
_UNIT_CONTEXT_RE = re.compile(r"\b(?:an?|per|the)[\s  -]+$", re.IGNORECASE)

_SCALE_WORDS = {
    "k": 1000, "thousand": 1000,
    "m": 1000000, "mm": 1000000, "million": 1000000,
    "bn": 1000000000, "b": 1000000000, "billion": 1000000000,
    "tn": 1000000000000, "trillion": 1000000000000,
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}

#: Han, kana, and CJK-compatibility ideographs. Python's ``\w`` matches every
#: one of them, so a plain ``(?<![\w.])`` guard switched the digit scan off
#: completely in ordinary Chinese prose, where numerals sit flush against the
#: characters beside them: ``全年用電量達6800萬度`` asserted no figure at all. The guard
#: still has to stop a digit inside an ASCII identifier, so CJK is subtracted
#: from it rather than the guard being dropped.
_CJK_RANGES = "\u2e80-\u9fff\uf900-\ufaff"

#: ``\b`` vanishes for the same reason between a Han character and an ASCII
#: token. These are that boundary with CJK subtracted, so dates, versions, and
#: ledger IDs stay recognizable where Chinese prose runs straight into them.
_NOT_WORD_BEFORE = r"(?<![^\W" + _CJK_RANGES + r"])"
_NOT_WORD_AFTER = r"(?![^\W" + _CJK_RANGES + r"])"

#: Chinese scale suffixes attach with no separator, so they cannot use the
#: ``\b`` the English scale words rely on. 千, 百, and 兆 stay out: the first
#: two are rare beside digits, and 兆 is read as 10**6 or 10**12 depending on
#: the writer.
_CJK_SCALE_WORDS = {
    "萬": 10000, "万": 10000,
    "億": 100000000, "亿": 100000000,
}

#: Han digits used inside a spelled-out Chinese number. 兩/两 ("two" before a
#: classifier or a unit, as in "兩個"/"兩億") folds into the same value as 二:
#: nothing here needs the grammatical distinction, only the figure.
_HAN_DIGIT_VALUES = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "两": 2,
    "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

#: 十/百/千 multiply the pending digit the way "hundred" does in
#: _word_phrase_value: "十八" is 1*10 + 8, not two unrelated numbers. Standing
#: alone at the head of a phrase they denote one unit of themselves ("十萬"
#: opens at 1*10), mirroring _word_phrase_value's `current if current else 1`.
_HAN_SMALL_UNIT_VALUES = {"十": 10, "百": 100, "千": 1000}

#: Every character a Han numeral phrase can be built from, for use inside a
#: character class. Kept as one set so _HAN_NUMBER_RE and the ordinal,
#: percent, fraction, and cheng patterns below all recognize the same span.
_HAN_NUMERAL_CHARS = "".join(
    sorted(
        set(_HAN_DIGIT_VALUES) | set(_HAN_SMALL_UNIT_VALUES) | set(_CJK_SCALE_WORDS)
    )
)

#: The decimal-point marker ("三十五點五" = 35.5, "零點八" = 0.8). Unlike a
#: whole-number phrase, every digit after it is read one at a time rather
#: than multiplied by a place-value unit ("點五" is .5, not 十/百/千/萬/億
#: acting on 五), so the suffix only ever admits bare digit characters. Kept
#: out of _HAN_NUMERAL_CHARS itself: folding 點/点 into the base character
#: class would let it stand alone (as in "兩點到四點" = "two o'clock to four
#: o'clock"), so it is only recognized as a suffix directly after a numeral
#: run and only when at least one digit follows it.
_HAN_DECIMAL_MARKER_CHARS = chr(0x9EDE) + chr(0x70B9)
_HAN_DECIMAL_DIGIT_CHARS = "".join(sorted(_HAN_DIGIT_VALUES))
_HAN_DECIMAL_SUFFIX = (
    "(?:[" + _HAN_DECIMAL_MARKER_CHARS + "][" + _HAN_DECIMAL_DIGIT_CHARS + "]+)?"
)

#: Scale words on their own, for the places a pattern needs to see one without
#: the rest of the numeral vocabulary.
_CJK_SCALE_CHARS = "".join(sorted(_CJK_SCALE_WORDS))

#: A scale word may follow the decimal suffix: "三點五萬" is 35,000 the way
#: "3.5萬" already is. Without this trailing group the numeral run ended at the
#: fractional digit, the scale word was left to match as a run of its own, and
#: that bare run then failed the leading-quantity guard below -- so a Han
#: decimal magnitude asserted no figure at all.
_HAN_NUMBER_RE = re.compile(
    "[" + _HAN_NUMERAL_CHARS + "]+"
    + _HAN_DECIMAL_SUFFIX
    + "[" + _CJK_SCALE_CHARS + "]?"
)

#: A number written with digits for the leading group and Han for the rest
#: ("3萬5千" = 35,000, "3萬" + "5千"). Scanned as one run before the digit
#: scanner can take the "3萬" off the front and leave "5" behind as a second,
#: unrelated figure. Only runs that mix the two scripts and carry material
#: after their scale word are claimed here; "6800萬" and pure Han numerals
#: stay with _NUMBER_RE and _HAN_NUMBER_RE respectively. The 之 exclusion
#: keeps the percent and fraction markers ("百分之35") with the patterns that
#: understand them.
_CJK_MIXED_NUMBER_RE = re.compile(
    _NOT_WORD_BEFORE + r"(?<![.,之])"
    + r"(?:[0-9]|[" + _HAN_NUMERAL_CHARS + r"])+"
)

#: A run ending in bare digits after its scale word is an abbreviation: the
#: trailing digits fill the places below the scale rather than the ones place,
#: so "3萬5" is 35,000 (not 30,005) and "十八萬五" is 185,000. The reading is
#: genuinely ambiguous in writing, so both are offered as acceptable forms
#: (see _scaled_number_values). An explicit 零/〇 placeholder settles it the  # noqa: RUF003
#: other way ("十萬零一" is 100,001), so those are excluded from the tail.
_CJK_ABBREVIATED_TAIL_RE = re.compile(
    "([" + _CJK_SCALE_CHARS + "])"
    + "((?:[0-9]|["
    + "".join(sorted(set(_HAN_DIGIT_VALUES) - {chr(0x96F6), chr(0x3007)}))
    + r"])+)$"
)

#: Chinese measure words gated as sufficient context for a spelled-out count,
#: mirroring how English scans every spelled count ("three CVEs", "ten
#: engineers") but Chinese numerals are far more idiomatic outside a numeric
#: context ("一起", "一些", "二手", "十分"): requiring a classifier keeps those
#: silent without a stoplist. Deliberately narrow to 個/个, the classifier in
#: both worked examples ("三個漏洞", "十八個月"); broadening it is deferred.
_CJK_COUNT_CLASSIFIERS = frozenset("個个項项名家次種种款位條条篇卷册冊")

#: R29: a quantity spelled with Han numeral words ("三位作者"), with or without
#: the classifier the scan leaves out of the display, raises no finding at all.
#: Digits, percentages, currency and dates never match, so those stay hard.
_CJK_NUMERAL_TOKEN_RE = re.compile(
    "^[" + _HAN_NUMERAL_CHARS + "]+[位次个個年月日]?$"
)


def _is_cjk_numeral_token(display):
    """R29: tag the Han-numeral quantities that carry no obligation."""
    return bool(_CJK_NUMERAL_TOKEN_RE.match(str(display or "").strip()))

#: Measure units whose figure is comparable across notations, each mapped to
#: the (dimension, factor) that converts it to that dimension's base unit. A
#: number directly followed by one of these is normalized to the base scale
#: before it is compared, so every spelling of one quantity lands on a single
#: form: 三點五千瓦, 3.5千瓦, 三千五百瓦, and 3,500瓦 are all u:W:3500.
#:
#: Normalizing is what makes the 千/百 prefix tractable at all. Those are also
#: place values, so "五千瓦" parses as 五千 + 瓦 (5,000 watts) or 五 + 千瓦
#: (5 kilowatts) -- the same physical quantity, and the same normalized form,
#: which is why the reading no longer has to be guessed. Comparing notations
#: instead compared the wrong things in both directions: a 5,000-watt claim
#: matched a 5-watt extract through the shared digit 5, and a claim of
#: 三點五千瓦 was rejected by an extract stating the identical 3,500瓦.
#:
#: 公里 and 千米 are one unit spelled two ways and cross-match by sharing a
#: dimension. Simplified and traditional spellings both, since either script
#: may appear. Deliberately a closed table: a character sequence is only read
#: as a unit if it is listed, because 千/百 are place values everywhere else
#: ("五千戶" is 5,000 households, not 5 kilo-households). 百公里 is absent on
#: purpose -- it is a unit only in per-100km constructions ("每百公里"), and
#: listing it made "三百公里" (300 km) offer a spurious reading of 3.
_CJK_MEASURE_UNITS = {
    "瓦": ("W", 1), "千瓦": ("W", 1000),
    "瓦時": ("Wh", 1), "瓦时": ("Wh", 1),
    "千瓦時": ("Wh", 1000), "千瓦时": ("Wh", 1000),
    "米": ("m", 1), "千米": ("m", 1000), "公里": ("m", 1000),
    "克": ("g", 1), "千克": ("g", 1000),
    "噸": ("t", 1), "吨": ("t", 1), "千噸": ("t", 1000), "千吨": ("t", 1000),
    "卡": ("cal", 1), "千卡": ("cal", 1000),
    "像素": ("px", 1), "百萬像素": ("px", 1000000), "百万像素": ("px", 1000000),
    "百分點": ("pp", 1), "百分点": ("pp", 1),
}

#: Longest spelling first, so "千瓦時" is not read as "千瓦" with stray prose
#: after it and "百萬像素" is not read as "像素" alone.
_CJK_MEASURE_UNIT_SPELLINGS = tuple(
    sorted(_CJK_MEASURE_UNITS, key=len, reverse=True)
)

#: Separators allowed between a figure and its unit. Digit forms are commonly
#: spaced ("0.72 千瓦"); Han forms are not, but the same gap is harmless there.
_CJK_UNIT_GAP_CHARS = " \t\u00a0\u202f\u3000"

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_LEDGER_ID_RE = re.compile(
    _NOT_WORD_BEFORE + r"[CS][0-9]{1,7}" + _NOT_WORD_AFTER
)
_IDENTIFIER_RE = re.compile(
    _NOT_WORD_BEFORE
    + r"[A-Za-z]{2,}[-‑][0-9][0-9A-Za-z‑-]*"
    + _NOT_WORD_AFTER
)
#: 1949-12-1 is the same day as 1949-12-01: sources write the month and day
#: unpadded as readily as padded, so both notations parse to one form.
_ISO_DATE_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})" + _NOT_WORD_AFTER
)
_ISO_MONTH_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})-([0-9]{1,2})" + _NOT_WORD_AFTER
)
_VERSION_RE = re.compile(
    _NOT_WORD_BEFORE + r"[vV]?([0-9]+(?:\.[0-9]+){2,})" + _NOT_WORD_AFTER
)
_NUMBER_RE = re.compile(
    _NOT_WORD_BEFORE + r"(?<!\.)"
    r"([0-9]+(?:[,\u00a0\u202f][0-9]{3})*(?:\.[0-9]+)?)(?![0-9])"
    r"(?:\s*(?:(k|mm|m|bn|b|tn|thousand|million|billion|trillion)\b"
    r"|(" + "|".join(_CJK_SCALE_WORDS) + r")))?",
    re.IGNORECASE,
)
_NUMBER_WORD_ALT = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))

#: One spelled-out number, however many words spell it: "twenty-five",
#: "four hundred million", "one hundred and fifty". Members join with a space,
#: a hyphen, or "and". The trailing boundary admits a directly attached
#: multiple ("threefold", "tenfold") without matching a word that merely starts
#: with a number word: "tender" and "secondary" still need a non-letter after.
_WORD_NUMBER_RE = re.compile(
    r"\b(?:" + _NUMBER_WORD_ALT + r")"
    r"(?:[\s  -]+(?:and[\s  -]+)?(?:" + _NUMBER_WORD_ALT + r"))*"
    r"(?=fold\b|[^A-Za-z]|$)",
    re.IGNORECASE,
)

_NUMBER_WORD_TOKEN_RE = re.compile(r"\b(" + _NUMBER_WORD_ALT + r")\b", re.IGNORECASE)


def _word_phrase_value(phrase):
    """Assemble a spelled-out number phrase into the value it denotes.

    Additive members accumulate ("twenty" + "five" -> 25); "hundred" multiplies
    the pending group; a larger scale word closes the group and adds it to the
    running total, so "four hundred million" is 400,000,000 rather than three
    unrelated numbers.
    """
    total = 0
    current = 0
    seen = False
    for word in _NUMBER_WORD_TOKEN_RE.findall(phrase):
        value = _NUMBER_WORDS[word.casefold()]
        seen = True
        if word.casefold() in _GROUP_MULTIPLIERS:
            multiplier = _GROUP_MULTIPLIERS[word.casefold()]
            current = (current if current else 1) * multiplier
        elif value >= 1000:
            total += (current or 1) * value
            current = 0
        else:
            current += value
    if not seen:
        return 0
    value = total + current
    # Keep integral results integral so the word form and the digit form share
    # a key: the digit scanner emits n:1, never n:1.0.
    return int(value) if float(value).is_integer() else value

def _han_phrase_value(phrase):
    """Assemble a Han-numeral phrase into the value it denotes.

    Mirrors _word_phrase_value's grouping, but Chinese groups by 10,000
    (萬/万) and 100,000,000 (億/亿) rather than by 1,000: 十/百/千 multiply the
    pending digit within the current group ("十八" -> 1*10 + 8 = 18), and a
    scale word closes the group and adds it to the running total ("三千萬" ->
    (3*1000)*10000 = 30,000,000, "六億" -> 6*100,000,000).

    A run of ASCII digits counts as one pending digit, so a phrase that writes
    its leading group with digits and the rest in Han ("3萬5千") resolves as the
    single number it denotes rather than as two.
    """
    total = 0
    group = 0
    current = None
    pending = ""

    for char in phrase + " ":
        if "0" <= char <= "9":
            pending += char
            continue
        if pending:
            current = int(pending)
            pending = ""
        if char in _HAN_DIGIT_VALUES:
            current = _HAN_DIGIT_VALUES[char]
        elif char in _HAN_SMALL_UNIT_VALUES:
            group += (current if current is not None else 1) * _HAN_SMALL_UNIT_VALUES[char]
            current = None
        elif char in _CJK_SCALE_WORDS:
            total += (group + (current or 0)) * _CJK_SCALE_WORDS[char]
            group = 0
            current = None
    return total + group + (current or 0)


def _scaled_decimal_string(raw, scale):
    """Multiply a decimal string by a scale word's factor exactly.

    Decimal, not float: "零點八億" is 80,000,000, and 0.8 * 10**8 in binary
    floating point is 80000000.00000001, which normalizes to a figure no
    extract will ever carry.
    """
    value = Decimal(raw) * scale
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _han_numeral_string(phrase):
    """Return the normalized digit string a (possibly decimal) Han phrase denotes.

    A 點/点 marker splits the phrase into a whole part, resolved the normal
    way through _han_phrase_value, and a fractional part read digit-by-digit
    ("三十五點五" -> whole 35, fraction "5" -> "35.5"; "零點八" -> "0.8"), never
    through a place-value unit: "點五" is always .5, not 十/百/千 acting on 五.
    The result is passed through _normalize_number so a Han decimal and its
    digit-form equivalent land on the same key regardless of trailing zeros
    ("三十五點五零" and "35.50" both normalize to "35.5").

    A scale word after the fractional digits multiplies the decimal, the way it
    would in digit form: "三點五萬" is 35,000 exactly as "3.5萬" is. The two
    machineries did not compose before, so a Han decimal magnitude asserted
    nothing.
    """
    for marker in _HAN_DECIMAL_MARKER_CHARS:
        if marker in phrase:
            whole, _, rest = phrase.partition(marker)
            fraction_digits = ""
            scale = 1
            for char in rest:
                if char in _CJK_SCALE_WORDS:
                    scale *= _CJK_SCALE_WORDS[char]
                elif char in _HAN_DIGIT_VALUES and scale == 1:
                    fraction_digits += str(_HAN_DIGIT_VALUES[char])
            raw = (
                f"{_han_phrase_value(whole)}.{fraction_digits}"
                if fraction_digits
                else str(_han_phrase_value(whole))
            )
            if scale != 1:
                raw = _scaled_decimal_string(raw, scale)
            return _normalize_number(raw)
    return _normalize_number(str(_han_phrase_value(phrase)))


def _scaled_phrase_is_ambiguous(phrase):
    """True when a scaled phrase opens with an implied 1 rather than a figure.

    "萬一" ("just in case") and the adverb "千萬" ("by all means") read as
    10,000 and 10,000,000 only if the missing leading quantity is filled in the
    way English fills it for a bare "a million". Chinese idiom makes that
    reading wrong far too often, so a scaled figure has to carry its own
    leading quantity. 十/百 count as one ("十八萬" is 180,000, "百萬" is a
    million); it is specifically a phrase that opens *on* the scale word, or the
    adverb 千萬/千億, that stays silent.
    """
    if not phrase:
        return True
    if phrase[0] in _CJK_SCALE_WORDS:
        return True
    return (
        phrase[0] == chr(0x5343)
        and len(phrase) > 1
        and phrase[1] in _CJK_SCALE_WORDS
    )


def _cjk_measure_unit_after(text, start):
    """Return (unit, source) for a listed measure unit sitting at `start`.

    `source` is the text the unit occupies, leading gap included, so a caller
    can display the figure with its unit ("0.72 千瓦"). None when the text at
    `start` is not a listed unit.
    """
    offset = start
    while offset < len(text) and text[offset] in _CJK_UNIT_GAP_CHARS:
        offset += 1
    for unit in _CJK_MEASURE_UNIT_SPELLINGS:
        if text.startswith(unit, offset):
            return unit, text[start : offset + len(unit)]
    return None


def _cjk_absorbed_measure_unit(span, text, start):
    """Resolve a measure unit whose own prefix was swallowed by the numeral run.

    Returns (unit, numeral, source) or None. 千 and 百 are place values as well
    as unit prefixes, so a greedy numeral run takes them: "五百" + "分點" is
    五 + 百分點, five percentage points. Where the remainder after the prefix is
    itself a listed unit the direct reading already covers the phrase and
    normalizes to the same value (千瓦 is worth exactly the 千 the run
    swallowed), so this is only reached for a unit like 百分點 whose remainder
    stands for nothing on its own.

    The swallowed prefix has to actually multiply what is left of the run, and
    that is checked arithmetically rather than assumed: 五百 is 五 hundreds, so
    "五百分點" is 5 percentage points, but 三千五百 is not 三千五 hundreds, so
    "三千五百分點" is not a unit phrase at all and keeps its plain reading.
    """
    for unit in _CJK_MEASURE_UNIT_SPELLINGS:
        for taken in range(1, len(unit)):
            prefix, rest = unit[:taken], unit[taken:]
            if not span.endswith(prefix) or not text.startswith(rest, start):
                continue
            numeral = span[:-taken]
            if not numeral:
                continue
            if _han_phrase_value(span) != _han_phrase_value(
                numeral
            ) * _han_phrase_value(prefix):
                continue
            return unit, numeral, text[start : start + len(rest)]
    return None


def _unit_normalized_forms(values, unit):
    """Forms for a figure that carries a measure unit.

    Each value is converted to the unit's base scale and emitted twice: tagged
    with its dimension, so only a quantity of the same magnitude in the same
    dimension satisfies it however either side spells the unit, and untagged,
    so evidence that states the base figure without a unit ("3,500") still
    counts. The un-normalized figure is deliberately not offered untagged: a
    bare n:5 for 五千瓦 is what let a 5,000-watt claim pass on 5瓦.
    """
    dimension, factor = _CJK_MEASURE_UNITS[unit]
    forms = set()
    for value in values:
        base = _normalize_number(_scaled_decimal_string(value, factor))
        forms.add(f"u:{dimension}:{base}")
        forms.add(f"n:{base}")
    return forms


def _scaled_number_values(phrase):
    """Acceptable values for one scaled number run.

    Normally the single value the run denotes. A run ending in bare digits
    after its scale word is ambiguous in writing -- "3萬5" is 35,000 read as an
    abbreviation and 30,005 read strictly by place value -- so both readings are
    offered: the run still has to find *a* matching figure in the evidence, but
    a correct extract is not rejected over a reading the writer did not intend.
    """
    values = {_han_numeral_string(phrase)}
    match = _CJK_ABBREVIATED_TAIL_RE.search(phrase)
    if match:
        digits = "".join(
            str(_HAN_DIGIT_VALUES[char]) if char in _HAN_DIGIT_VALUES else char
            for char in match.group(2)
        )
        place = _CJK_SCALE_WORDS[match.group(1)] // 10 ** len(digits)
        if place:
            head = _han_phrase_value(phrase[: match.start(2)])
            values.add(str(head + int(digits) * place))
    return values


#: Historical vocabulary from the retired magnitude-specific word-number
#: check. Spelled-out counts create obligations equivalent to their digit
#: forms; vague number-like words such as "dozens" do not.
_MAGNITUDE_UNITS = (
    # proportion and multiple
    r"%|per ?cents?|percents?|percentage ?points?|basis ?points?|pc|pct"
    r"|times|fold|x"
    # currency
    r"|dollars?|euros?|pounds?|cents?|pence|yen|yuan|rmb|usd|eur|gbp|jpy|cny"
    # time
    r"|nanoseconds?|microseconds?|milliseconds?|seconds?|minutes?|hours?"
    r"|days?|weeks?|months?|quarters?|years?|decades?|centuries|century"
    # data and compute
    r"|bits?|bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|petabytes?"
    r"|kb|mb|gb|tb|pb|tokens?|flops?"
    # physical
    r"|millimet(?:re|er)s?|centimet(?:re|er)s?|met(?:re|er)s?"
    r"|kilomet(?:re|er)s?|miles?|feet|foot|inch(?:es)?|acres?|hectares?"
    r"|milligrams?|grams?|kilograms?|tons?|tonnes?|pounds?"
    r"|millilit(?:re|er)s?|lit(?:re|er)s?|gallons?"
    r"|watts?|kilowatts?|megawatts?|gigawatts?|terawatts?|volts?|amps?"
    r"|joules?|hertz|kilohertz|megahertz|gigahertz|degrees?|celsius"
    # scale words, so "four hundred" and "four billion" always count
    r"|hundreds?|thousands?|millions?|billions?|trillions?"
)

#: A unit may follow the number after a space, a hyphen, or nothing at all
#: ("fifty percent", "fifty-percent", "threefold").
#: A fraction is a proportion, not a figure: "two-thirds" asserts 2/3, never 2.
#: Emitting the numerator matched the wrong value in an extract, so a fraction
#: yields no obligation at all. Vague proportions are the content review's job.
_FRACTION_WORD_RE = re.compile(
    r"[\s\u00a0\u202f-]*(?:halves|halfs?|thirds?|quarters?|fifths?|sixths?"
    r"|sevenths?|eighths?|ninths?|tenths?)\b",
    re.IGNORECASE,
)

#: Ordinal marker: a position, not a figure. English gets this exclusion for
#: free only incidentally, when an ordinal-unit word follows "the" (see
#: word_number's _UNIT_CONTEXT_RE check); the Chinese marker character is
#: unambiguous, so it is excluded outright and matched first, before anything
#: below can see the numeral that follows it.
_CJK_ORDINAL_MARKER = chr(0x7B2C)
_CJK_ORDINAL_RE = re.compile(re.escape(_CJK_ORDINAL_MARKER) + "[" + _HAN_NUMERAL_CHARS + "]+")

#: Percent marker (literally "out of a hundred, ..."): a figure exactly the
#: way "12%" is. Matched and blanked before _CJK_FRACTION_RE below, because
#: the percent marker itself contains the fraction pattern's connector
#: substring, and would otherwise parse as a fraction over 100 and lose its
#: obligation entirely. The captured group admits the decimal suffix so
#: "百分之三十五點五" resolves to 35.5, not a truncated 35.
_CJK_PERCENT_MARKER = chr(0x767E) + chr(0x5206) + chr(0x4E4B)
_CJK_PERCENT_RE = re.compile(
    re.escape(_CJK_PERCENT_MARKER)
    + "([" + _HAN_NUMERAL_CHARS + "]+" + _HAN_DECIMAL_SUFFIX + ")"
)

#: A bare "X <connector> Y" is a proportion ("three-connector-two" = 2/3),
#: mirroring _FRACTION_WORD_RE's exclusion of "two-thirds": emitting either
#: side matched the wrong value in an extract, so it asserts no figure at all.
_CJK_FRACTION_CONNECTOR = chr(0x5206) + chr(0x4E4B)
_CJK_FRACTION_RE = re.compile(
    "[" + _HAN_NUMERAL_CHARS + "]+"
    + re.escape(_CJK_FRACTION_CONNECTOR)
    + "[" + _HAN_NUMERAL_CHARS + "]+"
)

#: The cheng ("tenths") percent marker: "six-cheng-eight" is 68%, cheng being
#: tenths, so a trailing digit after it is read as ones (6*10 + 8); "three
#: cheng" alone is 30%. The leading digit also admits "ten" ("ten-cheng" =
#: 100%); the trailing one is a bare 0-9 digit, never a unit.
_CJK_CHENG_MARKER = chr(0x6210)
_CJK_CHENG_RE = re.compile(
    "([" + "".join(sorted(set(_HAN_DIGIT_VALUES) | {chr(0x5341)})) + "])"
    + re.escape(_CJK_CHENG_MARKER)
    + "([" + "".join(sorted(_HAN_DIGIT_VALUES)) + "])?"
)

_MONTH_NAME_DATE_RE = re.compile(
    r"(?i)\b(?:([0-9]{1,2})\s+)?(" + "|".join(sorted(_MONTHS, key=len, reverse=True))
    + r")\.?\s+(?:([0-9]{1,2})(?:st|nd|rd|th)?,?\s+)?([0-9]{4})\b"
)
_SLASH_DATE_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})" + _NOT_WORD_AFTER
)
#: 1948.11.24 is a date, not a three-part version; normalizing it here keeps the
#: version scan from claiming it.
_DOT_DATE_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})\.([0-9]{1,2})\.([0-9]{1,2})" + _NOT_WORD_AFTER
)
#: 2026年7月28日 is one date, exactly as "28 July 2026" is. Left as bare digits it
#: would assert three separate figures, so it is normalized like every other
#: date form. A bare 2026年 stays a number, which is what "in 2026" already does.
_CJK_DATE_RE = re.compile(
    r"([0-9]{4})\s*年\s*([0-9]{1,2})\s*月(?:\s*([0-9]{1,2})\s*日)?"
)
#: "1931年9月18-20日" (with any dash) names two days, not a 0918-20 token: the
#: range is expanded into its two end dates before anything else reads them.
_CJK_DATE_RANGE_RE = re.compile(
    r"(?:([0-9]{4})\s*年\s*)?(?:([0-9]{1,2})\s*月\s*)?"
    r"([0-9]{1,2})\s*[-‐‑‒–—~〜至]\s*([0-9]{1,2})\s*日"
)


def _duplicates(values):
    seen = set()
    return sorted({value for value in values if value in seen or seen.add(value)})


def _normalized_family(value):
    return " ".join(
        re.sub(r"[\W_]+", " ", str(value or ""), flags=re.UNICODE).split()
    ).casefold()


def _registrable_domain(value):
    """Return the registrable domain of a URL, or '' when it has no host."""
    try:
        host = urlsplit(str(value or "").strip()).hostname or ""
    except ValueError:
        return ""
    host = host.casefold().strip(".")
    if not host or host.replace(".", "").isdigit():
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _normalize_number(raw):
    text = re.sub(r"[,  \s]", "", str(raw))
    if "." in text:
        whole, _, fraction = text.partition(".")
        fraction = fraction.rstrip("0")
        whole = whole.lstrip("0") or "0"
        return f"{whole}.{fraction}" if fraction else whole
    return text.lstrip("0") or "0"


def _expand_date_ranges(match):
    year = f"{match.group(1)}年" if match.group(1) else ""
    month = f"{match.group(2)}月" if match.group(2) else ""
    return (
        f"{year}{month}{match.group(3)}日 {year}{month}{match.group(4)}日"
    )


def _normalize_dates(text):
    text = _CJK_DATE_RANGE_RE.sub(_expand_date_ranges, text)
    text = _CJK_DATE_RE.sub(
        lambda match: (
            f"{match.group(1)}-{int(match.group(2)):02d}"
            + (f"-{int(match.group(3)):02d}" if match.group(3) else "")
        ),
        text,
    )
    text = _SLASH_DATE_RE.sub(
        lambda match: (
            f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        ),
        text,
    )
    text = _DOT_DATE_RE.sub(
        lambda match: (
            f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        ),
        text,
    )

    def month_name(match):
        month = _MONTHS[match.group(2).casefold()]
        day = match.group(1) or match.group(3)
        year = match.group(4)
        if day:
            return f"{year}-{month:02d}-{int(day):02d}"
        return f"{year}-{month:02d}"

    return _MONTH_NAME_DATE_RE.sub(month_name, text)


def _prose_minimum(text):
    value = _text(text)
    if not value:
        return _LATIN_PROSE_MIN
    cjk = sum(1 for char in value if "\u3400" <= char <= "\u9fff")
    return _CJK_PROSE_MIN if cjk * 2 >= len(value) else _LATIN_PROSE_MIN


def _trigger_has_carrier(text, match):
    window = text[max(0, match.start() - 48) : match.end() + 48]
    return bool(_NUMERIC_OR_LEGAL_CARRIER.search(window))


def _parse_date_form(form):
    if not form.startswith("d:"):
        return None
    body = form[2:]
    year = month = day = None
    if body.startswith("*-*-"):
        day = body[4:]
    elif body.startswith("*-"):
        rest = body[2:]
        month, _, day = rest.partition("-")
        day = day or None
    else:
        parts = body.split("-")
        year = parts[0]
        if len(parts) > 1:
            month = parts[1]
        if len(parts) > 2:
            day = parts[2]
    return year, month, day


def _date_fragment_covered(claim_form, evidence_form):
    claim = _parse_date_form(claim_form)
    evidence = _parse_date_form(evidence_form)
    if not claim or not evidence:
        return False
    cy, cm, cd = claim
    ey, em, ed = evidence
    if cy and ey != cy:
        return False
    if cm and (not em or int(em) != int(cm)):
        return False
    if cd and (not ed or int(ed) != int(cd)):
        return False
    if cy and not ey:
        return False
    if cm and not em:
        return False
    return not (cd and not ed)


#: R21: a 4-digit number is read as a year only inside this range.
_YEAR_RANGE = range(1000, 3000)


def _year_number_coverage(claim_forms, evidence_forms):
    """R21: an extract cut before 年 still states the year as a plain number.

    "…蒋介石1917" offers `n:1917`, which is the very figure the claim's
    `1917年` asserts; only the character that made it a date is missing.
    """
    for claim_form in claim_forms:
        parts = _parse_date_form(claim_form)
        if not parts:
            continue
        year, month, day = parts
        if month or day or not (year and year.isdigit()):
            continue
        if int(year) in _YEAR_RANGE and f"n:{int(year)}" in evidence_forms:
            return True
    return False


def _year_documented_coverage(claim_forms, evidence_forms, source_text):
    """R14: a month-day (or day) fragment covers the claim's full date when the
    parts the extract omits are stated elsewhere in the same source (cached
    text, title or published date). Without that text the rule is unchanged.

    R14b: the same holds for a year-month claim (`1945年8月`) against a
    month-day fragment of that month (`8月2日`).

    R29: a claim that names no year (`12月13日`) needs only its month
    documented in the source to be covered by a bare `13日` extract."""
    if not source_text:
        return False
    for claim_form in claim_forms:
        parts = _parse_date_form(claim_form)
        if not parts:
            continue
        year, month, day = parts
        if not month:
            continue
        if year and not re.search(rf"(?<!\d){year}(?!\d)", source_text):
            continue
        if not day:
            if any(
                form.startswith(f"d:*-{int(month):02d}-")
                for form in evidence_forms
            ):
                return True
            continue
        if f"d:*-{int(month):02d}-{int(day):02d}" in evidence_forms:
            return True
        if f"d:*-*-{int(day):02d}" in evidence_forms and re.search(
            rf"(?<!\d){int(month)}\s*月|-{int(month):02d}-", source_text
        ):
            return True
    return False



def _claim_field_fix(field):
    """A claim field re-enters the ledger only through `claim add`."""
    return f"set field {field} in claims/*.json, then alx claim add claims/*.json"


#: R23: the synthesis field is merged, not re-added with a claim.
ADVERSARIAL_TESTS_FIX = (
    "put the counterevidence id in synthesis.adversarial_tests in a patch "
    "file, then alx ledger merge <patch>"
)
COVERAGE_PATCH_FIX = (
    "set coverage[i].claim_ids to supported claim ids in a patch file, "
    "then alx ledger merge <patch>"
)
PROVENANCE_INDEPENDENT_FIX = (
    "alx source set {sid} --provenance primary_independent only if the "
    "page truly is; otherwise fetch an independent one"
)


def _claim_set_fix(field):
    return f"set field {field} in claims/<file>, then alx claim add claims/<file>"


def _synthesis_ids_fix(ids):
    named = " ".join(ids) if ids else "C1 C2 …"
    return (
        f"put {named} in synthesis.central_judgment_claim_ids in a patch "
        "file, then alx ledger merge <patch>"
    )


def _family_justification_fix(source_id, *, parties):
    return (
        f"write ≥40 characters on why these pages are {parties} into "
        f"family-justification.txt, then alx source set {source_id} "
        "--family-justification family-justification.txt"
    )


def _key_claim_fix(claim_id):
    return (
        f"fetch an independent page for {claim_id}, add it to source_evidence "
        "and alx claim add; or set field importance \"supporting\" and re-add"
    )


def _scan_quantities(text):
    """Yield (display, claim_forms, evidence_forms, is_word) for a string.

    URLs and ledger IDs are ignored. Other identifiers, dates, versions, digit
    forms, and spelled-out counts create obligations. Spelled-out counts use
    their digit-equivalent forms; vague number-like words such as "dozens" do
    not create obligations.
    """
    working = unicodedata.normalize("NFKC", str(text or ""))
    for mark in _CJK_SENTENCE_PUNCT:
        working = working.replace(mark, " ")
    working = _URL_RE.sub(" ", working)
    working = _LEDGER_ID_RE.sub(" ", working)
    working = _CJK_DATE_RANGE_RE.sub(_expand_date_ranges, working)
    tokens = []

    def take(pattern, handler):
        nonlocal working
        parts = []
        last = 0
        for match in pattern.finditer(working):
            token = handler(match)
            if token is None:
                continue
            tokens.append(token)
            parts.append(working[last : match.start()])
            parts.append(" " * (match.end() - match.start()))
            last = match.end()
        parts.append(working[last:])
        working = "".join(parts)

    def identifier(match):
        raw = match.group(0)
        form = "id:" + _normalized_family(raw).replace(" ", "-")
        return (raw, {form}, {form}, False)

    def iso_date(match):
        year, month, day = match.group(1), match.group(2), match.group(3)
        form = f"d:{year}-{int(month):02d}-{int(day):02d}"
        return (match.group(0), {form}, {form}, False)

    def iso_month(match):
        year, month = match.group(1), match.group(2)
        form = f"d:{year}-{int(month):02d}"
        return (match.group(0), {form}, {form}, False)

    def version(match):
        form = "v:" + match.group(1)
        return (match.group(0), {form}, {form}, False)

    def number(match):
        normalized = _normalize_number(match.group(1))
        values = {normalized}
        scale = _SCALE_WORDS.get(
            (match.group(2) or "").casefold()
        ) or _CJK_SCALE_WORDS.get(match.group(3) or "")
        if scale:
            try:
                scaled = float(normalized) * scale
            except ValueError:
                scaled = None
            if scaled is not None and scaled == int(scaled):
                # The scale word is part of the asserted figure: "6800萬" means
                # 68,000,000 and nothing else. Keeping the bare digits as an
                # acceptable form let "6800萬" match an extract saying "6800億"
                # (and "5 million" match "5 billion") through the shared digits.
                values = {str(int(scaled))}
        # A digit form takes a measure unit as readily as a Han one, and the
        # two notations have to normalize identically for either to recognize
        # the other: "3.5 千瓦" and "3,500瓦" are one quantity.
        unit = _cjk_measure_unit_after(working, match.end())
        if unit is not None:
            spelling, source = unit
            forms = _unit_normalized_forms(values, spelling)
            return (match.group(0).strip() + source, forms, set(forms), False)
        forms = {f"n:{value}" for value in values}
        return (match.group(0).strip(), forms, set(forms), False)

    def word_number(match):
        # "half a second" is a duration; without this, `second` scanned as the
        # ordinal two and asserted a figure the sentence never made.
        head = text[max(0, match.start() - 12) : match.start()]
        if match.group(0).casefold() in _ORDINAL_UNIT_WORDS and _UNIT_CONTEXT_RE.search(
            head
        ):
            return (match.group(0), set(), set(), True)
        # A spelled-out number is one figure however many words spell it.
        # Scanning word by word produced {20, 5} for "twenty-five", which both
        # failed a claim against an extract reading "25%" and passed the same
        # claim against one reading "5%".
        forms = {f"n:{_word_phrase_value(match.group(0))}"}
        # A spelled-out count ("three CVEs") is ordinary prose and must not
        # manufacture an obligation. A spelled-out *magnitude* ("fifty percent",
        # "four billion dollars") asserts a figure exactly as a digit would, and
        # writing it as a word was otherwise a clean way past this check.
        tail = text[match.end() : match.end() + 32]
        if _FRACTION_WORD_RE.match(tail):
            return (match.group(0), set(), set(), True)
        return (
            match.group(0),
            forms,
            forms,
            False,
        )

    def han_ordinal(match):
        return (match.group(0), set(), set(), True)

    def han_percent(match):
        forms = {f"n:{_han_numeral_string(match.group(1))}"}
        return (match.group(0), forms, set(forms), False)

    def han_fraction(match):
        return (match.group(0), set(), set(), True)

    def han_cheng(match):
        value = _han_phrase_value(match.group(1)) * 10 + (
            _HAN_DIGIT_VALUES[match.group(2)] if match.group(2) else 0
        )
        forms = {f"n:{value}"}
        return (match.group(0), forms, set(forms), False)

    def mixed_number(match):
        # "3萬5千" is one number (35,000). Left to _NUMBER_RE it lost its tail:
        # the scan asserted 30,000 and a separate 5, which rejected the correct
        # "35,000" and passed a fabricated extract carrying "30000" and "5".
        span = match.group(0)
        if not any("0" <= char <= "9" for char in span):
            return None  # pure Han: _HAN_NUMBER_RE's job
        scale_at = next(
            (index for index, char in enumerate(span) if char in _CJK_SCALE_WORDS),
            None,
        )
        if scale_at is None or scale_at == len(span) - 1:
            # No scale word, or nothing after it ("6800萬"): _NUMBER_RE already
            # reads those correctly, including the "6800 萬" spaced form it
            # accepts and this contiguous run cannot see.
            return None
        if _scaled_phrase_is_ambiguous(span):
            return None
        values = _scaled_number_values(span)
        unit = _cjk_measure_unit_after(working, match.end())
        if unit is not None:
            spelling, source = unit
            forms = _unit_normalized_forms(values, spelling)
            return (span + source, forms, set(forms), False)
        forms = {f"n:{value}" for value in values}
        return (span, forms, set(forms), False)

    def han_number(match):
        span = match.group(0)
        # A listed measure unit is quantitative context in its own right, the
        # way a classifier is, and it fixes the figure's scale: without it
        # "功率三點五千瓦" reached the classifier gate below with an
        # unrecognized unit character in the tail and asserted nothing at all.
        unit = _cjk_measure_unit_after(working, match.end())
        if unit is not None and span in _HAN_SMALL_UNIT_VALUES:
            # The run is nothing but the unit's own prefix character: "千瓦電力"
            # names a unit, "每百公里" is a per-100km rate, and "數千瓦" is
            # vague. Each would otherwise assert the prefix's place value as a
            # figure, so a unit phrase needs a leading quantity of its own
            # exactly as a scaled one does.
            unit = None
        scaled = any(char in _CJK_SCALE_WORDS for char in span)
        if scaled:
            # "萬一" and the adverb "千萬" ("by all means") open with an
            # implied 1 the way a bare "million" would in English ("Revenue
            # reached a million dollars"); unlike English, that implied 1
            # collides with real idioms, so a scaled figure needs a leading
            # quantity of its own ("三千萬", "十八萬", "六億").
            if _scaled_phrase_is_ambiguous(span):
                return (span, set(), set(), True)
            values = _scaled_number_values(span)
        else:
            values = {_han_numeral_string(span)}
        if unit is not None:
            spelling, source = unit
            forms = _unit_normalized_forms(values, spelling)
            return (span + source, forms, set(forms), False)
        if scaled:
            forms = {f"n:{value}" for value in values}
            return (span, forms, set(forms), False)
        # The run may instead have swallowed the unit's own prefix character,
        # which only a 千/百 place value can do (see
        # _cjk_absorbed_measure_unit).
        absorbed = _cjk_absorbed_measure_unit(span, working, match.end())
        if absorbed is not None:
            spelling, numeral, source = absorbed
            forms = _unit_normalized_forms({_han_numeral_string(numeral)}, spelling)
            return (span + source, forms, set(forms), False)
        # No scale word: an ordinary count, gated on a following classifier
        # the same way "三個漏洞" and "十八個月" are in the brief. Bare "一" is
        # excluded unconditionally: it is Chinese's indefinite article
        # ("一個" = "a", not "1"), a role English gives to a separate word
        # ("a"/"an") that never appears in _NUMBER_WORDS.
        if span == "一":
            return (span, set(), set(), True)
        tail = working[match.end() : match.end() + 1]
        if tail not in _CJK_COUNT_CLASSIFIERS:
            return (span, set(), set(), True)
        forms = {f"n:{_han_numeral_string(span)}"}
        return (span, forms, set(forms), False)

    def cjk_month_day(match):
        month, day = int(match.group(1)), int(match.group(2))
        form = f"d:*-{month:02d}-{day:02d}"
        return (match.group(0), {form}, {form}, False)

    def cjk_year_only(match):
        form = f"d:{match.group(1)}"
        return (match.group(0), {form}, {form}, False)

    def cjk_month_only(match):
        form = f"d:*-{int(match.group(1)):02d}"
        return (match.group(0), {form}, {form}, False)

    def cjk_day_only(match):
        form = f"d:*-*-{int(match.group(1)):02d}"
        return (match.group(0), {form}, {form}, False)

    def surface_cjk_date(match):
        form = f"d:{match.group(1)}-{int(match.group(2)):02d}"
        if match.group(3):
            form += f"-{int(match.group(3)):02d}"
        return (match.group(0), {form}, {form}, False)

    def surface_ymd_date(match):
        form = (
            f"d:{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        )
        return (match.group(0), {form}, {form}, False)

    def surface_month_name_date(match):
        month = _MONTHS[match.group(2).casefold()]
        day = match.group(1) or match.group(3)
        year = match.group(4)
        form = (
            f"d:{year}-{month:02d}-{int(day):02d}"
            if day
            else f"d:{year}-{month:02d}"
        )
        return (match.group(0), {form}, {form}, False)

    take(_CJK_DATE_RE, surface_cjk_date)
    take(_SLASH_DATE_RE, surface_ymd_date)
    take(_DOT_DATE_RE, surface_ymd_date)
    take(_MONTH_NAME_DATE_RE, surface_month_name_date)
    working = _normalize_dates(working)
    take(_IDENTIFIER_RE, identifier)
    take(_ISO_DATE_RE, iso_date)
    take(_ISO_MONTH_RE, iso_month)
    take(_VERSION_RE, version)
    take(re.compile(r"([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日"), cjk_month_day)
    take(re.compile(r"([0-9]{4})\s*年"), cjk_year_only)
    take(re.compile(r"([0-9]{1,2})\s*月"), cjk_month_only)
    take(re.compile(r"([0-9]{1,2})\s*日"), cjk_day_only)
    take(_CJK_MIXED_NUMBER_RE, mixed_number)
    take(_NUMBER_RE, number)
    take(_WORD_NUMBER_RE, word_number)
    take(_CJK_ORDINAL_RE, han_ordinal)
    take(_CJK_PERCENT_RE, han_percent)
    take(_CJK_FRACTION_RE, han_fraction)
    take(_CJK_CHENG_RE, han_cheng)
    take(_HAN_NUMBER_RE, han_number)
    return tokens


def quantitative_obligations(text):
    """Return (display, acceptable forms) for every number a claim asserts."""
    return [
        (display, claim_forms)
        for display, claim_forms, _, is_word in _scan_quantities(text)
        if claim_forms and not is_word
    ]


def quantitative_evidence(*texts):
    """Return every quantitative form the supplied evidence text offers."""
    forms = set()
    for text in texts:
        for _, _, evidence_forms, _ in _scan_quantities(text):
            forms |= evidence_forms
        # R29: as evidence, a Han ordinal (第十三) or year count (十三周年,
        # 十三年) offers its digit value: a figure the page spells out is never
        # a fabrication in the claim that writes it as 13.
        for match in _HAN_ORDINAL_OR_YEAR_RE.finditer(str(text or "")):
            span = match.group(1) or match.group(2)
            if span in {"一", "零"} or any(char in _CJK_SCALE_WORDS for char in span):
                continue
            forms.add(f"n:{_han_numeral_string(span)}")
    return forms


_HAN_ORDINAL_OR_YEAR_RE = re.compile(
    re.escape(_CJK_ORDINAL_MARKER)
    + "([" + _HAN_NUMERAL_CHARS + "]+)"
    + "|([" + _HAN_NUMERAL_CHARS + "]+)(?=周年|年)"
)


def _quantity_is_covered(claim_forms, evidence_forms):
    for form in claim_forms:
        if form.startswith("n:"):
            if form in evidence_forms:
                return True
            continue
        if form in evidence_forms:
            return True
        if form.startswith("d:") and any(
            other.startswith("d:") and _date_fragment_covered(form, other)
            for other in evidence_forms
        ):
            return True
    return False


def _normalized_url(value):
    try:
        parts = urlsplit(str(value or "").strip())
    except ValueError:
        return str(value or "").strip().casefold()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path,
            parts.query,
            "",
        )
    )


def _text(value):
    return str(value or "").strip()


def _exact_expression_in_text(expression, text):
    expression = _text(expression)
    text = _text(text)
    if not expression:
        return False
    if expression.isascii():
        return re.search(
            rf"(?<!\w){re.escape(expression)}(?!\w)",
            text,
            re.IGNORECASE,
        ) is not None
    return expression in text


def _claim_evidence_text(claim):
    """Return authoritative per-source evidence, with legacy test fallback."""
    records = claim.get("source_evidence")
    extracts = [
        _text(record.get("extract_or_location"))
        for record in records
        if isinstance(record, dict)
        and _text(record.get("extract_or_location"))
    ] if isinstance(records, list) else []
    if extracts:
        return " ".join(extracts)
    return _text(claim.get("extract_or_location"))


def _derived_entries(claim):
    entries = claim.get("derived_assertions")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(
        entries, list
    ) else []


def _derived_findings(claim):
    """Keep the derived-assertion escape hatch from becoming a rubber stamp."""
    claim_id = claim.get("claim_id", "<unknown>")
    entries = _derived_entries(claim)
    if not entries:
        return []
    errors = []
    fix = "set field derived_assertions"
    claim_text = _text(claim.get("claim")).casefold()
    extract = _claim_evidence_text(claim).casefold()
    seen = set()
    for entry in entries:
        expression = _text(entry.get("expression"))
        derivation = _text(entry.get("derivation"))
        if not expression:
            errors.append(
                _f(
                    "ledger/derived",
                    f"{claim_id}: derived_assertions entry has no expression; "
                    "name the exact wording in claim that is derived.",
                    fix=fix,
                    remove=_drop(claim_id),
                )
            )
            continue
        folded = expression.casefold()
        if not _exact_expression_in_text(expression, claim_text):
            errors.append(
                _f(
                    "ledger/derived",
                    f"{claim_id}: derived assertion '{expression}' does not appear "
                    "in claim; the expression must be quoted from the claim text.",
                    fix=fix,
                    remove=_drop(claim_id),
                )
            )
        if extract and folded in extract:
            errors.append(
                _f(
                    "ledger/derived",
                    f"{claim_id}: derived assertion '{expression}' already appears "
                    "in extract_or_location; it is quoted evidence, not a "
                    "derivation. Remove the derived_assertions entry.",
                    fix=fix,
                    remove=_drop(claim_id),
                )
            )
        if folded in seen:
            errors.append(
                _f(
                    "ledger/derived",
                    f"{claim_id}: derived assertion '{expression}' is declared twice.",
                    fix=fix,
                    remove=_drop(claim_id),
                )
            )
        seen.add(folded)
        needed = _prose_minimum(derivation) if derivation else _prose_minimum(
            expression
        )
        if len(derivation) < needed:
            errors.append(
                _f(
                    "ledger/derived",
                    f"{claim_id}: derived assertion '{expression}' needs a "
                    f"derivation of at least {needed} characters stating how it "
                    f"was computed or inferred (threshold: {needed}; actual: "
                    f"{len(derivation)}).",
                    fix=fix,
                    remove=_drop(claim_id),
                )
            )
    if claim.get("kind") != "estimate" and len(entries) > 2:
        errors.append(
            _f(
                "ledger/derived",
                f"{claim_id}: {len(entries)} derived assertions on a "
                f"{claim.get('kind')} claim. Split the claim, or record the "
                "arithmetic as kind 'estimate' with assumptions.",
                fix=fix,
                remove=_drop(claim_id),
            )
        )
    return errors


def derived_assertion_errors(claim):
    return _as_legacy(_derived_findings(claim))


def _is_negated(text, index):
    """Report whether a status word is denied rather than asserted."""
    window = text[max(0, index - 32) : index].casefold()
    return bool(
        re.search(
            r"\b(?:not|no|never|nor|without|n't|isn't|aren't|wasn't|weren't|"
            r"cannot|hardly|fails? to|denies|denied)\b[^.;]*$",
            window,
        )
        # R17: scraped Chinese pages often punctuate with ASCII "." and ";".
        # Without them in the stop set a negation leaked across sentences and
        # denied an assertion two sentences later.
        or re.search(r"[不未沒没非][^。；.;]*$", window)
    )


def _has_affirmative_match(pattern, text):
    return any(
        not _is_negated(text, match.start())
        for match in re.finditer(pattern, text, re.IGNORECASE)
    )


_ASSERTION_CARRIER_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "for", "from", "had", "has", "have", "in", "is", "it", "of", "on",
    "or", "that", "the", "this", "to", "was", "were", "will", "with",
    "according", "advisory", "claim", "notes", "report", "reported",
    "reports", "says", "said", "states", "stated",
}
_ASSERTION_MEASURE_WORDS = {
    "percent", "percentage", "point", "points", "dollar", "dollars",
    "euro", "euros", "pound", "pounds", "yen", "yuan", "usd", "eur",
    "gbp", "jpy", "cny", "hundred", "thousand", "million", "billion",
    "trillion", "bn", "mn",
}

#: The Latin-script carrier branch above already drops English number and
#: measure words before comparing subjects; the CJK-bigram fallback needs the
#: same exclusion; otherwise a spelled-out Chinese figure ("百分之三十五") is
#: pure CJK and reads as carrier vocabulary in its own right, while the same
#: figure in digit form ("35%") contributes nothing to the fallback's
#: `[㐀-鿿]` scan. Two claim/evidence pairs that state the same
#: figure in different notation then compare a numeral-bigram carrier against
#: an unrelated preamble ("報告稱") and never overlap. Excluding every
#: character _scan_quantities treats as part of a Chinese number keeps the
#: fallback comparing actual subject words on both sides, matching how a
#: digit-form figure was already excluded for free.
_CJK_CARRIER_NOISE_CHARS = frozenset(
    _HAN_NUMERAL_CHARS
    + _CJK_ORDINAL_MARKER
    + _CJK_PERCENT_MARKER
    + _CJK_FRACTION_CONNECTOR
    + _CJK_CHENG_MARKER
    + _HAN_DECIMAL_MARKER_CHARS
)


def _assertion_match_is_affirmative(text, match):
    """Reject denied assertions and status words used only as proposal nouns."""
    if _is_negated(text, match.start()):
        return False
    sentence_start = max(
        text.rfind(".", 0, match.start()),
        text.rfind(";", 0, match.start()),
        text.rfind("。", 0, match.start()),
        text.rfind("；", 0, match.start()),
    ) + 1
    prefix = text[sentence_start : match.start()].casefold()
    if re.search(
        r"\b(?:rejects?|rejected|denies?|denied|disputes?|disputed)\s+"
        r"(?:the\s+)?(?:claims?|assertions?|reports?)\s+that\b"
        r"|\b(?:it\s+is\s+|is\s+)?(?:false|incorrect|untrue)\s+that\b",
        prefix,
    ):
        return False
    tail = text[match.end() : match.end() + 80].casefold()
    if re.search(
        r"\b(?:is|are|was|were)\s+"
        r"(?:false|incorrect|untrue|disputed|denied|rejected)\b",
        tail,
    ):
        return False
    return not (
        match.group(0).casefold() in {"patch", "fix", "approval", "recall"}
        and re.match(r"\s+(?:proposal|plan|request|candidate|idea)\b", tail)
        and re.search(r"\b(?:reject(?:ed|s)?|denied|withdrawn)\b", tail)
    )


def _assertion_sentence(text, match):
    """The sentence holding an assertion, with the assertion word removed."""
    start = max(
        text.rfind(".", 0, match.start()),
        text.rfind(";", 0, match.start()),
        text.rfind("。", 0, match.start()),
        text.rfind("；", 0, match.start()),
    ) + 1
    ends = [
        index
        for token in (".", ";", "。", "；")
        if (index := text.find(token, match.end())) >= 0
    ]
    end = min(ends) if ends else len(text)
    return text[start:match.start()] + " " + text[match.end():end]


#: R17: the shortest CJK run that identifies a carrier on its own.
_CJK_CARRIER_PHRASE_CHARS = 4


def _assertion_carrier_cjk(text, match):
    """The carrier's CJK characters, in order, numerals and noise removed."""
    return "".join(
        char
        for char in re.findall(r"[㐀-鿿]", _assertion_sentence(text, match))
        if char not in _CJK_CARRIER_NOISE_CHARS
    )


def _shares_cjk_phrase(claim_cjk, evidence_cjk):
    """R17: CJK carriers agree on a phrase, not on 75% of their bigrams.

    The bigram ratio below is calibrated for Latin sentences, which yield a
    handful of content words. A Chinese clause yields one bigram per character,
    so two sentences naming the same subject in different surrounding prose
    ("公告中必须增加中国主席" against "要求公告列名增加中国主席且置于英国首相之前")
    overlap far below 0.75 while plainly carrying the same assertion. A shared
    run of four characters is the phrase-level evidence that ratio was after.
    """
    size = _CJK_CARRIER_PHRASE_CHARS
    if len(claim_cjk) < size or len(evidence_cjk) < size:
        return False
    grams = {
        claim_cjk[index : index + size]
        for index in range(len(claim_cjk) - size + 1)
    }
    return any(
        evidence_cjk[index : index + size] in grams
        for index in range(len(evidence_cjk) - size + 1)
    )


def _assertion_carrier_tokens(text, match):
    """Extract the subject/carrier around an assertion occurrence."""
    def normalize_word(word):
        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    sentence = _assertion_sentence(text, match)
    words = {
        normalize_word(word)
        for word in re.findall(r"[a-z][a-z0-9'-]*", sentence.casefold())
        if word not in _ASSERTION_CARRIER_STOPWORDS and len(word) > 1
        and word not in _NUMBER_WORDS
        and word not in _ASSERTION_MEASURE_WORDS
    }
    if words:
        return words
    cjk = _assertion_carrier_cjk(text, match)
    return {
        cjk[index : index + 2]
        for index in range(max(0, len(cjk) - 1))
    }


def _evidence_carries_assertion(
    claim_text, claim_matches, evidence_text, evidence_pattern
):
    """Bind an assertion to affirmative evidence about the same carrier."""
    def anaphoric_quantity_binding(claim_match, evidence_match):
        claim_prefix = claim_text[
            max(0, claim_match.start() - 80) : claim_match.start()
        ]
        if re.search(
            r"\b(?:it|them|they|those|these)\b", claim_prefix, re.IGNORECASE
        ) is None:
            return False
        evidence_prefix = evidence_text[
            max(0, evidence_match.start() - 80) : evidence_match.start()
        ]
        return bool(
            quantitative_evidence(claim_prefix).intersection(
                quantitative_evidence(evidence_prefix)
            )
        )

    claim_carriers = [
        _assertion_carrier_tokens(claim_text, match)
        for match in claim_matches
    ]
    claim_phrases = [
        _assertion_carrier_cjk(claim_text, match) for match in claim_matches
    ]
    for evidence_match in re.finditer(
        evidence_pattern, evidence_text, re.IGNORECASE
    ):
        if not _assertion_match_is_affirmative(
            evidence_text, evidence_match
        ):
            continue
        evidence_carrier = _assertion_carrier_tokens(
            evidence_text, evidence_match
        )
        evidence_phrase = _assertion_carrier_cjk(evidence_text, evidence_match)
        if any(
            (
                not claim_carrier
                or not evidence_carrier
                or (
                    len(claim_carrier.intersection(evidence_carrier))
                    / min(len(claim_carrier), len(evidence_carrier))
                    >= 0.75
                )
                or _shares_cjk_phrase(claim_phrase, evidence_phrase)
                or anaphoric_quantity_binding(
                    claim_match, evidence_match
                )
            )
            for claim_match, claim_carrier, claim_phrase in zip(
                claim_matches, claim_carriers, claim_phrases, strict=True
            )
        ):
            return True
    return False


def _evidence_coverage_findings(
    claim, dated_fields=(), inherited_evidence="", source_text=""
):
    """Require claim assertions to be covered by the recorded evidence.

    `dated_fields` carries the dates the ledger already records in its own
    fields (as_of, verified_at, source access and publication). A date in the
    claim that matches one of them is dated by the ledger, not by the extract.

    `inherited_evidence` carries the extracts of the claims this one rests on.
    An analysis claim quotes no source of its own but still may not introduce a
    figure or a status that appears nowhere in the evidence beneath it;
    otherwise relabelling a claim `analysis` would launder any assertion.
    """
    kind = claim.get("kind")
    if kind not in {"fact", "reported_claim", "estimate", "analysis"}:
        return []
    claim_text = _text(claim.get("claim"))
    extract = _claim_evidence_text(claim)
    claim_id = claim.get("claim_id", "<unknown>")
    errors = []
    if not claim_text:
        return errors
    if not extract and kind != "analysis":
        # An absent extract used to exempt the claim from every check below,
        # which made a blank field the cheapest way to assert anything.
        return [
            _f(
                "ledger/extract-length",
                f"{claim_id}: extract_or_location is empty, so nothing in the claim "
                "is evidenced. Quote the source wording or its precise location.",
                fix="set field extract_or_location",
                remove=_drop(claim_id),
            )
        ]
    extract = " ".join(part for part in (extract, _text(inherited_evidence)) if part)
    if not extract:
        return [
            _f(
                "ledger/extract-length",
                f"{claim_id}: analysis rests on no recorded evidence. Quote its "
                "reasoning basis, or link the claims it is derived from.",
                fix="set field extract_or_location",
                remove=_drop(claim_id),
            )
        ]
    assumptions = claim.get("assumptions")
    assumption_text = (
        " ".join(str(item) for item in assumptions)
        if isinstance(assumptions, list)
        else ""
    )
    evidence_forms = quantitative_evidence(extract, assumption_text)
    for value in dated_fields:
        if isinstance(value, str) and _as_date(value):
            evidence_forms.add(f"d:{value}")
    derived_entries = [
        entry
        for entry in _derived_entries(claim)
        if _exact_expression_in_text(entry.get("expression"), claim_text)
    ]
    derived_quantities = []
    for entry in derived_entries:
        expression = _text(entry.get("expression"))
        forms = set()
        for _, expression_forms in quantitative_obligations(expression):
            forms.update(expression_forms)
        derived_quantities.append((expression.casefold(), forms))
    used_expressions = set()
    covering_forms = None
    for display, claim_forms in quantitative_obligations(claim_text):
        matching_expressions = [
            expression
            for expression, forms in derived_quantities
            if forms and _quantity_is_covered(claim_forms, forms)
        ]
        if matching_expressions:
            used_expressions.update(matching_expressions)
            continue
        # R29: a quantity spelled with Han numerals raises no finding at all.
        if _is_cjk_numeral_token(display):
            continue
        if covering_forms is None:
            # R29: the cited source's cached page, title and published date
            # carry a figure as legitimately as the pasted extract does.
            covering_forms = evidence_forms | quantitative_evidence(source_text)
        if _quantity_is_covered(claim_forms, covering_forms):
            continue
        if _year_documented_coverage(claim_forms, covering_forms, source_text):
            continue
        if _year_number_coverage(claim_forms, covering_forms):
            continue
        cited = []
        seen = set()
        for entry in claim.get("source_evidence") or []:
            if isinstance(entry, dict):
                sid = entry.get("source_id")
                if sid and sid not in seen:
                    seen.add(sid)
                    cited.append(sid)
        linked = claim.get("source_ids")
        if isinstance(linked, list):
            for sid in linked:
                if sid and sid not in seen:
                    seen.add(sid)
                    cited.append(sid)
        find_id = cited[0] if cited else None
        named = " or ".join(cited) if cited else "the cited sources"
        fix = (
            f"alx find {find_id} {display} — paste that window into "
            "extract_or_location and alx claim add, or reword the claim"
            if find_id
            else (
                "set field extract_or_location in claims/<file>, then "
                "alx claim add claims/<file>, or reword the claim"
            )
        )
        errors.append(
            _f(
                "ledger/quantity",
                f"{claim_id}: '{display}' is in the claim but not in "
                f"{named} (extracts or cached page). "
                f"Fix: {fix}",
                ids=_ids_in(f"{claim_id} {find_id or ''}"),
                fix=fix,
            )
        )
    folded_extract = extract.casefold()
    folded_claim = claim_text.casefold()
    for label, claim_pattern, evidence_pattern in DIRECTION_ASSERTIONS:
        asserted = [
            match
            for match in re.finditer(claim_pattern, folded_claim, re.IGNORECASE)
            if not _is_negated(folded_claim, match.start())
            and (label != "below" or _trigger_has_carrier(folded_claim, match))
        ]
        if not asserted or (
            _has_affirmative_match(evidence_pattern, folded_extract)
            if kind == "analysis"
            else _evidence_carries_assertion(
                folded_claim, asserted, folded_extract, evidence_pattern
            )
        ):
            continue
        matching_expressions = [
            _text(entry.get("expression")).casefold()
            for entry in derived_entries
            if re.search(
                claim_pattern,
                _text(entry.get("expression")),
                re.IGNORECASE,
            )
        ]
        if matching_expressions:
            used_expressions.update(matching_expressions)
            continue
        errors.append(
            _f(
                "ledger/direction",
                f"{claim_id}: claim asserts the {label!r} direction but the "
                "recorded evidence does not.",
                fix="set field claim",
                remove=_drop(claim_id),
            )
        )
    for label, claim_pattern, evidence_pattern in STATUS_ASSERTIONS:
        asserted = [
            match
            for match in re.finditer(claim_pattern, folded_claim, re.IGNORECASE)
            if not _is_negated(folded_claim, match.start())
            and (label != "settled" or _trigger_has_carrier(folded_claim, match))
        ]
        if not asserted:
            # A denied status ("not open source") is not an appended status
            # assertion; the negative-existence rule governs those.
            continue
        if _evidence_carries_assertion(
            folded_claim, asserted, folded_extract, evidence_pattern
        ):
            continue
        matching_expressions = [
            _text(entry.get("expression")).casefold()
            for entry in derived_entries
            if re.search(
                claim_pattern,
                _text(entry.get("expression")),
                re.IGNORECASE,
            )
        ]
        if matching_expressions:
            used_expressions.update(matching_expressions)
            continue
        errors.append(
            _f(
                "ledger/status",
                f"{claim_id}: claim asserts '{label}' but extract_or_location "
                "records no evidence of it. Quote the source wording that "
                "establishes the status, or declare it in derived_assertions.",
                fix="set field extract_or_location",
                remove=_drop(claim_id),
            )
        )
    for entry in derived_entries:
        expression = _text(entry.get("expression"))
        folded = expression.casefold()
        if not expression or folded in used_expressions:
            continue
        errors.append(
            _f(
                "ledger/derived",
                f"{claim_id}: derived assertion '{expression}' excuses nothing; "
                "the escape hatch is only for quantities or status assertions "
                "that the extract does not carry.",
                severity="warn",
                fix="set field derived_assertions",
            )
        )
    return errors


def evidence_coverage_errors(claim, dated_fields=(), inherited_evidence=""):
    return _as_legacy(
        _evidence_coverage_findings(
            claim,
            dated_fields=dated_fields,
            inherited_evidence=inherited_evidence,
        )
    )


def _as_date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _absence_errors(claim, report_day):
    """Require a bounded search record behind every negative-existence claim."""
    claim_id = claim.get("claim_id", "<unknown>")
    claim_text = _text(claim.get("claim"))
    if not claim_text or not NEGATIVE_EXISTENCE_PATTERN.search(claim_text):
        return []
    record = claim.get("evidence_of_absence")
    if not isinstance(record, dict):
        return [
            _f(
                "ledger/reference",
                f"{claim_id}: claim asserts that something does not exist or was "
                "not found but records no evidence_of_absence. Record the "
                "queries, the expected locations, and searched_at.",
                severity="warn",
                ids=[claim_id],
                fix=_claim_set_fix("evidence_of_absence"),
            )
        ]
    errors = []
    for field in ("queries", "expected_locations"):
        values = record.get(field)
        if not isinstance(values, list) or not [
            item for item in values if _text(item)
        ]:
            errors.append(
                f"{claim_id}: evidence_of_absence.{field} is empty; a bounded "
                "search result needs the searches run and the places checked."
            )
    searched_day = _as_date(record.get("searched_at"))
    if searched_day is None:
        errors.append(
            f"{claim_id}: evidence_of_absence.searched_at is missing or not a "
            "date."
        )
    elif report_day:
        if searched_day > report_day:
            errors.append(
                f"{claim_id}: evidence_of_absence.searched_at is after the "
                "report date."
            )
        elif (report_day - searched_day).days > FRESHNESS_WINDOW_DAYS:
            errors.append(
                f"{claim_id}: the absence search ran "
                f"{(report_day - searched_day).days} days before the report "
                f"date. Re-run it inside the {FRESHNESS_WINDOW_DAYS}-day "
                "freshness window; absence decays faster than presence."
            )
    return errors


def _verification_errors(
    claim, claim_day, report_day, direct_foundations, sources_by_id
):
    """Keep verified_at meaning re-read, not re-dated."""
    claim_id = claim.get("claim_id", "<unknown>")
    raw = claim.get("verified_at")
    verified_day = _as_date(raw)
    errors = []
    if raw is not None and verified_day is None:
        errors.append(f"{claim_id}: verified_at is not a date.")
        return errors
    if verified_day is None:
        if claim.get("time_sensitive") is True:
            errors.append(
                f"{claim_id}: a time-sensitive claim needs verified_at, the "
                "date its extract was last re-read against the live source. "
                "Re-dating as_of is not re-verification."
            )
        return errors
    if report_day and verified_day > report_day:
        errors.append(f"{claim_id}: verified_at is after the report date.")
    # R24: verified_at is the UTC fetch date and as_of is often the local one,
    # so a single day of drift is a timezone, not a claim about the future.
    if claim_day and (claim_day - verified_day).days > AS_OF_DRIFT_DAYS:
        errors.append(
            _f(
                "ledger/reference",
                f"{claim_id}: as_of {claim_day.isoformat()} is "
                f"{(claim_day - verified_day).days} days after verified_at "
                f"{verified_day.isoformat()} (threshold {AS_OF_DRIFT_DAYS} "
                "day); a claim cannot be verified before the state it describes.",
                severity="warn",
                ids=[claim_id],
                fix=_claim_set_fix("as_of"),
                remove=_drop(claim_id),
            )
        )
    accessed_days = [
        _as_date(sources_by_id[source_id].get("accessed"))
        for source_id in direct_foundations
        if source_id in sources_by_id
    ]
    accessed_days = [day for day in accessed_days if day]
    if accessed_days and verified_day > max(accessed_days):
        errors.append(
            f"{claim_id}: verified_at ({verified_day.isoformat()}) is later "
            f"than the most recent source access ({max(accessed_days).isoformat()}). "
            "Re-access the source, or correct the date."
        )
    if (
        claim.get("time_sensitive") is True
        and report_day
        and (report_day - verified_day).days > FRESHNESS_WINDOW_DAYS
    ):
        errors.append(
            f"{claim_id}: a time-sensitive claim was last verified "
            f"{(report_day - verified_day).days} days before the report date."
        )
    return errors


def _source_family_index(sources_by_id):
    """Merge sources into real independence families.

    A declared family can only ever be coarser than the evidence: sources
    sharing a registrable domain or a publisher are one family whatever they
    call themselves, and a shared declared family merges different domains.
    """
    parent = {source_id: source_id for source_id in sources_by_id}

    def find(source_id):
        while parent[source_id] != source_id:
            parent[source_id] = parent[parent[source_id]]
            source_id = parent[source_id]
        return source_id

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)

    groups = {}
    for source_id, source in sources_by_id.items():
        keys = set()
        domain = _registrable_domain(source.get("url"))
        if domain:
            keys.add(("domain", domain))
        declared = _normalized_family(source.get("source_family"))
        if declared:
            keys.add(("family", declared))
        publisher = _normalized_family(source.get("publisher"))
        if publisher:
            keys.add(("publisher", publisher))
        for key in keys:
            if key in groups:
                union(groups[key], source_id)
            else:
                groups[key] = source_id
    return {source_id: find(source_id) for source_id in sources_by_id}


def _source_family_errors(sources_by_id):
    """Tie source_family and provenance to the publisher and the URL host."""
    errors = []
    independent = {"primary_independent", "secondary_independent"}
    interested = {"primary_interested", "secondary_dependent", "unverified"}
    hosts = {}
    for source_id, source in sorted(sources_by_id.items()):
        try:
            host = urlsplit(str(source.get("url") or "")).hostname or ""
        except ValueError:
            host = ""
        if host:
            hosts.setdefault(host.casefold(), []).append(source_id)
    # A descriptive label like 'anthropic-docs' is more useful than 'claude.com'
    # and is never itself an error: _source_family_index already merges by
    # registrable domain, so a label cannot manufacture a second family. What
    # does need flagging is one domain wearing several labels, because that is
    # the shape of deliberate family inflation and it misleads every human
    # reader of the ledger even though the counting defeats it.
    by_domain = {}
    for source_id, source in sorted(sources_by_id.items()):
        domain = _registrable_domain(source.get("url"))
        declared = _normalized_family(source.get("source_family"))
        if domain and declared:
            by_domain.setdefault(domain, {}).setdefault(declared, []).append(source_id)
    for domain, labels in sorted(by_domain.items()):
        if len(labels) < 2:
            continue
        unjustified = sorted(
            source_id
            for ids in labels.values()
            for source_id in ids
            if len(_text(sources_by_id[source_id].get("family_justification")))
            < _prose_minimum(sources_by_id[source_id].get("family_justification"))
        )
        if unjustified:
            sid = unjustified[0]
            errors.append(
                _f(
                    "ledger/source-family",
                    f"Domain {domain} is split across {len(labels)} source families "
                    f"({', '.join(sorted(labels))}): {', '.join(unjustified)}. "
                    "Use one family per domain, or record a family_justification "
                    f"of at least {_CJK_PROSE_MIN} characters (CJK) / "
                    f"{_LATIN_PROSE_MIN} characters explaining the genuine "
                    "independence.",
                    severity="warn",
                    ids=unjustified,
                    fix=_family_justification_fix(sid, parties="one party"),
                )
            )
    for host, source_ids in sorted(hosts.items()):
        if len(source_ids) < 2:
            continue
        classes = set()
        for source_id in source_ids:
            provenance = sources_by_id[source_id].get("provenance")
            if provenance in independent:
                classes.add("independent")
            elif provenance in interested:
                classes.add("interested")
            elif provenance:
                classes.add(str(provenance))
        unjustified = [
            source_id
            for source_id in source_ids
            if len(_text(sources_by_id[source_id].get("family_justification")))
            < _prose_minimum(
                sources_by_id[source_id].get("family_justification")
            )
        ]
        provenances = ", ".join(
            f"{source_id}={sources_by_id[source_id].get('provenance')}"
            for source_id in source_ids
        )
        if len(classes) > 1 and unjustified:
            sid = unjustified[0]
            errors.append(
                _f(
                    "ledger/host-conflict",
                    f"Sources on host {host} declare different independence "
                    f"classes ({', '.join(sorted(classes))}) without a "
                    f"family_justification ({', '.join(unjustified)}): "
                    f"{provenances}. Pages on one host are one interested "
                    "party unless the difference is justified.",
                    severity="warn",
                    ids=source_ids,
                    fix=_family_justification_fix(sid, parties="two parties"),
                    remove="",
                )
            )
    return errors


def _supports_cycles(claims_by_id):
    """Return every cycle in the supports graph; supports must point down."""
    cycles = set()
    state = {}

    def walk(claim_id, path):
        state[claim_id] = 1
        claim = claims_by_id.get(claim_id, {})
        supports = claim.get("supports", [])
        if isinstance(supports, list):
            for related_id in supports:
                if related_id not in claims_by_id:
                    continue
                if state.get(related_id) == 1:
                    start = path.index(related_id)
                    cycles.add(tuple(path[start:] + [related_id]))
                elif state.get(related_id) is None:
                    walk(related_id, path + [related_id])
        state[claim_id] = 2

    for claim_id in claims_by_id:
        if state.get(claim_id) is None:
            walk(claim_id, [claim_id])
    return sorted(cycles)


def coverage_claim_ids(item):
    if not isinstance(item, dict):
        return []
    for key in ("claim_ids", "claims"):
        value = item.get(key)
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return value
    return []


def _reference_findings(data, cache_dir=None):
    """Check ID uniqueness and links that JSON Schema cannot express."""
    if not isinstance(data, dict):
        return []
    errors = []
    sources = data.get("sources", [])
    claims = data.get("claims", [])
    if not isinstance(sources, list) or not isinstance(claims, list):
        return []
    coverage = data.get("coverage", [])
    if not isinstance(coverage, list):
        coverage = []
    source_ids = [
        source.get("source_id")
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    ]
    claim_ids = [
        claim.get("claim_id")
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    ]
    source_set = set(source_ids)
    claim_set = set(claim_ids)
    sources_by_id = {
        source.get("source_id"): source
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }
    claims_by_id = {
        claim.get("claim_id"): claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    }
    people = data.get("people", [])
    people = people if isinstance(people, list) else []
    person_ids = [
        person.get("person_id")
        for person in people
        if isinstance(person, dict) and person.get("person_id")
    ]
    people_by_id = {
        person.get("person_id"): person
        for person in people
        if isinstance(person, dict) and person.get("person_id")
    }
    independent_provenance = {
        "primary_independent",
        "secondary_independent",
    }
    interested_provenance = {
        "primary_interested",
        "secondary_dependent",
        "unverified",
    }

    excluded_claims = data.get("excluded_claims")
    excluded_claims = excluded_claims if isinstance(excluded_claims, list) else []
    excluded_ids = {
        item.get("claim_id")
        for item in excluded_claims
        if isinstance(item, dict) and item.get("claim_id")
    }

    if data.get("schema_version") in {3, 4} and sources_by_id and not any(
        source.get("provenance") in independent_provenance
        for source in sources_by_id.values()
    ):
        errors.append(
            _f(
                "ledger/portfolio",
                "Evidence portfolio has no independent source; unverified "
                "counts as interested. Record affected coverage as a gap "
                "rather than supported.\n"
                "  --provenance: primary_independent, primary_interested, "
                "secondary_independent, secondary_dependent, unverified\n"
                "  --type: accountable_record, peer_reviewed, preprint, "
                "official_documentation, dataset_or_test, reported_interview, "
                "news_report, opinion_or_forecast, marketing, anecdote\n"
                "  --role: subject_official, counterparty_official, "
                "independent_analysis, empirical_data, affected_stakeholder, "
                "expert_interpretation, historical_record",
                # R27: unclassified sourcing is a judgment about the portfolio,
                # not a fabrication; triangulation still computes from whatever
                # classification is set.
                severity="warn",
                fix=PROVENANCE_INDEPENDENT_FIX.format(sid="S1"),
            )
        )

    errors.extend(f"Duplicate source ID: {item}" for item in _duplicates(source_ids))
    errors.extend(f"Duplicate claim ID: {item}" for item in _duplicates(claim_ids))
    errors.extend(f"Duplicate person ID: {item}" for item in _duplicates(person_ids))
    source_urls = [
        _normalized_url(source.get("url"))
        for source in sources
        if isinstance(source, dict) and source.get("url")
    ]
    errors.extend(
        f"Duplicate source URL: {item}" for item in _duplicates(source_urls)
    )

    for item in coverage:
        if not isinstance(item, dict):
            continue
        area = item.get("area", "<unknown>")
        coverage_claims = coverage_claim_ids(item)
        for claim_id in coverage_claims:
            if claim_id not in claim_set:
                errors.append(
                    _f(
                        "ledger/reference",
                        f"Coverage {area} references unknown claim {claim_id}.",
                        severity="warn",
                        ids=[claim_id],
                        fix=f"remove {claim_id} from coverage claim_ids",
                    )
                )
        if (
            item.get("priority") == "high"
            and item.get("status") in {"unstarted", "in_progress"}
        ):
            errors.append(f"High-priority coverage {area} is unresolved.")
        if item.get("status") == "gap" and not str(
            item.get("gap_impact") or ""
        ).strip():
            errors.append(f"Coverage {area} is a gap but has no gap impact.")
        if item.get("status") == "gap" and coverage_claims:
            errors.append(f"Coverage {area} is a gap but still references claims.")
        has_claim_list = "claim_ids" in item or "claims" in item
        if item.get("status") == "disputed" and has_claim_list and not any(
            claims_by_id.get(claim_id, {}).get("status") == "disputed"
            for claim_id in coverage_claims
        ):
            errors.append(
                _f(
                    "ledger/coverage",
                    f"Coverage {area} is disputed but references no disputed claim.",
                    severity="warn",
                    fix=(
                        "set coverage[i].claim_ids to disputed claim ids in a "
                        "patch file, then alx ledger merge <patch>"
                    ),
                )
            )
        if item.get("status") == "supported" and has_claim_list and not any(
            claims_by_id.get(claim_id, {}).get("status") == "supported"
            for claim_id in coverage_claims
        ):
            errors.append(
                _f(
                    "ledger/coverage",
                    f"Coverage {area} is supported but references no supported claim.",
                    severity="warn",
                    fix=COVERAGE_PATCH_FIX,
                )
            )

    report_date_value = data.get("report_date")
    try:
        report_day = (
            date.fromisoformat(report_date_value)
            if isinstance(report_date_value, str)
            else None
        )
    except ValueError:
        report_day = None
    for source_id, source in sources_by_id.items():
        try:
            published = (
                date.fromisoformat(source["published"])
                if isinstance(source.get("published"), str)
                else None
            )
            accessed = (
                date.fromisoformat(source["accessed"])
                if isinstance(source.get("accessed"), str)
                else None
            )
        except ValueError:
            continue
        if published and report_day and published > report_day:
            errors.append(f"{source_id} is published after the report date.")
        if accessed and report_day and accessed > report_day:
            errors.append(f"{source_id} is accessed after the report date.")
        if published and accessed and published > accessed:
            errors.append(f"{source_id} is published after it was accessed.")
        url = _text(source.get("url"))
        if url and not url.lower().startswith("https://") and not source.get(
            "plain_http"
        ):
            errors.append(
                _f(
                    "ledger/https",
                    f"{source_id}: source.url must be https "
                    f"(threshold: https; actual: {url}).",
                    severity="warn",
                    ids=[source_id],
                    fix=(
                        f"alx source set {source_id} --url "
                        f"{re.sub(r'(?i)^http://', 'https://', url)}"
                    ),
                )
            )

    def direct_source_ids(claim_id):
        claim = claims_by_id.get(claim_id, {})
        linked = claim.get("source_ids")
        if linked is None:
            evidence = claim.get("source_evidence")
            linked = [
                entry.get("source_id")
                for entry in evidence
                if isinstance(entry, dict) and entry.get("source_id")
            ] if isinstance(evidence, list) else []
        linked = set(linked) if isinstance(linked, list) else set()
        return {source_id for source_id in linked if source_id in sources_by_id}

    def foundation_source_ids(claim_id, levels=1):
        """Direct sources plus at most `levels` declared support levels.

        `supports` points strictly downward, so a foundation is never counted
        through an unbounded chain: one declared level is the most a claim may
        borrow before it must cite the evidence itself.
        """
        foundations = direct_source_ids(claim_id)
        if levels <= 0:
            return foundations
        supports = claims_by_id.get(claim_id, {}).get("supports", [])
        if isinstance(supports, list):
            for related_id in supports:
                if related_id in claims_by_id and related_id != claim_id:
                    foundations.update(
                        foundation_source_ids(related_id, levels - 1)
                    )
        return foundations

    family_of = _source_family_index(sources_by_id)
    errors.extend(_source_family_errors(sources_by_id))

    # The schema floor is 20 so CJK notes fit; the script-aware floor keeps a
    # Latin note substantive (40) without punishing CJK prose (20).
    for source_id, source in sorted(sources_by_id.items()):
        note = _text(source.get("accountability_note"))
        threshold = _prose_minimum(note)
        if note and len(note) < threshold:
            errors.append(
                _f(
                    "ledger/provenance",
                    f"{source_id}: accountability_note must say what makes the "
                    "source accountable (threshold "
                    f"{threshold}, actual {len(note)}).",
                    severity="warn",
                    ids=[source_id],
                    fix=(
                        f"alx source set {source_id} "
                        "--accountability-note accountability-note.txt"
                    ),
                )
            )

    for item in coverage:
        if not isinstance(item, dict) or item.get("status") != "supported":
            continue
        coverage_claims = coverage_claim_ids(item)
        linked_sources = {
            source_id
            for claim_id in coverage_claims
            for source_id in foundation_source_ids(claim_id)
            if source_id in sources_by_id
        }
        if linked_sources and all(
            sources_by_id[source_id].get("provenance") in interested_provenance
            for source_id in linked_sources
        ):
            errors.append(
                _f(
                    "ledger/provenance",
                    f"Supported coverage {item.get('area', '<unknown>')} relies "
                    "only on interested sources; mark it as a gap or add "
                    "independent evidence.",
                    severity="warn",
                    fix=PROVENANCE_INDEPENDENT_FIX.format(
                        sid=sorted(linked_sources)[0]
                    ),
                )
            )

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        try:
            claim_day = (
                date.fromisoformat(claim["as_of"])
                if isinstance(claim.get("as_of"), str)
                else None
            )
        except ValueError:
            claim_day = None
        if claim_day and report_day and claim_day > report_day:
            errors.append(f"{claim_id} is dated after the report date.")
        source_evidence = claim.get("source_evidence")
        source_evidence = (
            source_evidence if isinstance(source_evidence, list) else []
        )
        evidence_ids = [
            entry.get("source_id")
            for entry in source_evidence
            if isinstance(entry, dict) and entry.get("source_id")
        ]
        raw_source_ids = claim.get("source_ids")
        if raw_source_ids is None:
            source_links = list(dict.fromkeys(evidence_ids))
            errors.append(
                _f(
                    "ledger/source-ids",
                    f"{claim_id}: source_ids missing; derived {source_links} "
                    f"from source_evidence (threshold: present; actual: absent). "
                    "Fix: `alx check --fix`.",
                    severity="warn",
                    ids=_ids_in(claim_id),
                    fix="alx check --fix",
                )
            )
        elif not isinstance(raw_source_ids, list):
            source_links = []
        else:
            source_links = list(raw_source_ids)
        for source_id in source_links:
            if source_id not in source_set:
                # R28: the one hard cross-reference — a claim may cite only a
                # source the ledger actually fetched.
                errors.append(
                    _f(
                        "ledger/reference",
                        f"{claim_id} references unknown source {source_id}.",
                        ids=[claim_id, source_id],
                        fix=f"remove {source_id} from source_ids in claims/<file>, then alx claim add claims/<file>",
                        remove=_drop(claim_id),
                    )
                )
        # R22: two passages from one page are legitimate evidence; source_ids
        # derivation dedupes, and every entry is probed on its own.
        for source_id in evidence_ids:
            if source_id not in source_links:
                errors.append(
                    f"{claim_id}: source_evidence references {source_id}, "
                    "which is not a direct source for the claim."
                )
        extras = [
            source_id
            for source_id in source_links
            if source_id not in evidence_ids
        ]
        if extras:
            errors.append(
                _f(
                    "ledger/source-ids",
                    f"{claim_id}: extra source_ids {extras} not in "
                    f"source_evidence (threshold: 0 extras; actual: {len(extras)}). "
                    "Fix: `alx check --fix`.",
                    severity="warn",
                    ids=_ids_in(claim_id),
                    fix="alx check --fix",
                    remove=_drop(claim_id),
                )
            )
        person_links = claim.get("person_ids", [])
        person_links = person_links if isinstance(person_links, list) else []
        # R25: naming a registered person is a silent mechanical repair (R15),
        # and an unregistered id is a bookkeeping warn. Nothing else about a
        # person blocks a claim.
        auto_linked = [
            person_id
            for person_id in derive_person_ids(claim, people_by_id.values())
            if person_id not in person_links
        ]
        person_links = person_links + auto_linked
        for person_id in person_links:
            if person_id not in people_by_id:
                errors.append(
                    _f(
                        "ledger/person",
                        f"{claim_id}: person_ids {person_id} not in "
                        "ledger.people; run alx ledger merge people or drop "
                        "the id",
                        severity="warn",
                        ids=[claim_id, person_id],
                        fix=(
                            "set people in a patch file, then alx ledger "
                            "merge <patch>"
                        ),
                    )
                )
        for relation in ("supports", "contradicts"):
            related_claims = claim.get(relation, [])
            if not isinstance(related_claims, list):
                continue
            for related_id in related_claims:
                if related_id == claim_id:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"{claim_id} has a circular {relation} reference.",
                            severity="warn",
                            ids=[claim_id],
                            fix=f"remove {related_id} from {relation} in claims/<file>, then alx claim add claims/<file>",
                        )
                    )
                if related_id in excluded_ids:
                    errors.append(
                        _f(
                            "ledger/excluded-supports",
                            f"{claim_id}: surviving {relation} naming excluded "
                            f"claim {related_id}. Fix: set field {relation}. "
                            f"Remove: `{_drop(claim_id)}`.",
                            severity="warn",
                            ids=[claim_id, related_id],
                            fix=f"set field {relation}",
                            remove=_drop(claim_id),
                        )
                    )
                elif related_id not in claim_set:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"{claim_id} references unknown claim {related_id}.",
                            severity="warn",
                            ids=[claim_id, related_id],
                            fix=f"remove {related_id} from {relation} in claims/<file>, then alx claim add claims/<file>",
                        )
                    )
                elif relation == "contradicts":
                    other = claims_by_id.get(related_id, {})
                    reverse = other.get("contradicts", [])
                    if not isinstance(reverse, list) or claim_id not in reverse:
                        errors.append(
                            f"{claim_id} contradicts {related_id}, but the "
                            "relationship is not reciprocal."
                        )
        if claim.get("status") == "disputed":
            if not str(claim.get("resolution") or "").strip():
                errors.append(
                    _f(
                        "ledger/coverage",
                        f"{claim_id} is disputed but has no resolution.",
                        severity="warn",
                        ids=[claim_id],
                        fix="set field resolution",
                    )
                )
            if not claim.get("contradicts"):
                errors.append(
                    _f(
                        "ledger/coverage",
                        f"{claim_id} is disputed but has no contradicting claim.",
                        severity="warn",
                        ids=[claim_id],
                        fix="set field contradicts",
                    )
                )

        foundations = foundation_source_ids(claim_id)
        direct_foundations = direct_source_ids(claim_id)
        errors.extend(_derived_findings(claim))
        ledger_dates = [claim.get("as_of"), claim.get("verified_at")]
        for source_id in sorted(direct_foundations):
            source = sources_by_id[source_id]
            ledger_dates.extend([source.get("accessed"), source.get("published")])
        # An analysis inherits the evidence of the claims it rests on, so a
        # figure it carries must appear somewhere beneath it.
        inherited = ""
        if claim.get("kind") == "analysis":
            inherited = " ".join(
                _claim_evidence_text(claims_by_id[related_id])
                for related_id in claim.get("supports") or []
                if related_id in claims_by_id
            )
        errors.extend(
            _evidence_coverage_findings(
                claim, ledger_dates, inherited, source_year_text(claim, data, cache_dir)
            )
        )
        errors.extend(
            _absence_errors(claim, report_day)
        )
        errors.extend(
            _verification_errors(claim, claim_day, report_day, direct_foundations, sources_by_id)
        )
        if claim.get("kind") == "estimate":
            assumptions = claim.get("assumptions")
            if not isinstance(assumptions, list) or not [
                item for item in assumptions if _text(item)
            ]:
                errors.append(
                    _f(
                        "ledger/reference",
                        f"{claim_id}: an estimate must record its assumptions; "
                        "state the inputs and the arithmetic that produced it.",
                        severity="warn",
                        ids=[claim_id],
                        fix=_claim_set_fix("assumptions"),
                    )
                )
        if claim.get("kind") == "analysis" and not _text(claim.get("reasoning")):
            errors.append(
                _f(
                    "ledger/reference",
                    f"{claim_id}: an analysis must record its reasoning; "
                    "state the inference that produced it.",
                    severity="warn",
                    ids=[claim_id],
                    fix=_claim_input_remedy("reasoning"),
                )
            )
        if claim.get("time_sensitive") is True:
            if claim_day is None:
                errors.append(
                    f"{claim_id}: time-sensitive claim requires a non-null as_of date."
                )
            elif report_day and (
                report_day - claim_day
            ).days > FRESHNESS_WINDOW_DAYS:
                errors.append(
                    _f(
                        "ledger/freshness",
                        f"{claim_id}: time-sensitive claim is dated "
                        f"{(report_day - claim_day).days} days before the report date.",
                        severity="warn",
                        ids=[claim_id],
                        fix="set field as_of",
                        remove=_drop(claim_id),
                    )
                )
            for source_id in sorted(foundations):
                source = sources_by_id[source_id]
                undated_reason = _text(source.get("undated_reason"))
                if not source.get("published") and not undated_reason:
                    errors.append(
                        f"{source_id}: source for time-sensitive {claim_id} "
                        "has no publication date or undated_reason."
                    )
                    continue
                accessed_day = _as_date(source.get("accessed"))
                if report_day and accessed_day is None:
                    errors.append(
                        f"{source_id}: source for time-sensitive {claim_id} "
                        "has no usable accessed date; a stale reading cannot "
                        "support a current claim."
                    )
                elif (
                    report_day
                    and accessed_day
                    and (report_day - accessed_day).days > FRESHNESS_WINDOW_DAYS
                ):
                    errors.append(
                        f"{source_id}: source for time-sensitive {claim_id} "
                        f"was last accessed {(report_day - accessed_day).days} "
                        "days before the report date; re-read it inside the "
                        f"{FRESHNESS_WINDOW_DAYS}-day freshness window."
                    )
                published_day = _as_date(source.get("published"))
                stale_publication = (
                    published_day is not None
                    and report_day is not None
                    and (report_day - published_day).days > FRESHNESS_WINDOW_DAYS
                )
                if (
                    published_day is None or stale_publication
                ) and not CONTINUOUS_UPDATE_PATTERN.search(undated_reason):
                    errors.append(
                        _f(
                            "ledger/undated-reason",
                            f"{source_id}: source for time-sensitive {claim_id} is "
                            "not published inside the freshness window and its "
                            "undated_reason does not state that the page is "
                            "continuously updated. Accepted phrasings, for example: "
                            "'continuously updated', 'updated continuously', "
                            "'living page', '持续更新', '持續更新'.",
                            severity="warn",
                            ids=[source_id, claim_id],
                            fix=(
                                "write why the page is continuously updated into "
                                f"undated-reason.txt, then alx source set {source_id} "
                                "--undated-reason undated-reason.txt"
                            ),
                            remove=_drop(claim_id),
                        )
                    )
        if (
            claim.get("confidence") == "high"
            and claim.get("status") == "inference"
            and foundations
            and not any(
                sources_by_id[source_id].get("provenance")
                in independent_provenance
                for source_id in foundations
            )
        ):
            errors.append(
                f"{claim_id}: high-confidence inference requires an "
                "independent source foundation."
            )

        if (
            claim.get("kind") == "analysis"
            and claim.get("importance") == "key"
        ):
            triangulation = claim.get("triangulation", {})
            triangulation_status = (
                triangulation.get("status")
                if isinstance(triangulation, dict)
                else None
            )
            families = {
                family_of[source_id]
                for source_id in foundation_source_ids(claim_id)
                if source_id in family_of
            }
            if triangulation_status == "met" and len(families) < 2:
                errors.append(
                    _f(
                        "ledger/triangulation",
                        f"{claim_id} declares triangulation met but has "
                        f"{len(families)} normalized source family.",
                        severity="warn",
                        ids=[claim_id],
                        fix="set field triangulation",
                        remove=_drop(claim_id),
                    )
                )
            if triangulation_status == "met" and not any(
                sources_by_id[source_id].get("provenance")
                in independent_provenance
                for source_id in foundation_source_ids(claim_id)
                if source_id in sources_by_id
            ):
                errors.append(
                    _f(
                        "ledger/triangulation",
                        f"{claim_id} declares triangulation met but has "
                        "no independent source.",
                        severity="warn",
                        ids=[claim_id],
                        fix=PROVENANCE_INDEPENDENT_FIX.format(sid="S1"),
                        remove=_drop(claim_id),
                    )
                )
            if triangulation_status == "limited":
                if claim.get("confidence") == "high":
                    errors.append(
                        _f(
                            "ledger/triangulation",
                            f"{claim_id}: high-confidence key judgment cannot "
                            "use limited triangulation.",
                            severity="warn",
                            ids=[claim_id],
                            fix="set field triangulation",
                            remove=_drop(claim_id),
                        )
                    )
                if not str(claim.get("limitations") or "").strip():
                    errors.append(
                        _f(
                            "ledger/triangulation",
                            f"{claim_id} has limited triangulation but no limitation.",
                            severity="warn",
                            ids=[claim_id],
                            fix="set field limitations",
                            remove=_drop(claim_id),
                        )
                    )
            if triangulation_status == "not_applicable":
                errors.append(
                    _f(
                        "ledger/triangulation",
                        f"{claim_id} is a key analysis; triangulation cannot be "
                        "not applicable.",
                        severity="warn",
                        ids=[claim_id],
                        fix="set field triangulation",
                        remove=_drop(claim_id),
                    )
                )

        if claim.get("importance") == "key":
            # Judged on the claim's own sources when it has any: a supporting
            # claim's independent source does not launder a key claim that
            # cites only the subject.
            judged = direct_foundations or foundations
            if not judged:
                errors.append(
                    _f(
                        "ledger/key-claim",
                        f"{claim_id}: key claim has no direct source and no "
                        "first-level supporting claim with one.",
                        severity="warn",
                        ids=[claim_id],
                        fix=_key_claim_fix(claim_id),
                        remove=_drop(claim_id),
                    )
                )
            elif all(
                sources_by_id[source_id].get("provenance")
                in interested_provenance
                for source_id in judged
            ):
                errors.append(
                    _f(
                        "ledger/key-claim",
                        f"{claim_id}: key claim rests only on interested/unverified sources "
                        f"({', '.join(sorted(judged))}); add independent "
                        "evidence or record the area as a gap.",
                        severity="warn",
                        ids=[claim_id, *sorted(judged)],
                        fix=_key_claim_fix(claim_id),
                        remove=_drop(claim_id),
                    )
                )
            declared_roles = {
                source_id: {
                    role
                    for role in sources_by_id[source_id].get("roles", [])
                    if isinstance(role, str)
                }
                for source_id in (direct_foundations or foundations)
            }
            if any(declared_roles.values()) and not any(
                roles - {"subject_official"}
                for roles in declared_roles.values()
            ):
                errors.append(
                    f"{claim_id}: every source under this key claim is "
                    "subject_official. A key judgment needs at least one "
                    "source in another role (independent analysis, empirical "
                    "data, affected stakeholder, or historical record)."
                )

    def reaches_sourced_claim(claim_id, visited=None):
        visited = set() if visited is None else visited
        if claim_id in visited:
            return False
        visited.add(claim_id)
        claim = claims_by_id.get(claim_id)
        if not claim:
            return False
        if direct_source_ids(claim_id):
            return True
        supports = claim.get("supports", [])
        if not isinstance(supports, list):
            return False
        return any(
            reaches_sourced_claim(related_id, visited)
            for related_id in supports
        )

    for claim_id, claim in claims_by_id.items():
        if (
            claim.get("kind") == "analysis"
            and claim.get("include_in_report") is True
            and not reaches_sourced_claim(claim_id)
        ):
            errors.append(f"{claim_id} has no sourced foundation.")
    # Cycles are detected on the whole supports graph, never short-circuited
    # by a sourced claim on the way down: supports points strictly downward,
    # so any cycle is a collapsed source graph and is rejected outright.
    for path in _supports_cycles(claims_by_id):
        errors.append(
            _f(
                "ledger/reference",
                "Analysis has circular support: "
                f"{' -> '.join(path)}. supports must point strictly downward to "
                "the evidence a claim rests on.",
                severity="warn",
                ids=list(path),
                fix=f"remove {path[0]} from supports in claims/<file>, then alx claim add claims/<file>",
            )
        )

    synthesis = data.get("synthesis")
    if isinstance(synthesis, dict):
        central = synthesis.get("central_judgment_claim_ids", [])
        central = central if isinstance(central, list) else []
        counterevidence = synthesis.get("counterevidence_claim_ids", [])
        counterevidence = (
            counterevidence if isinstance(counterevidence, list) else []
        )
        for claim_id in central:
            claim = claims_by_id.get(claim_id)
            if not claim:
                errors.append(
                    _f(
                        "ledger/synthesis",
                        f"Synthesis references unknown central judgment {claim_id}.",
                        severity="warn",
                        ids=[claim_id],
                        fix=f"remove {claim_id} from synthesis.central_judgment_claim_ids",
                    )
                )
            elif (
                claim.get("importance") != "key"
                or claim.get("include_in_report") is not True
            ):
                errors.append(
                    _f(
                        "ledger/synthesis",
                        f"Central judgment {claim_id} must be an included key claim.",
                        severity="warn",
                        ids=[claim_id],
                        fix=f"remove {claim_id} from synthesis.central_judgment_claim_ids",
                    )
                )
        missing_key = [
            claim_id
            for claim_id, claim in claims_by_id.items()
            if (
                claim.get("importance") == "key"
                and claim.get("include_in_report") is True
                and claim_id not in central
            )
        ]
        if missing_key:
            errors.append(
                _f(
                    "ledger/synthesis",
                    f"{len(missing_key)} key report claims are not in "
                    f"synthesis.central_judgment_claim_ids: {' '.join(missing_key)}",
                    severity="warn",
                    ids=missing_key,
                    fix=_synthesis_ids_fix(missing_key),
                )
            )
        for claim_id in counterevidence:
            if claim_id not in claim_set:
                errors.append(
                    _f(
                        "ledger/reference",
                        f"Synthesis references unknown counterevidence {claim_id}.",
                        severity="warn",
                        ids=[claim_id],
                        fix=f"remove {claim_id} from synthesis.counterevidence_claim_ids",
                    )
                )
        adversarial_claims = set()
        adversarial_tests = synthesis.get("adversarial_tests", [])
        if not isinstance(adversarial_tests, list):
            adversarial_tests = []
        for test in adversarial_tests:
            if not isinstance(test, dict):
                continue
            test_claims = test.get("claim_ids")
            if not isinstance(test_claims, list):
                continue
            for claim_id in test_claims:
                adversarial_claims.add(claim_id)
                if claim_id not in claim_set:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"Synthesis references unknown adversarial-test claim {claim_id}.",
                            severity="warn",
                            ids=[claim_id],
                            fix=f"remove {claim_id} from synthesis.adversarial_tests",
                        )
                    )
        for claim_id in counterevidence:
            if claim_id in claim_set and claim_id not in adversarial_claims:
                # R23: an untested counterevidence claim is a thin synthesis,
                # not a fabricated one; it is advice, and it has its own fix.
                errors.append(
                    _f(
                        "ledger/reference",
                        f"Counterevidence {claim_id} is not tested by an "
                        "adversarial hypothesis (threshold: 1 adversarial_tests "
                        "entry naming it; actual: 0).",
                        severity="warn",
                        ids=[claim_id],
                        fix=ADVERSARIAL_TESTS_FIX,
                    )
                )

        implications = synthesis.get("implications")
        implications = implications if isinstance(implications, list) else []
        for implication in implications:
            if not isinstance(implication, dict):
                continue
            implication_claims = implication.get("claim_ids")
            if not isinstance(implication_claims, list):
                continue
            for claim_id in implication_claims:
                if claim_id not in claim_set:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"Synthesis references unknown implication claim {claim_id}.",
                            severity="warn",
                            ids=[claim_id],
                            fix=f"remove {claim_id} from synthesis.implications",
                        )
                    )
            if not set(implication_claims).intersection(central):
                errors.append(
                    "Implication is not linked to a central judgment."
                )
        takeaways = synthesis.get("decisions_or_takeaways")
        takeaways = takeaways if isinstance(takeaways, list) else []
        for takeaway in takeaways:
            if not isinstance(takeaway, dict):
                continue
            rationale_claims = takeaway.get("rationale_claim_ids")
            if not isinstance(rationale_claims, list):
                continue
            for claim_id in rationale_claims:
                if claim_id not in claim_set:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"Synthesis references unknown takeaway rationale {claim_id}.",
                            severity="warn",
                            ids=[claim_id],
                            fix=f"remove {claim_id} from synthesis.decisions_or_takeaways",
                        )
                    )
            if not set(rationale_claims).intersection(central):
                errors.append(
                    "Takeaway is not linked to a central judgment."
                )
        scenarios = synthesis.get("scenarios")
        scenarios = scenarios if isinstance(scenarios, list) else []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            scenario_claims = scenario.get("claim_ids")
            if not isinstance(scenario_claims, list):
                continue
            for claim_id in scenario_claims:
                if claim_id not in claim_set:
                    errors.append(
                        _f(
                            "ledger/reference",
                            f"Synthesis references unknown scenario claim {claim_id}.",
                            severity="warn",
                            ids=[claim_id],
                            fix=f"remove {claim_id} from synthesis.scenarios",
                        )
                    )
            if not set(scenario_claims).intersection(central):
                errors.append(
                    "Scenario is not linked to a central judgment."
                )

        if any(isinstance(item, dict) and "priority" in item for item in coverage):
            high_priority_claims = {
                claim_id
                for item in coverage
                if isinstance(item, dict) and item.get("priority") == "high"
                for claim_id in coverage_claim_ids(item)
            }
            uncovered = [
                claim_id
                for claim_id in central
                if claim_id in claim_set and claim_id not in high_priority_claims
            ]
            if uncovered:
                errors.append(
                    _f(
                        "ledger/reference",
                        f"Central judgment {' '.join(uncovered)} is not covered by a "
                        "high-priority research area.",
                        severity="warn",
                        ids=uncovered,
                        fix=(
                            "set coverage[i].claim_ids to include "
                            f"{' '.join(uncovered)} on a high-priority item "
                            "in a patch file, then alx ledger merge <patch>"
                        ),
                    )
                )
    return [_ref(item) for item in errors]


def validate_references(data, cache_dir=None):
    """Legacy strings; pass the sources cache so R14 sees the page (run 6, C25)."""
    return _as_legacy(_reference_findings(data, cache_dir))


_COVERAGE_STATUSES = frozenset(
    {"unstarted", "in_progress", "supported", "disputed", "gap"}
)
_CLAIM_ID_LIST_HINT = '["C1","C2"]'


def _str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def notes_shape_findings(ledger):
    """R35.14: WARN only where check reads a notes field; store as given."""
    findings = []
    if not isinstance(ledger, dict):
        return findings
    if "coverage" in ledger:
        coverage = ledger["coverage"]
        if not isinstance(coverage, list):
            findings.append(
                _f(
                    "ledger/coverage",
                    "coverage is not an object — stored as given; check reads "
                    "area/status/claim_ids from objects only",
                    severity="warn",
                    ids=[],
                    fix=COVERAGE_PATCH_FIX,
                )
            )
        else:
            for i, item in enumerate(coverage):
                if not isinstance(item, dict):
                    findings.append(
                        _f(
                            "ledger/coverage",
                            f"coverage[{i}] is not an object — stored as given; "
                            "check reads area/status/claim_ids from objects only",
                            severity="warn",
                            ids=[],
                            fix=COVERAGE_PATCH_FIX,
                        )
                    )
                    continue
                if "status" in item and item["status"] not in _COVERAGE_STATUSES:
                    findings.append(
                        _f(
                            "ledger/coverage",
                            f"coverage[{i}].status '{item['status']}' is not one of "
                            "unstarted|in_progress|supported|disputed|gap — stored "
                            "as given; check tracks coverage only for "
                            "supported|disputed|gap",
                            severity="warn",
                            ids=[],
                            fix=COVERAGE_PATCH_FIX,
                        )
                    )
                if "claim_ids" in item and not _str_list(item["claim_ids"]):
                    findings.append(
                        _f(
                            "ledger/coverage",
                            f"coverage[{i}].claim_ids must be a list of claim ids "
                            f"like {_CLAIM_ID_LIST_HINT} — stored as given",
                            severity="warn",
                            ids=[],
                            fix=COVERAGE_PATCH_FIX,
                        )
                    )
                elif "claim_ids" not in item and "claims" not in item:
                    findings.append(
                        _f(
                            "ledger/coverage",
                            f"coverage[{i}] '{item.get('area', '')}': no claim_ids — "
                            'check reads claim_ids: ["C1", …]',
                            severity="warn",
                            ids=[],
                            fix=COVERAGE_PATCH_FIX,
                        )
                    )
    synthesis = ledger.get("synthesis")
    if not isinstance(synthesis, dict):
        return findings
    for key in ("central_judgment_claim_ids", "counterevidence_claim_ids"):
        if key in synthesis and not _str_list(synthesis[key]):
            findings.append(
                _f(
                    "ledger/synthesis",
                    f"synthesis.{key} must be a list of claim ids like "
                    f"{_CLAIM_ID_LIST_HINT} — stored as given",
                    severity="warn",
                    ids=[],
                    fix=_synthesis_ids_fix([]),
                )
            )
    buckets = (
        ("adversarial_tests", "claim_ids"),
        ("implications", "claim_ids"),
        ("decisions_or_takeaways", "rationale_claim_ids"),
        ("scenarios", "claim_ids"),
    )
    for bucket, field in buckets:
        items = synthesis.get(bucket)
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            if isinstance(item, dict) and isinstance(item.get(field), list):
                continue
            findings.append(
                _f(
                    "ledger/synthesis",
                    f"synthesis.{bucket}[{i}] is a {type(item).__name__}; "
                    f"check links it to claims only through an object with "
                    f"{field} — stored as given",
                    severity="warn",
                    ids=[],
                    fix=_synthesis_ids_fix([]),
                )
            )
    return findings


def collect_findings(ledger, *, schema_path=None, cache_dir=None):
    schema_file = Path(schema_path) if schema_path else DEFAULT_SCHEMA
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    findings = []
    for item in validate_schema(ledger, schema):
        location, _, detail = item.partition(": ")
        findings.append(_f("ledger/schema", item, fix=schema_remedy(location, detail)))
    findings.extend(notes_shape_findings(ledger))
    findings.extend(_reference_findings(ledger, cache_dir))
    if cache_dir:
        findings.extend(_offline_probe_findings(ledger, cache_dir))
    return findings


def _offline_probe_findings(ledger, cache_dir, *, with_context=True):
    try:
        from source_fidelity import probe_findings, read_cache
    except ImportError:
        return []
    findings = []
    sources = {
        source.get("source_id"): source
        for source in ledger.get("sources") or []
        if isinstance(source, dict)
    }
    for claim in ledger.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        # R22: two passages from one page are two evidence entries, and each is
        # probed on its own; source_ids is the fallback for a legacy claim.
        entries = [
            (entry.get("source_id"), entry.get("extract_or_location"))
            for entry in claim.get("source_evidence") or []
            if isinstance(entry, dict) and entry.get("source_id")
        ] or [(source_id, None) for source_id in claim.get("source_ids") or []]
        for source_id, extract in entries:
            cached = read_cache(cache_dir, source_id)
            if cached is None:
                continue
            text, meta = cached
            # cache_meta carries the recorded probe contexts, so offline
            # `check` produces fidelity/context-changed (spec §7.2.6) instead
            # of waiting for a successful live receipt.
            findings.extend(
                probe_findings(
                    claim, sources.get(source_id, {}), text,
                    cache_meta=meta if with_context else None,
                    extract=extract,
                )
            )
    return findings


#: Keys `references/evidence-ledger.schema.json` requires on every claim that a
#: claim-input object never supplies. `expand_claim_input` fills them so its
#: result validates against the ledger schema (pinned contract: claim-input ->
#: full v4 claim).
CLAIM_DEFAULTS = {
    # R28: kind and importance are no longer required of a claim input; the
    # least-committal reading is the default.
    "kind": "fact",
    "importance": "supporting",
    "as_of": None,
    "confidence": "medium",
    "status": "supported",
    "supports": [],
    "contradicts": [],
    "person_ids": [],
    "reasoning": None,
    "decision_relevance": None,
    "what_would_change": None,
    "resolution": None,
    "limitations": None,
    "verified_at": None,
}


def _triangulation_rationale(families):
    if len(families) >= 2:
        return "Independent source families carry this claim: " + ", ".join(families) + "."
    return (
        "Only one source family carries this claim: "
        + (families[0] if families else "none")
        + "."
    )


def expand_claim_input(item, ledger, *, cache_meta):
    evidence = item.get("source_evidence") if isinstance(item.get("source_evidence"), list) else []
    source_ids = list(
        dict.fromkeys(
            entry.get("source_id")
            for entry in evidence
            if isinstance(entry, dict) and entry.get("source_id")
        )
    )
    sources_by_id = {
        source.get("source_id"): source
        for source in ledger.get("sources") or []
        if isinstance(source, dict) and source.get("source_id")
    }
    families = {
        _normalized_family(sources_by_id[source_id].get("source_family"))
        for source_id in source_ids
        if source_id in sources_by_id
    }
    families.discard("")
    fetched = None
    if isinstance(cache_meta, dict):
        for source_id in source_ids:
            meta = cache_meta.get(source_id) or {}
            if isinstance(meta, dict) and meta.get("fetched_at"):
                fetched = meta["fetched_at"]
                break
    claim = dict(item)
    claim.pop("report_paragraph", None)
    claim["source_ids"] = source_ids
    claim["person_ids"] = derive_person_ids(claim, ledger.get("people"))
    claim["include_in_report"] = True
    claim["report_excerpts"] = []
    claim["triangulation"] = {
        "status": "met" if len(families) >= 2 else "limited",
        "rationale": _triangulation_rationale(sorted(families)),
    }
    if fetched:
        claim["verified_at"] = fetched
    for key, value in CLAIM_DEFAULTS.items():
        claim.setdefault(key, value)
    if isinstance(claim.get("verified_at"), str):
        claim["verified_at"] = claim["verified_at"][:10]
    if claim.get("as_of") is None:
        # The cache stamp is UTC and `report_date` is local, so preferring
        # verified_at keeps `verified_at >= as_of` across a date rollover.
        claim["as_of"] = claim.get("verified_at") or ledger.get("report_date")
    if evidence and not claim.get("extract_or_location"):
        claim["extract_or_location"] = evidence[0].get("extract_or_location", "")
    return claim


def _claim_input_field(error):
    """Addendum 11: the field a claim-input schema error names (as J2 derives it)."""
    location, _, detail = str(error).partition(": ")
    path = (
        ""
        if location in {"", "<root>"} or not _SCHEMA_PATH_RE.match(location)
        else location
    )
    required = _SCHEMA_REQUIRED_RE.search(detail)
    if required:
        path = f"{path}.{required.group(1)}" if path else required.group(1)
    return path if path and _SCHEMA_PATH_RE.match(path) else "claim"


def _claim_input_remedy(field):
    """A claim input is repaired in its own file and re-enters through `claim add`."""
    return f"set field {field} in claims/*.json, then alx claim add claims/*.json"


def _claim_input_schema_findings(claim):
    if not CLAIM_INPUT_SCHEMA.is_file():
        return []
    schema = json.loads(CLAIM_INPUT_SCHEMA.read_text(encoding="utf-8"))
    claim_id = claim.get("claim_id")
    if not claim_id:
        return [
            _f(
                "ledger/claim-input",
                "add claim_id",
                fix=_claim_input_remedy("claim_id"),
            )
        ]
    return [
        _f(
            "ledger/claim-input",
            item,
            ids=[claim_id],
            fix=_claim_input_remedy(_claim_input_field(item)),
        )
        for item in validate_schema(claim, schema)
    ]


_CJK_CHARACTER = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def _cached_documents(claim, cache_dir):
    """Normalized cache text for every source this claim cites."""
    if not cache_dir:
        return []
    try:
        from source_fidelity import read_cache, strip_markup
    except ImportError:
        return []
    source_ids = list(claim.get("source_ids") or [])
    source_ids.extend(
        entry.get("source_id")
        for entry in claim.get("source_evidence") or []
        if isinstance(entry, dict) and entry.get("source_id")
    )
    documents = []
    for source_id in dict.fromkeys(source_ids):
        cached = read_cache(cache_dir, source_id)
        if cached is None:
            continue
        # Word spacing is kept here: the quantity scan reads this haystack and
        # needs adjacent figures to stay apart.
        documents.append(strip_markup(cached[0]))
    return documents


def source_year_text(claim, ledger, cache_dir=None):
    """R14 haystack: the claim's own extracts, cached text, title/published."""
    sources_by_id = {
        source.get("source_id"): source
        for source in (ledger or {}).get("sources") or []
        if isinstance(source, dict)
    }
    cited = list(claim.get("source_ids") or [])
    cited.extend(
        entry.get("source_id")
        for entry in claim.get("source_evidence") or []
        if isinstance(entry, dict)
    )
    parts = [
        _text(entry.get("extract_or_location"))
        for entry in claim.get("source_evidence") or []
        if isinstance(entry, dict)
    ]
    parts.extend(_cached_documents(claim, cache_dir))
    for source_id in dict.fromkeys(cited):
        source = sources_by_id.get(source_id) or {}
        parts.extend([_text(source.get("title")), _text(source.get("published"))])
    return " ".join(part for part in parts if part)


def _extract_length_findings(claim, *, cache_dir=None):
    """Ruling R13: length is advice, never a fabrication check.

    The whole extract may read short; only `fidelity/mismatch` decides whether
    it is real. Ellipsis-separated pieces carry no length floor at all.
    """
    findings = []
    claim_id = claim.get("claim_id", "")
    texts = []
    if claim.get("extract_or_location"):
        texts.append(str(claim.get("extract_or_location")))
    for entry in claim.get("source_evidence") or []:
        if isinstance(entry, dict) and entry.get("extract_or_location"):
            texts.append(str(entry.get("extract_or_location")))
    for text in texts:
        folded = unicodedata.normalize("NFKC", text)
        compact = re.sub(r"\s+", "", folded)
        threshold = 10 if _CJK_CHARACTER.search(compact) else 20
        if len(compact) < threshold:
            findings.append(
                Finding(
                    family="ledger/extract-length",
                    severity="warn",
                    klass="A",
                    ids=_ids_in(claim_id),
                    message=(
                        f"{claim_id}: extract length {len(compact)} is below "
                        f"threshold {threshold}; extend the quote"
                    ),
                    fix="extend the quote in claims/<file>",
                    remove="",
                )
            )
    return findings


def claim_findings(claim, ledger, *, cache_dir=None):
    findings = []
    findings.extend(_claim_input_schema_findings(claim))
    findings.extend(_extract_length_findings(claim, cache_dir=cache_dir))
    working = dict(claim)
    if working.get("source_ids") is None and working.get("source_evidence"):
        working = expand_claim_input(working, ledger, cache_meta={})
    findings.extend(
        _evidence_coverage_findings(
            working, source_text=source_year_text(working, ledger, cache_dir)
        )
    )
    findings.extend(_derived_findings(working))
    claims = [item for item in (ledger.get("claims") or []) if isinstance(item, dict)]
    shadow = dict(ledger)
    if working.get("claim_id") not in {item.get("claim_id") for item in claims}:
        shadow["claims"] = claims + [working]
    claim_id = working.get("claim_id")
    findings.extend(
        item
        for item in _reference_findings(shadow, cache_dir)
        if claim_id and claim_id in item.ids
    )
    if cache_dir:
        findings.extend(
            _offline_probe_findings(
                {"claims": [working], "sources": ledger.get("sources")},
                cache_dir,
                with_context=False,
            )
        )
    return findings


def _halved_minimums(node):
    """Return the schema with every prose floor doubled back to the full one."""
    if isinstance(node, dict):
        return {
            key: value * 2
            if key == "minLength" and isinstance(value, int) and value > 1
            else _halved_minimums(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_halved_minimums(item) for item in node]
    return node


def prose_floor_errors(data, schema):
    """J3: a schema's string minimums are the CJK floor (spec §7.1 halving).

    Non-CJK prose must meet the full floor, which is twice the schema's, and
    the message states threshold and actual the way every other length rule
    does. CJK text is already bounded by the schema itself.
    """
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError:
        return []

    # B7: content-review minLength is the full floor for every script; no
    # J3 doubling (Latin would become 40). CJK still skips below.
    floor_schema = (
        schema
        if schema.get("$id") == _CONTENT_REVIEW_SCHEMA_ID
        else _halved_minimums(schema)
    )
    validator = Draft202012Validator(floor_schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        if error.validator != "minLength" or not isinstance(error.instance, str):
            continue
        if _prose_minimum(error.instance) == _CJK_PROSE_MIN:
            continue
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(
            f"{location}: {error.instance!r} is too short "
            f"(threshold {error.validator_value}, actual {len(error.instance)})"
        )
    return errors


#: J2: the remedy of a schema finding names the field the schema error named.
#: `claims.*` re-enters through `claim add`; the four mergeable sections through
#: `ledger merge`; anything else is edited in `ledger.json`.
_SCHEMA_REQUIRED_RE = re.compile(r"'([^']+)' is a required property")
_SCHEMA_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
MERGEABLE_SECTIONS = ("brief", "people", "coverage", "synthesis")


def schema_remedy(location, detail=""):
    """Return the pinned remedy for one schema error, or "" when it names none."""
    path = "" if location in {"", "<root>"} or not _SCHEMA_PATH_RE.match(location) else location
    required = _SCHEMA_REQUIRED_RE.search(detail)
    if required:
        field = required.group(1)
        if path != field and not path.endswith(f".{field}"):
            path = f"{path}.{field}" if path else field
    if not path or not _SCHEMA_PATH_RE.match(path):
        return ""
    section = path.split(".", 1)[0]
    if section == "claims":
        return f"set field {path} in claims/*.json, then alx claim add claims/*.json"
    if section in MERGEABLE_SECTIONS:
        return f"set field {path} in {section} via alx ledger merge"
    return f"set field {path} in ledger.json"


def validate_schema(data, schema):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError:
        return [
            f"jsonschema is not importable from {sys.executable}. Run alx through "
            "the managed runtime (it relocates itself; if it printed RUNTIME MISSING, "
            "run scripts/install.sh / install.ps1)."
        ]

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an Alexandria evidence ledger")
    parser.add_argument("ledger", help="Evidence ledger JSON")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="JSON Schema path")
    args = parser.parse_args(argv)

    try:
        data = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        findings = collect_findings(data, schema_path=args.schema)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(render_grouped(findings), file=sys.stderr)
    if hard_errors(findings):
        return 1
    print(f"[OK] Evidence ledger validated: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
