#!/usr/bin/env python3
"""Validate an Alexandria evidence ledger and its internal references."""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gate_severity import emit_findings  # noqa: E402

DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "references"
    / "evidence-ledger.schema.json"
)

#: Days a time-sensitive record may lag the report date before it is stale.
FRESHNESS_WINDOW_DAYS = 30

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

PROTECTED_LIVING_STATUSES = {
    "living",
    "recently_deceased",
    "unknown",
}
HUMAN_HARM_PATTERN = re.compile(
    r"(?i)\b(?:alleg(?:e[ds]?|ation)|accus(?:e[ds]?|ation)|"
    r"investigat(?:ed|ion)|charged(?!\s+(?:the\s+)?(?:battery|device|phone|"
    r"account|card|fee|price))|indicted|convicted|acquitted|"
    r"liable|misconduct|fraud|harass(?:ed|ment)|abuse[ds]?|assault(?:ed)?|"
    r"bribery|corrupt(?:ion)?|theft|stole|embezzl(?:e[ds]?|ement)|"
    r"murder(?:ed)?|manslaughter|kill(?:ed|ing)?|launder(?:ed|ing)?|"
    r"tax evasion|plagiariz(?:ed|ing)|discriminat(?:ed|ion)|"
    r"retaliat(?:ed|ion)|extort(?:ed|ion)|blackmail(?:ed)?|"
    r"kidnap(?:ped|ping)?|traffick(?:ed|ing)?|perjury|forgery|"
    r"falsif(?:ied|ication)|scam(?:med)?|wrongdoing|personal failing)\b|"
    r"指控|被控|起訴|起诉|定罪|無罪|无罪|欺詐|欺诈|騷擾|骚扰|賄賂|贿赂"
)
SENSITIVE_PRIVATE_PATTERN = re.compile(
    r"(?i)\b(?:medical|diagnos(?:is|ed)|health condition|sexuality|religion|"
    r"minor child|romantic|addiction|home address|private financ)"
    r"|病歷|病历|診斷|诊断|性取向|宗教|未成年子女|住址|私人財務|私人财务"
)
LEGAL_STAGE_PATTERNS = {
    "alleged": re.compile(r"(?i)\b(?:alleg(?:e[ds]?|ation)|accus(?:e[ds]?|ation))\b|指控"),
    "investigated": re.compile(r"(?i)\b(?:investigat(?:ed|ion)|under investigation)\b|調查|调查"),
    "charged": re.compile(r"(?i)\b(?:charged?|criminal charges?)\b|被控"),
    "indicted": re.compile(r"(?i)\b(?:indicted|indictment)\b|起訴|起诉"),
    "settled_no_admission": re.compile(
        r"(?i)\bsettled\b.{0,60}\bwithout (?:admitting|admission)\b"
    ),
    "settled_with_admission": re.compile(
        r"(?i)\bsettled\b.{0,60}\b(?:admitted|admission)\b"
    ),
    "found_liable": re.compile(r"(?i)\b(?:found|held) liable\b|裁定.*責任|裁定.*责任"),
    "convicted": re.compile(r"(?i)\b(?:convicted|conviction|found guilty)\b|定罪"),
    "acquitted": re.compile(r"(?i)\b(?:acquitted|acquittal|found not guilty)\b|無罪|无罪"),
    "overturned": re.compile(r"(?i)\b(?:overturned|vacated|reversed on appeal)\b|推翻"),
    "expunged": re.compile(r"(?i)\b(?:expunged|sealed record)\b|撤銷記錄|撤销记录"),
    "retracted": re.compile(r"(?i)\b(?:retracted|withdrew|withdrawn)\b|撤回"),
}


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
_HAN_NUMBER_RE = re.compile("[" + _HAN_NUMERAL_CHARS + "]+" + _HAN_DECIMAL_SUFFIX)

