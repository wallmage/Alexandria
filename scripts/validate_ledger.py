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
from urllib.parse import urlsplit

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
        "ledger/claim-input",
        "ledger/reference",
    }
)


#: Quantity scan is a heuristic; the verbatim extract is the fabrication gate.
WARN_FAMILIES = frozenset({"ledger/quantity"})


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
_CJK_PROSE_MIN = 20
_LATIN_PROSE_MIN = 40

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

def mentions_person_alias(text, person):
    """Match a registered name or alias without substringing another word."""
    folded = str(text or "").casefold()
    values = [person.get("name"), *(person.get("aliases") or [])]
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
    working = _normalize_dates(working)
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
                "ledger/claim-input",
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
                "ledger/claim-input",
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
        find_id = next(
            (
                entry.get("source_id")
                for entry in claim.get("source_evidence") or []
                if isinstance(entry, dict) and entry.get("source_id")
            ),
            None,
        )
        if not find_id:
            linked = claim.get("source_ids")
            if isinstance(linked, list) and linked:
                find_id = linked[0]
        fix = (
            f"alx find {find_id} {display}"
            if find_id
            else "set field extract_or_location"
        )
        errors.append(
            _f(
                "ledger/quantity",
                f"{claim_id}: '{display}' is in the claim but not in "
                f"{find_id or 'the cited sources'} (extracts or cached page). "
                f"Fix: {fix}, or reword the claim.",
                ids=_ids_in(f"{claim_id} {find_id or ''}"),
                fix=fix,
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


def _reference_findings(data, cache_dir=None):
    """Unknown source_id (hard) plus the quantity/empty-extract scan."""
    if not isinstance(data, dict):
        return []
    sources = data.get("sources", [])
    claims = data.get("claims", [])
    if not isinstance(sources, list) or not isinstance(claims, list):
        return []
    source_set = {
        source.get("source_id")
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }
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
    findings = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        raw = claim.get("source_ids")
        if raw is None:
            evidence = claim.get("source_evidence")
            evidence = evidence if isinstance(evidence, list) else []
            source_links = list(
                dict.fromkeys(
                    entry.get("source_id")
                    for entry in evidence
                    if isinstance(entry, dict) and entry.get("source_id")
                )
            )
        elif not isinstance(raw, list):
            source_links = []
        else:
            source_links = list(raw)
        for source_id in source_links:
            if source_id not in source_set:
                findings.append(
                    _f(
                        "ledger/reference",
                        f"{claim_id} references unknown source {source_id}.",
                        ids=[claim_id, source_id],
                        fix="set field source_ids",
                        remove=_drop(claim_id),
                    )
                )
        ledger_dates = [claim.get("as_of"), claim.get("verified_at")]
        for source_id in source_links:
            source = sources_by_id.get(source_id) or {}
            ledger_dates.extend([source.get("accessed"), source.get("published")])
        inherited = ""
        if claim.get("kind") == "analysis":
            inherited = " ".join(
                _claim_evidence_text(claims_by_id[related_id])
                for related_id in claim.get("supports") or []
                if related_id in claims_by_id
            )
        findings.extend(
            _evidence_coverage_findings(
                claim,
                ledger_dates,
                inherited,
                source_year_text(claim, data, cache_dir),
            )
        )
    return findings


def validate_references(data, cache_dir=None):
    """Legacy strings; pass the sources cache so R14 sees the page (run 6, C25)."""
    return _as_legacy(_reference_findings(data, cache_dir))


def collect_findings(ledger, *, schema_path=None, cache_dir=None):
    del schema_path
    findings = []
    findings.extend(_reference_findings(ledger, cache_dir))
    if cache_dir:
        findings.extend(_offline_probe_findings(ledger, cache_dir))
    return findings


def _offline_probe_findings(ledger, cache_dir):
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
                    claim, sources.get(source_id, {}), text, cache_meta=meta,
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


def claim_findings(claim, ledger, *, cache_dir=None):
    findings = []
    findings.extend(_claim_input_schema_findings(claim))
    working = dict(claim)
    if working.get("source_ids") is None and working.get("source_evidence"):
        working = expand_claim_input(working, ledger, cache_meta={})
    claims = [item for item in (ledger.get("claims") or []) if isinstance(item, dict)]
    shadow = dict(ledger)
    shadow["claims"] = [
        item for item in claims if item.get("claim_id") != working.get("claim_id")
    ] + [working]
    claim_id = working.get("claim_id")
    findings.extend(
        item
        for item in _reference_findings(shadow, cache_dir)
        if claim_id and claim_id in item.ids
    )
    if cache_dir:
        findings.extend(
            _offline_probe_findings({"claims": [working], "sources": ledger.get("sources")}, cache_dir)
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

    validator = Draft202012Validator(_halved_minimums(schema))
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