#: Chinese measure words gated as sufficient context for a spelled-out count,
#: mirroring how English scans every spelled count ("three CVEs", "ten
#: engineers") but Chinese numerals are far more idiomatic outside a numeric
#: context ("一起", "一些", "二手", "十分"): requiring a classifier keeps those
#: silent without a stoplist. Deliberately narrow to 個/个, the classifier in
#: both worked examples ("三個漏洞", "十八個月"); broadening it is deferred.
_CJK_COUNT_CLASSIFIERS = frozenset({"個", "个"})

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_LEDGER_ID_RE = re.compile(
    _NOT_WORD_BEFORE + r"[CS][0-9]{1,7}" + _NOT_WORD_AFTER
)
_IDENTIFIER_RE = re.compile(
    _NOT_WORD_BEFORE
    + r"[A-Za-z]{2,}[-‑][0-9][0-9A-Za-z‑-]*"
    + _NOT_WORD_AFTER
)
_ISO_DATE_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})-([0-9]{2})-([0-9]{2})" + _NOT_WORD_AFTER
)
_ISO_MONTH_RE = re.compile(
    _NOT_WORD_BEFORE + r"([0-9]{4})-([0-9]{2})" + _NOT_WORD_AFTER
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
    """
    total = 0
    group = 0
    current = None
    for char in phrase:
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


def _han_numeral_string(phrase):
    """Return the normalized digit string a (possibly decimal) Han phrase denotes.

    A 點/点 marker splits the phrase into a whole part, resolved the normal
    way through _han_phrase_value, and a fractional part read digit-by-digit
    ("三十五點五" -> whole 35, fraction "5" -> "35.5"; "零點八" -> "0.8"), never
    through a place-value unit: "點五" is always .5, not 十/百/千 acting on 五.
    The result is passed through _normalize_number so a Han decimal and its
    digit-form equivalent land on the same key regardless of trailing zeros
    ("三十五點五零" and "35.50" both normalize to "35.5").
    """
    for marker in _HAN_DECIMAL_MARKER_CHARS:
        if marker in phrase:
            whole, _, fraction = phrase.partition(marker)
            fraction_digits = "".join(
                str(_HAN_DIGIT_VALUES[char])
                for char in fraction
                if char in _HAN_DIGIT_VALUES
            )
            raw = (
                f"{_han_phrase_value(whole)}.{fraction_digits}"
                if fraction_digits
                else str(_han_phrase_value(whole))
            )
            return _normalize_number(raw)
    return _normalize_number(str(_han_phrase_value(phrase)))


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
#: 2026年7月28日 is one date, exactly as "28 July 2026" is. Left as bare digits it
#: would assert three separate figures, so it is normalized like every other
#: date form. A bare 2026年 stays a number, which is what "in 2026" already does.
_CJK_DATE_RE = re.compile(
    r"([0-9]{4})\s*年\s*([0-9]{1,2})\s*月(?:\s*([0-9]{1,2})\s*日)?"
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


def _normalize_dates(text):
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

    def month_name(match):
        month = _MONTHS[match.group(2).casefold()]
        day = match.group(1) or match.group(3)
        year = match.group(4)
        if day:
            return f"{year}-{month:02d}-{int(day):02d}"
        return f"{year}-{month:02d}"

    return _MONTH_NAME_DATE_RE.sub(month_name, text)


def _scan_quantities(text):
    """Yield (display, claim_forms, evidence_forms, is_word) for a string.

    URLs and ledger IDs are ignored. Other identifiers, dates, versions, digit
    forms, and spelled-out counts create obligations. Spelled-out counts use
    their digit-equivalent forms; vague number-like words such as "dozens" do
    not create obligations.
    """
    working = _URL_RE.sub(" ", str(text or ""))
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
        form = f"d:{year}-{month}-{day}"
        return (match.group(0), {form}, {form}, False)

    def iso_month(match):
        year, month = match.group(1), match.group(2)
        form = f"d:{year}-{month}"
        return (match.group(0), {form}, {form}, False)

    def version(match):
        form = "v:" + match.group(1)
        return (match.group(0), {form}, {form}, False)

    def number(match):
        normalized = _normalize_number(match.group(1))
        forms = {f"n:{normalized}"}
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
                forms = {f"n:{int(scaled)}"}
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

    def han_number(match):
        span = match.group(0)
        if any(char in _CJK_SCALE_WORDS for char in span):
            # "萬一" and the adverb "千萬" ("by all means") open with an
            # implied 1 the way a bare "million" would in English ("Revenue
            # reached a million dollars"); unlike English, that implied 1
            # collides with real idioms, so a scaled figure needs a leading
            # digit that already makes it unambiguous ("三千萬", "六億").
            if span[0] not in _HAN_DIGIT_VALUES:
                return (span, set(), set(), True)
            forms = {f"n:{_han_numeral_string(span)}"}
            return (span, forms, set(forms), False)
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

    take(_IDENTIFIER_RE, identifier)
    take(_ISO_DATE_RE, iso_date)
    take(_ISO_MONTH_RE, iso_month)
    take(_VERSION_RE, version)
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
    return forms


def _quantity_is_covered(claim_forms, evidence_forms):
    for form in claim_forms:
        if form in evidence_forms:
            return True
        if form.startswith("d:") and any(
            other.startswith(form)
            for other in evidence_forms
            if other.startswith("d:")
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


def derived_assertion_errors(claim):
    """Keep the derived-assertion escape hatch from becoming a rubber stamp."""
    claim_id = claim.get("claim_id", "<unknown>")
    entries = _derived_entries(claim)
    if not entries:
        return []
    errors = []
    claim_text = _text(claim.get("claim")).casefold()
    extract = _claim_evidence_text(claim).casefold()
    seen = set()
    for entry in entries:
        expression = _text(entry.get("expression"))
        derivation = _text(entry.get("derivation"))
        if not expression:
            errors.append(
                f"{claim_id}: derived_assertions entry has no expression; "
                "name the exact wording in claim that is derived."
            )
            continue
        folded = expression.casefold()
        if not _exact_expression_in_text(expression, claim_text):
            errors.append(
                f"{claim_id}: derived assertion '{expression}' does not appear "
                "in claim; the expression must be quoted from the claim text."
            )
        if extract and folded in extract:
            errors.append(
                f"{claim_id}: derived assertion '{expression}' already appears "
                "in extract_or_location; it is quoted evidence, not a "
                "derivation. Remove the derived_assertions entry."
            )
        if folded in seen:
            errors.append(
                f"{claim_id}: derived assertion '{expression}' is declared twice."
            )
        seen.add(folded)
        if len(derivation) < 40:
            errors.append(
                f"{claim_id}: derived assertion '{expression}' needs a "
                "derivation of at least 40 characters stating how it was "
                "computed or inferred."
            )
    if claim.get("kind") != "estimate" and len(entries) > 2:
        errors.append(
            f"{claim_id}: {len(entries)} derived assertions on a "
            f"{claim.get('kind')} claim. Split the claim, or record the "
            "arithmetic as kind 'estimate' with assumptions."
        )
    return errors


def _is_negated(text, index):
    """Report whether a status word is denied rather than asserted."""
    window = text[max(0, index - 32) : index].casefold()
    return bool(
        re.search(
            r"\b(?:not|no|never|nor|without|n't|isn't|aren't|wasn't|weren't|"
            r"cannot|hardly|fails? to|denies|denied)\b[^.;]*$",
            window,
        )
        or re.search(r"[不未沒没非][^。；]*$", window)
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


def _assertion_carrier_tokens(text, match):
    """Extract the subject/carrier around an assertion occurrence."""
    def normalize_word(word):
        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

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
    sentence = text[start:match.start()] + " " + text[match.end():end]
    words = {
        normalize_word(word)
        for word in re.findall(r"[a-z][a-z0-9'-]*", sentence.casefold())
        if word not in _ASSERTION_CARRIER_STOPWORDS and len(word) > 1
        and word not in _NUMBER_WORDS
        and word not in _ASSERTION_MEASURE_WORDS
    }
    if words:
        return words
    cjk = "".join(
        char
        for char in re.findall(r"[\u3400-\u9fff]", sentence)
        if char not in _CJK_CARRIER_NOISE_CHARS
    )
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
        if any(
            (
                not claim_carrier
                or not evidence_carrier
                or (
                    len(claim_carrier.intersection(evidence_carrier))
                    / min(len(claim_carrier), len(evidence_carrier))
                    >= 0.75
                )
                or anaphoric_quantity_binding(
                    claim_match, evidence_match
                )
            )
            for claim_match, claim_carrier in zip(
                claim_matches, claim_carriers, strict=True
            )
        ):
            return True
    return False


def evidence_coverage_errors(claim, dated_fields=(), inherited_evidence=""):
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
            f"{claim_id}: extract_or_location is empty, so nothing in the claim "
            "is evidenced. Quote the source wording or its precise location."
        ]
    extract = " ".join(part for part in (extract, _text(inherited_evidence)) if part)
    if not extract:
        return [
            f"{claim_id}: analysis rests on no recorded evidence. Quote its "
            "reasoning basis, or link the claims it is derived from."
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
    for display, claim_forms in quantitative_obligations(claim_text):
        if _quantity_is_covered(claim_forms, evidence_forms):
            continue
        matching_expressions = [
            expression
            for expression, forms in derived_quantities
            if forms and _quantity_is_covered(claim_forms, forms)
        ]
        if matching_expressions:
            used_expressions.update(matching_expressions)
            continue
        errors.append(
            f"{claim_id}: quantity '{display}' appears in claim but not in "
            "extract_or_location. Quote the figure from the source, or record "
            "it in derived_assertions with its derivation."
        )
    folded_extract = extract.casefold()
    folded_claim = claim_text.casefold()
    for label, claim_pattern, evidence_pattern in DIRECTION_ASSERTIONS:
        asserted = [
            match
            for match in re.finditer(claim_pattern, folded_claim, re.IGNORECASE)
            if not _is_negated(folded_claim, match.start())
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
            f"{claim_id}: claim asserts the {label!r} direction but the "
            "recorded evidence does not."
        )
    for label, claim_pattern, evidence_pattern in STATUS_ASSERTIONS:
        asserted = [
            match
            for match in re.finditer(claim_pattern, folded_claim, re.IGNORECASE)
            if not _is_negated(folded_claim, match.start())
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
            f"{claim_id}: claim asserts '{label}' but extract_or_location "
            "records no evidence of it. Quote the source wording that "
            "establishes the status, or declare it in derived_assertions."
        )
    for entry in derived_entries:
        expression = _text(entry.get("expression"))
        folded = expression.casefold()
        if not expression or folded in used_expressions:
            continue
        errors.append(
            f"{claim_id}: derived assertion '{expression}' excuses nothing; "
            "the escape hatch is only for quantities or status assertions "
            "that the extract does not carry."
        )
    return errors


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
            f"{claim_id}: claim asserts that something does not exist or was "
            "not found but records no evidence_of_absence. Record the "
            "queries, the expected locations, and searched_at."
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
    if claim_day and verified_day < claim_day:
        errors.append(
            f"{claim_id}: verified_at precedes as_of; a claim cannot be "
            "verified before the state it describes."
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
    interested = {"primary_interested", "secondary_dependent"}
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
            if len(_text(sources_by_id[source_id].get("family_justification"))) < 40
        )
        if unjustified:
            errors.append(
                f"Domain {domain} is split across {len(labels)} source families "
                f"({', '.join(sorted(labels))}): {', '.join(unjustified)}. "
                "Use one family per domain, or record a family_justification of "
                "at least 40 characters explaining the genuine independence."
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
            < 40
        ]
        if len(classes) > 1 and unjustified:
            errors.append(
                f"Sources on host {host} declare different independence "
                f"classes ({', '.join(sorted(classes))}) without a "
                "family_justification: "
                f"{', '.join(sorted(unjustified))}. Pages on one host are one "
                "interested party unless the difference is justified."
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


def validate_references(data):
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
    brief = data.get("brief")
    brief = brief if isinstance(brief, dict) else {}
    primary_protected_ids = {
        person_id
        for person_id, person in people_by_id.items()
        if person.get("relationship") == "primary_subject"
        and person.get("living_status") in PROTECTED_LIVING_STATUSES
    }
    independent_provenance = {
        "primary_independent",
        "secondary_independent",
    }
    interested_provenance = {
        "primary_interested",
        "secondary_dependent",
    }

    if data.get("schema_version") in {3, 4} and sources_by_id and not any(
        source.get("provenance") in independent_provenance
        for source in sources_by_id.values()
    ):
        errors.append(
            "Evidence portfolio has no independent source; record affected "
            "coverage as a gap rather than supported."
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
        coverage_claims = item.get("claim_ids", [])
        if not isinstance(coverage_claims, list):
            continue
        for claim_id in coverage_claims:
            if claim_id not in claim_set:
                errors.append(
                    f"Coverage {area} references unknown claim {claim_id}."
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
        if item.get("status") == "disputed" and not any(
            claims_by_id.get(claim_id, {}).get("status") == "disputed"
            for claim_id in coverage_claims
        ):
            errors.append(
                f"Coverage {area} is disputed but references no disputed claim."
            )
        if item.get("status") == "supported" and not any(
            claims_by_id.get(claim_id, {}).get("status") == "supported"
            for claim_id in coverage_claims
        ):
            errors.append(
                f"Coverage {area} is supported but references no supported claim."
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

    def direct_source_ids(claim_id):
        claim = claims_by_id.get(claim_id, {})
        linked = claim.get("source_ids", [])
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

    def support_reaches(claim_id, target_id, visited=None):
        visited = set() if visited is None else visited
        if claim_id in visited:
            return False
        visited.add(claim_id)
        supports = claims_by_id.get(claim_id, {}).get("supports", [])
        if not isinstance(supports, list):
            return False
        return target_id in supports or any(
            support_reaches(related_id, target_id, visited.copy())
            for related_id in supports
            if related_id in claims_by_id
        )

    family_of = _source_family_index(sources_by_id)
    errors.extend(_source_family_errors(sources_by_id))

    for item in coverage:
        if not isinstance(item, dict) or item.get("status") != "supported":
            continue
        linked_sources = {
            source_id
            for claim_id in item.get("claim_ids", [])
            for source_id in foundation_source_ids(claim_id)
            if source_id in sources_by_id
        }
        if linked_sources and all(
            sources_by_id[source_id].get("provenance") in interested_provenance
            for source_id in linked_sources
        ):
            errors.append(
                f"Supported coverage {item.get('area', '<unknown>')} relies "
                "only on interested sources; mark it as a gap or add "
                "independent evidence."
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
        source_links = claim.get("source_ids", [])
        if not isinstance(source_links, list):
            source_links = []
        for source_id in source_links:
            if source_id not in source_set:
                errors.append(f"{claim_id} references unknown source {source_id}.")
        source_evidence = claim.get("source_evidence")
        source_evidence = (
            source_evidence if isinstance(source_evidence, list) else []
        )
        evidence_ids = [
            entry.get("source_id")
            for entry in source_evidence
            if isinstance(entry, dict) and entry.get("source_id")
        ]
        for source_id in _duplicates(evidence_ids):
            errors.append(
                f"{claim_id}: duplicate source_evidence for {source_id}."
            )
        for source_id in evidence_ids:
            if source_id not in source_links:
                errors.append(
                    f"{claim_id}: source_evidence references {source_id}, "
                    "which is not a direct source for the claim."
                )
        for source_id in source_links:
            if source_id not in evidence_ids:
                errors.append(
                    f"{claim_id}: source_evidence is missing {source_id}; "
                    "record the exact extract or location supplied by that "
                    "individual source."
                )
        person_links = claim.get("person_ids", [])
        person_links = person_links if isinstance(person_links, list) else []
        for person_id in person_links:
            if person_id not in people_by_id:
                errors.append(
                    f"{claim_id} references unknown person {person_id}."
                )
        protected_people = [
            people_by_id[person_id]
            for person_id in person_links
            if person_id in people_by_id
            and people_by_id[person_id].get("living_status")
            in PROTECTED_LIVING_STATUSES
        ]
        person_claim_role = claim.get("person_claim_role")
        person_claim_assessment = claim.get("person_claim_assessment")
        if protected_people and person_claim_role not in {
            "neutral",
            "harmful",
            "sensitive_private_fact",
            "response",
            "resolution",
        }:
            errors.append(
                f"{claim_id}: claim linked to a protected person needs an "
                "explicit person_claim_role classification."
            )
        if protected_people and (
            not isinstance(person_claim_assessment, dict)
            or person_claim_assessment.get("classification")
            != person_claim_role
            or len(_text(person_claim_assessment.get("rationale"))) < 40
        ):
            errors.append(
                f"{claim_id}: protected-person claim needs a substantive "
                "person_claim_assessment matching person_claim_role."
            )
        harm_review = claim.get("human_harm_review")
        claim_text = _text(claim.get("claim"))
        harmful_text = bool(
            HUMAN_HARM_PATTERN.search(claim_text)
            or SENSITIVE_PRIVATE_PATTERN.search(claim_text)
        )
        for person_id, person in people_by_id.items():
            if (
                mentions_person_alias(claim_text, person)
                and person_id not in person_links
            ):
                errors.append(
                    f"{claim_id}: claim names registered person {person_id} "
                    "but does not link that person_id."
                )
        if harmful_text:
            if (
                brief.get("archetype") == "person"
                and len(primary_protected_ids) == 1
                and not person_links
            ):
                primary_id = next(iter(primary_protected_ids))
                errors.append(
                    f"{claim_id}: harmful claim in a person brief must link "
                    f"the protected primary subject {primary_id}; pronouns "
                    "and omitted names do not remove that accountability."
                )
            if protected_people and person_claim_role not in {
                "harmful",
                "sensitive_private_fact",
            }:
                errors.append(
                    f"{claim_id}: harmful wording conflicts with "
                    f"person_claim_role {person_claim_role!r}."
                )
        if (
            SENSITIVE_PRIVATE_PATTERN.search(claim_text)
            and protected_people
            and person_claim_role != "sensitive_private_fact"
        ):
            errors.append(
                f"{claim_id}: sensitive private wording requires "
                "person_claim_role 'sensitive_private_fact'."
            )
        needs_harm_review = bool(
            protected_people
            and (
                harmful_text
                or person_claim_role in {
                    "harmful",
                    "sensitive_private_fact",
                }
            )
        )
        if needs_harm_review and not isinstance(harm_review, dict):
            errors.append(
                f"{claim_id}: protected-person harm claim requires a "
                "human_harm_review bound to sourcing, attribution, resolution, "
                "privacy, and right of reply."
            )
        if isinstance(harm_review, dict) and protected_people:
            if (
                person_claim_role == "sensitive_private_fact"
                and harm_review.get("category") != "sensitive_private_fact"
            ):
                errors.append(
                    f"{claim_id}: person_claim_role sensitive_private_fact "
                    "requires the matching review category."
                )
            if (
                SENSITIVE_PRIVATE_PATTERN.search(claim_text)
                and harm_review.get("category") != "sensitive_private_fact"
            ):
                errors.append(
                    f"{claim_id}: sensitive private information must use the "
                    "sensitive_private_fact review category."
                )
            source_floor = harm_review.get("source_floor")
            legal_stage = harm_review.get("legal_stage")
            stage_pattern = LEGAL_STAGE_PATTERNS.get(legal_stage)
            evidence_by_source = {
                entry.get("source_id"): _text(
                    entry.get("extract_or_location")
                )
                for entry in source_evidence
                if isinstance(entry, dict) and entry.get("source_id")
            }
            supporting_harm_sources = {
                source_id
                for source_id, evidence_text in evidence_by_source.items()
                if (
                    legal_stage == "nonlegal"
                    and (
                        HUMAN_HARM_PATTERN.search(evidence_text)
                        or SENSITIVE_PRIVATE_PATTERN.search(evidence_text)
                    )
                )
                or (
                    stage_pattern is not None
                    and _has_affirmative_match(
                        stage_pattern.pattern, evidence_text
                    )
                )
            }
            if source_floor == "met":
                harm_families = {
                    family_of[source_id]
                    for source_id in supporting_harm_sources
                    if source_id in family_of
                }
                if len(harm_families) < 2:
                    errors.append(
                        f"{claim_id}: protected-person harm claim needs two "
                        "independent source families."
                    )
                accountable_ids = harm_review.get(
                    "accountable_source_ids", []
                )
                accountable_ids = (
                    accountable_ids
                    if isinstance(accountable_ids, list)
                    else []
                )
                accountable = [
                    source_id
                    for source_id in accountable_ids
                    if source_id in supporting_harm_sources
                    and sources_by_id.get(source_id, {}).get(
                        "accountability_basis"
                    )
                    in {
                        "court_or_regulator_record",
                        "named_source_investigation",
                        "subject_admission",
                    }
                ]
                if not accountable:
                    errors.append(
                        f"{claim_id}: protected-person harm claim needs an "
                        "accountable source: a court/regulator record, named-"
                        "source investigation, or subject admission."
                    )
            elif source_floor == "single_source_limited":
                triangulation = claim.get("triangulation")
                triangulation_status = (
                    triangulation.get("status")
                    if isinstance(triangulation, dict)
                    else None
                )
                limitation = _text(
                    harm_review.get("sourcing_limitation_excerpt")
                )
                if (
                    claim.get("kind") != "reported_claim"
                    or claim.get("importance") == "key"
                    or claim.get("confidence") != "low"
                    or triangulation_status != "limited"
                    or not limitation
                    or limitation.casefold() not in claim_text.casefold()
                ):
                    errors.append(
                        f"{claim_id}: single-source harm must be a low-"
                        "confidence, non-key reported claim with limited "
                        "triangulation and an in-sentence sourcing limitation."
                    )
                dependent_key_claims = [
                    other_id
                    for other_id, other_claim in claims_by_id.items()
                    if other_id != claim_id
                    and other_claim.get("importance") == "key"
                    and other_claim.get("include_in_report") is True
                    and support_reaches(other_id, claim_id)
                ]
                if dependent_key_claims:
                    errors.append(
                        f"{claim_id}: single-source harm cannot support a key "
                        "report claim: "
                        + ", ".join(sorted(dependent_key_claims))
                        + "."
                    )
            attribution = _text(harm_review.get("attributed_to"))
            if not attribution or attribution.casefold() not in claim_text.casefold():
                errors.append(
                    f"{claim_id}: protected-person harm must be attributed "
                    "in the claim text."
                )
            detected_claim_stages = {
                stage
                for stage, pattern in LEGAL_STAGE_PATTERNS.items()
                if _has_affirmative_match(pattern.pattern, claim_text)
            }
            evidence_text = " ".join(
                _text(entry.get("extract_or_location"))
                for entry in source_evidence
                if isinstance(entry, dict)
            )
            detected_evidence_stages = {
                stage
                for stage, pattern in LEGAL_STAGE_PATTERNS.items()
                if _has_affirmative_match(pattern.pattern, evidence_text)
            }
            if legal_stage == "nonlegal" and (
                detected_claim_stages or detected_evidence_stages
            ):
                errors.append(
                    f"{claim_id}: a legal allegation or outcome cannot be "
                    "classified as nonlegal."
                )
            elif legal_stage != "nonlegal":
                if (
                    not detected_claim_stages
                    or legal_stage not in detected_claim_stages
                ):
                    errors.append(
                        f"{claim_id}: human-harm legal stage {legal_stage!r} "
                        "is not stated consistently in the claim text."
                    )
                if stage_pattern is None or not _has_affirmative_match(
                    stage_pattern.pattern, evidence_text
                ):
                    errors.append(
                        f"{claim_id}: source evidence does not establish the "
                        f"declared legal stage {legal_stage!r}."
                    )

            resolution_status = harm_review.get("resolution_status")
            resolution_ids = harm_review.get("resolution_claim_ids", [])
            resolution_ids = (
                resolution_ids if isinstance(resolution_ids, list) else []
            )
            if (
                resolution_status == "not_applicable"
                and legal_stage != "nonlegal"
            ):
                errors.append(
                    f"{claim_id}: a legal allegation or outcome cannot mark "
                    "resolution as not_applicable."
                )
            if resolution_status == "resolved":
                known_resolution_ids = [
                    resolution_id
                    for resolution_id in resolution_ids
                    if resolution_id in claims_by_id
                ]
                if (
                    not resolution_ids
                    or len(known_resolution_ids) != len(resolution_ids)
                ):
                    errors.append(
                        f"{claim_id}: resolved harm needs known resolution "
                        "claim IDs."
                    )
                for resolution_id in known_resolution_ids:
                    resolution_claim = claims_by_id[resolution_id]
                    if (
                        resolution_claim.get("person_claim_role")
                        != "resolution"
                        or claim_id
                        not in (
                            resolution_claim.get("resolves_claim_ids") or []
                        )
                        or not set(
                            resolution_claim.get("person_ids", [])
                        ).intersection(person_links)
                    ):
                        errors.append(
                            f"{claim_id}: resolution claim {resolution_id} "
                            "must reciprocally resolve this claim for the "
                            "same protected person."
                        )
                if claim.get("include_in_report") is True:
                    harm_excerpts = {
                        _text(excerpt)
                        for excerpt in claim.get("report_excerpts", [])
                        if _text(excerpt)
                    }
                    resolution_excerpts = {
                        _text(excerpt)
                        for resolution_id in known_resolution_ids
                        for excerpt in claims_by_id[resolution_id].get(
                            "report_excerpts", []
                        )
                        if _text(excerpt)
                    }
                    if not harm_excerpts.intersection(resolution_excerpts):
                        errors.append(
                            f"{claim_id}: a known resolution must appear in "
                            "the same report excerpt as the harmful claim."
                        )
            elif resolution_status == "unresolved":
                reversal_stages = {
                    "acquitted",
                    "overturned",
                    "expunged",
                    "retracted",
                }
                evidenced_reversals = detected_evidence_stages.intersection(
                    reversal_stages
                )
                if evidenced_reversals:
                    errors.append(
                        f"{claim_id}: unresolved harm conflicts with evidence "
                        "of a reversal: "
                        + ", ".join(sorted(evidenced_reversals))
                        + "."
                    )
                search = harm_review.get("resolution_search")
                search_day = _as_date(
                    search.get("searched_at")
                    if isinstance(search, dict)
                    else None
                )
                if (
                    not isinstance(search, dict)
                    or not search.get("queries")
                    or not search.get("expected_locations")
                    or search_day is None
                    or (
                        report_day
                        and (
                            search_day > report_day
                            or (report_day - search_day).days
                            > FRESHNESS_WINDOW_DAYS
                        )
                    )
                ):
                    errors.append(
                        f"{claim_id}: unresolved harm needs a fresh bounded "
                        "resolution search."
                    )
            right_of_reply = harm_review.get("right_of_reply")
            if not isinstance(right_of_reply, dict):
                errors.append(
                    f"{claim_id}: protected-person harm claim needs a "
                    "documented right of reply."
                )
            else:
                response_status = right_of_reply.get("status")
                response_ids = right_of_reply.get("response_claim_ids", [])
                response_ids = (
                    response_ids if isinstance(response_ids, list) else []
                )
                if response_status in {"documented", "declined"}:
                    if not response_ids or any(
                        response_id not in claim_set
                        for response_id in response_ids
                    ):
                        errors.append(
                            f"{claim_id}: documented or declined right of "
                            "reply needs known response claim IDs."
                        )
                    elif any(
                        not set(
                            claims_by_id[response_id].get("person_ids", [])
                        ).intersection(person_links)
                        for response_id in response_ids
                    ):
                        errors.append(
                            f"{claim_id}: right-of-reply claims must refer to "
                            "the same protected person."
                        )
                    for response_id in [
                        item for item in response_ids if item in claims_by_id
                    ]:
                        response_claim = claims_by_id[response_id]
                        if (
                            response_claim.get("person_claim_role")
                            != "response"
                            or claim_id
                            not in (
                                response_claim.get("responds_to_claim_ids")
                                or []
                            )
                        ):
                            errors.append(
                                f"{claim_id}: right-of-reply claim "
                                f"{response_id} must reciprocally respond to "
                                "this harmful claim."
                            )
                        response_sources = response_claim.get("source_ids", [])
                        if not any(
                            sources_by_id.get(source_id, {}).get(
                                "accountability_basis"
                            )
                            == "subject_admission"
                            for source_id in response_sources
                        ):
                            errors.append(
                                f"{claim_id}: right-of-reply claim "
                                f"{response_id} needs subject-origin evidence."
                            )
                        if claim.get("include_in_report") is True:
                            harm_excerpts = {
                                _text(excerpt)
                                for excerpt in claim.get(
                                    "report_excerpts", []
                                )
                                if _text(excerpt)
                            }
                            response_excerpts = {
                                _text(excerpt)
                                for excerpt in response_claim.get(
                                    "report_excerpts", []
                                )
                                if _text(excerpt)
                            }
                            if not harm_excerpts.intersection(
                                response_excerpts
                            ):
                                errors.append(
                                    f"{claim_id}: documented response must "
                                    "appear in the same report excerpt as "
                                    "the harmful claim."
                                )
                elif response_status == "no_public_response":
                    search = right_of_reply.get("search_record")
                    search_day = _as_date(
                        search.get("searched_at")
                        if isinstance(search, dict)
                        else None
                    )
                    if (
                        not isinstance(search, dict)
                        or not search.get("queries")
                        or not search.get("expected_locations")
                        or search_day is None
                        or (
                            report_day
                            and (
                                search_day > report_day
                                or (
                                    report_day - search_day
                                ).days > FRESHNESS_WINDOW_DAYS
                            )
                        )
                    ):
                        errors.append(
                            f"{claim_id}: no-public-response finding needs "
                            "a fresh bounded response search."
                        )
                elif response_status == "not_applicable" and not (
                    harm_review.get("category") == "sensitive_private_fact"
                    and harm_review.get("privacy_basis") == "self_disclosed"
                ):
                    errors.append(
                        f"{claim_id}: right of reply cannot be not_applicable "
                        "for a protected-person harm claim."
                    )
            if harm_review.get("category") == "sensitive_private_fact":
                privacy_basis = harm_review.get("privacy_basis")
                privacy_ids = harm_review.get(
                    "privacy_basis_source_ids", []
                )
                privacy_ids = (
                    privacy_ids if isinstance(privacy_ids, list) else []
                )
                relevance = _text(
                    harm_review.get("governing_question_relevance")
                )
                valid_privacy_source = any(
                    source_id in source_links
                    and (
                        (
                            privacy_basis == "self_disclosed"
                            and "subject_official"
                            in sources_by_id.get(source_id, {}).get("roles", [])
                        )
                        or (
                            privacy_basis == "court_or_regulator_record"
                            and sources_by_id.get(source_id, {}).get(
                                "accountability_basis"
                            )
                            == "court_or_regulator_record"
                        )
                    )
                    for source_id in privacy_ids
                )
                if (
                    privacy_basis
                    not in {"self_disclosed", "court_or_regulator_record"}
                    or not valid_privacy_source
                    or len(relevance) < 40
                ):
                    errors.append(
                        f"{claim_id}: sensitive private information needs "
                        "self-disclosure or a court/regulator record plus a "
                        "specific governing-question justification."
                    )
        for relation in ("supports", "contradicts"):
            related_claims = claim.get(relation, [])
            if not isinstance(related_claims, list):
                continue
            for related_id in related_claims:
                if related_id == claim_id:
                    errors.append(f"{claim_id} has a circular {relation} reference.")
                if related_id not in claim_set:
                    errors.append(f"{claim_id} references unknown claim {related_id}.")
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
                errors.append(f"{claim_id} is disputed but has no resolution.")
            if not claim.get("contradicts"):
                errors.append(
                    f"{claim_id} is disputed but has no contradicting claim."
                )

        foundations = foundation_source_ids(claim_id)
        direct_foundations = direct_source_ids(claim_id)
        errors.extend(derived_assertion_errors(claim))
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
            evidence_coverage_errors(claim, ledger_dates, inherited)
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
                    f"{claim_id}: an estimate must record its assumptions; "
                    "state the inputs and the arithmetic that produced it."
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
                    f"{claim_id}: time-sensitive claim is dated "
                    f"{(report_day - claim_day).days} days before the report date."
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
                        f"{source_id}: source for time-sensitive {claim_id} is "
                        "not published inside the freshness window and its "
                        "undated_reason does not state that the page is "
                        "continuously updated."
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
                    f"{claim_id} declares triangulation met but has "
                    f"{len(families)} normalized source family."
                )
            if triangulation_status == "met" and not any(
                sources_by_id[source_id].get("provenance")
                in independent_provenance
                for source_id in foundation_source_ids(claim_id)
                if source_id in sources_by_id
            ):
                errors.append(
                    f"{claim_id} declares triangulation met but has "
                    "no independent source."
                )
            if triangulation_status == "limited":
                if claim.get("confidence") == "high":
                    errors.append(
                        f"{claim_id}: high-confidence key judgment cannot "
                        "use limited triangulation."
                    )
                if not str(claim.get("limitations") or "").strip():
                    errors.append(
                        f"{claim_id} has limited triangulation but no limitation."
                    )
            if triangulation_status == "not_applicable":
                errors.append(
                    f"{claim_id} is a key analysis; triangulation cannot be "
                    "not applicable."
                )

        if claim.get("importance") == "key":
            # Judged on the claim's own sources when it has any: a supporting
            # claim's independent source does not launder a key claim that
            # cites only the subject.
            judged = direct_foundations or foundations
            if not judged:
                errors.append(
                    f"{claim_id}: key claim has no direct source and no "
                    "first-level supporting claim with one."
                )
            elif all(
                sources_by_id[source_id].get("provenance")
                in interested_provenance
                for source_id in judged
            ):
                errors.append(
                    f"{claim_id}: key claim rests only on interested sources "
                    f"({', '.join(sorted(judged))}); add independent "
                    "evidence or record the area as a gap."
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
            "Analysis has circular support: "
            f"{' -> '.join(path)}. supports must point strictly downward to "
            "the evidence a claim rests on."
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
                errors.append(f"Synthesis references unknown central judgment {claim_id}.")
            elif (
                claim.get("importance") != "key"
                or claim.get("include_in_report") is not True
            ):
                errors.append(
                    f"Central judgment {claim_id} must be an included key claim."
                )
        for claim_id, claim in claims_by_id.items():
            if (
                claim.get("importance") == "key"
                and claim.get("include_in_report") is True
                and claim_id not in central
            ):
                errors.append(
                    f"Key report claim {claim_id} is missing from the central synthesis."
                )
        for claim_id in counterevidence:
            if claim_id not in claim_set:
                errors.append(
                    f"Synthesis references unknown counterevidence {claim_id}."
                )
        adversarial_claims = set()
        adversarial_tests = synthesis.get("adversarial_tests", [])
        if not isinstance(adversarial_tests, list):
            adversarial_tests = []
        for test in adversarial_tests:
            if not isinstance(test, dict):
                continue
            for claim_id in test.get("claim_ids", []):
                adversarial_claims.add(claim_id)
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown adversarial-test claim {claim_id}."
                    )
        for claim_id in counterevidence:
            if claim_id in claim_set and claim_id not in adversarial_claims:
                errors.append(
                    f"Counterevidence {claim_id} is not tested by an "
                    "adversarial hypothesis."
                )

        for implication in synthesis.get("implications", []):
            if not isinstance(implication, dict):
                continue
            implication_claims = implication.get("claim_ids", [])
            for claim_id in implication_claims:
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown implication claim {claim_id}."
                    )
            if not set(implication_claims).intersection(central):
                errors.append(
                    "Implication is not linked to a central judgment."
                )
        for takeaway in synthesis.get("decisions_or_takeaways", []):
            if not isinstance(takeaway, dict):
                continue
            rationale_claims = takeaway.get("rationale_claim_ids", [])
            for claim_id in rationale_claims:
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown takeaway rationale {claim_id}."
                    )
            if not set(rationale_claims).intersection(central):
                errors.append(
                    "Takeaway is not linked to a central judgment."
                )
        for scenario in synthesis.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            scenario_claims = scenario.get("claim_ids", [])
            for claim_id in scenario_claims:
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown scenario claim {claim_id}."
                    )
            if not set(scenario_claims).intersection(central):
                errors.append(
                    "Scenario is not linked to a central judgment."
                )

        high_priority_claims = {
            claim_id
            for item in coverage
            if isinstance(item, dict) and item.get("priority") == "high"
            for claim_id in item.get("claim_ids", [])
        }
        for claim_id in central:
            if claim_id in claim_set and claim_id not in high_priority_claims:
                errors.append(
                    f"Central judgment {claim_id} is not covered by a "
                    "high-priority research area."
                )
    return errors


def validate_schema(data, schema):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError:
        return [
            "Ledger validation needs jsonschema. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
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
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    errors = validate_schema(data, schema) + validate_references(data)
    return emit_findings(
        errors,
        ok_message=f"[OK] Evidence ledger validated: {args.ledger}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
