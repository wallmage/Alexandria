#!/usr/bin/env python3
"""Deterministic structural checks for Alexandria Markdown and PDF reports."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from .artifact_safety import validated_artifact_path
    from .gate_severity import emit_findings, hard_errors, warning
    from .report_blocks import mask_fenced_code as _mask_fenced_code
    from .report_blocks import report_length
    from .report_contract import detect_language, localized_date, report_length_policy
    from .source_fidelity import (
        _registrable_domain,
        validate_source_fidelity_receipt_online,
    )
except ImportError:
    from artifact_safety import validated_artifact_path
    from gate_severity import emit_findings, hard_errors, warning
    from report_blocks import mask_fenced_code as _mask_fenced_code
    from report_blocks import report_length
    from report_contract import detect_language, localized_date, report_length_policy
    from source_fidelity import (
        _registrable_domain,
        validate_source_fidelity_receipt_online,
    )

try:
    from .gate_severity import Finding
except (ImportError, AttributeError):
    try:
        from gate_severity import Finding
    except (ImportError, AttributeError):
        Finding = None
if Finding is None:
    @dataclass
    class Finding:
        family: str
        severity: str
        klass: str
        ids: list
        message: str
        fix: str
        remove: str = ""

SOURCE_HEADINGS = {
    "sources",
    "references",
    "来源",
    "資料來源",
    "参考资料",
    "參考資料",
}
#: An H2 names the Sources section when its casefolded text, stripped of spaces
#: and punctuation, starts or ends with one of these (`## 资料来源`,
#: `## References and sources`, `## 六、参考文献` all count; a body section
#: such as `## 文献回顾` or `## Cross-references` does not).
SOURCE_HEADING_TOKENS = (
    "sources",
    "references",
    "bibliography",
    "workscited",
    "来源",
    "來源",
    "参考资料",
    "參考資料",
    "参考文献",
    "參考文獻",
)


def is_sources_heading(heading):
    """True when this H2 heading names the report's Sources section."""
    folded = re.sub(r"[\W_]+", "", str(heading).casefold())
    return any(
        folded.startswith(token) or folded.endswith(token)
        for token in SOURCE_HEADING_TOKENS
    )


LANG_CHOICES = ("en", "zh-CN", "zh-HK")
FAMILIES = (
    "integrity/control-chars",
    "integrity/replacement-char",
    "integrity/structure",
    "integrity/date-line",
    "integrity/length",
    "integrity/quotation-lost",
    "binding/link-not-in-ledger",
    "binding/claim-paragraph",
    "binding/sources-section",
)
_QUOTE_SPAN_RE = re.compile(
    r"「[^」]{4,}」|『[^』]{4,}』|[“][^”]{4,}[”]|[‘][^’]{4,}[’]|\"[^\"\n]*\""
)
ROOT = Path(__file__).resolve().parents[1]
S2T_CHARACTER_MAP = (
    ROOT / "references" / "rewild" / "opencc" / "STCharacters.txt"
)
REWILD_PROFILE_DIRS = {
    "en": "rewild",
    "zh-CN": "rewild-zh",
    "zh-HK": "rewild-hk",
}
_IDENTITY_ORG_SUFFIXES = frozenset(
    {
        "advisory",
        "association",
        "company",
        "corporation",
        "foundation",
        "group",
        "institute",
        "labs",
        "laboratory",
        "limited",
        "llc",
        "llp",
        "partners",
        "research",
        "studio",
        "systems",
        "team",
        "university",
    }
)


def _is_safe_identity_label(value):
    """Validate the narrow person/organization grammar used by cover metadata."""
    label = value.strip()
    if (
        not label
        or len(label) > 80
        or len(label.split()) > 8
        or re.search(r"""[\r\n<>[\]{}*_`~|:;!?。！？；]""", label)
    ):
        return False
    ascii_words = re.findall(r"[A-Za-z][A-Za-z0-9&'’.-]*", label)
    if ascii_words:
        connectors = {"and", "of", "the", "for", "de", "van", "von"}
        if any(
            word.casefold() not in connectors
            and not (word[0].isupper() or word.isupper())
            for word in ascii_words
        ):
            return False
        return (
            len(ascii_words) <= 2
            or ascii_words[-1].casefold() in _IDENTITY_ORG_SUFFIXES
        )
    return len(label) <= 12


def _h2_sections(text):
    """Return raw H2 titles with offsets.

    This deliberately keeps the verbatim heading text that
    ``report_blocks.h2_sections`` normalizes away: the section-review contract
    in content_gate.py and the Sources-placement rules below are keyed to the
    literal heading a user typed, so the two are not interchangeable.
    """
    masked = _mask_fenced_code(text)
    return [
        (match.group(1).strip(), match.start())
        for match in re.finditer(r"^##\s+(.+?)\s*$", masked, re.MULTILINE)
    ]


def _mask_nonlink_regions(text):
    masked = _mask_fenced_code(text)
    masked = re.sub(
        r"<!--.*?-->",
        lambda match: " " * len(match.group(0)),
        masked,
        flags=re.DOTALL,
    )
    masked = re.sub(
        r"(?P<ticks>`+).*?(?P=ticks)",
        lambda match: " " * len(match.group(0)),
        masked,
        flags=re.DOTALL,
    )
    return masked


def _markdown_url_entries(text, *, include_images=False):
    """Return (URL, start, end) while skipping fenced code."""
    masked = _mask_nonlink_regions(text)
    entries = []
    for match in re.finditer(r"\]\(", masked):
        label_start = masked.rfind("[", 0, match.start())
        is_image = label_start > 0 and masked[label_start - 1] == "!"
        if is_image and not include_images:
            continue
        index = match.end()
        if index < len(masked) and masked[index] == "<":
            end = masked.find(">", index + 1)
            if end != -1:
                destination = text[index + 1 : end]
                if destination.startswith(("http://", "https://")):
                    entries.append((destination, index + 1, end))
            continue

        depth = 1
        escaped = False
        chars = []
        destination_start = index
        destination_end = index
        while index < len(masked):
            char = text[index]
            index += 1
            if escaped:
                chars.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
                chars.append(char)
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
                chars.append(char)
            elif char.isspace() and depth == 1:
                break
            else:
                chars.append(char)
            destination_end = index
        destination = "".join(chars).strip()
        if destination.startswith(("http://", "https://")):
            entries.append((destination, destination_start, destination_end))
    return entries


def extract_markdown_urls(text):
    return [entry[0] for entry in _markdown_url_entries(text)]


def find_raw_urls(text):
    """Find HTTP(S) URLs outside Markdown links and fenced code."""
    masked = list(_mask_nonlink_regions(text))
    for _, start, end in _markdown_url_entries(text, include_images=True):
        masked[start:end] = " " * (end - start)
    masked_text = "".join(masked)
    masked_text = re.sub(
        r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*<?https?://[^\s>]+>?"
        r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$",
        lambda match: " " * len(match.group(0)),
        masked_text,
    )
    return re.findall(r"https?://[^\s<>]+", masked_text)


@lru_cache(maxsize=1)
def _traditional_only_characters():
    """Load Traditional-only forms from Alexandria's vendored OpenCC map."""
    simplified = set()
    traditional = set()
    for line in S2T_CHARACTER_MAP.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        source, targets = line.split("\t", 1)
        simplified.update(source)
        for target in targets.split():
            traditional.update(target)
    return frozenset(traditional - simplified)


def _protected_script_hits(text, sections, traditional_only):
    """Count unique Traditional hits inside bounded verbatim candidates."""
    source_starts = [
        start
        for heading, start in sections
        if is_sources_heading(heading)
    ]
    if source_starts:
        text = text[: min(source_starts)]
    text = _mask_fenced_code(text)
    protected = bytearray(len(text))
    callout_ranges = []

    def mark(start, end):
        protected[start:end] = b"\x01" * (end - start)

    for block in re.finditer(
        r"(?m)(?:^\s{0,3}>[^\n]*(?:\n|$))+",
        text,
    ):
        lines = [
            re.sub(r"^\s{0,3}>\s?", "", line)
            for line in block.group(0).splitlines()
        ]
        first = next((line.strip() for line in lines if line.strip()), "")
        if re.fullmatch(r"\[!(?:METRIC|INSIGHT|TAKEAWAY)\]", first):
            callout_ranges.append(block.span())
            continue
        mark(*block.span())
    for match in re.finditer(
        r"「[^」]*」|『[^』]*』|“[^”]*”|‘[^’]*’",
        text,
        flags=re.DOTALL,
    ):
        mark(*match.span())
    for match in re.finditer(r"!?\[([^\]]*)\]\([^)]+\)", text):
        mark(*match.span(1))
    for start, end in callout_ranges:
        protected[start:end] = b"\x00" * (end - start)
    return sum(
        bool(protected[index]) and char in traditional_only
        for index, char in enumerate(text)
    )


def simplified_script_errors(text, *, sections=None):
    """Reject materially Traditional or mixed script in a zh-CN report body."""
    try:
        traditional_only = _traditional_only_characters()
    except (OSError, ValueError) as exc:
        return [f"Simplified-Chinese script map could not be loaded: {exc}"]
    protected_hits = 0
    if sections is not None:
        protected_hits = _protected_script_hits(
            text,
            sections,
            traditional_only,
        )
        text = _report_prose(text, sections)
    han_count = len(re.findall(r"[\u3400-\u9fff]", text))
    hits = Counter(char for char in text if char in traditional_only)
    total_hits = sum(hits.values())
    protected_hits = min(total_hits, protected_hits)
    protected_budget = max(100, han_count // 5)
    hit_count = total_hits - min(protected_hits, protected_budget)
    threshold = max(8, (han_count + 99) // 100)
    if hit_count < threshold:
        return []
    examples = "、".join(
        char for char, _ in hits.most_common(12)
    )
    return [
        "Report marked zh-CN contains "
        f"{hit_count} Traditional-only character(s) "
        f"(examples: {examples}); use Simplified Chinese consistently."
    ]


def _report_prose(text, sections):
    """Return report body prose without Sources, URLs, markup, or code.

    ``report_blocks.visible_report_prose`` is block-structured and keeps a
    different set of text: it drops only recognized bibliography blocks and
    re-joins normalized blocks, which changes both the word and character
    counts the length policy is defined against. The two are not equivalent, so
    this stays the counting surface.
    """
    source_starts = [
        start
        for heading, start in sections
        if is_sources_heading(heading)
    ]
    if source_starts:
        text = text[: min(source_starts)]
    text = _mask_fenced_code(text)
    text = re.sub(r"<pre\b.*?</pre>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"(?m)^(?: {4}|\t).*$", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<!--.*?-->|<[^>]+>", " ", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"[*_~>|]", " ", text)
    return text


def _finding(family, message, *, ids=None, severity="hard", fix="", remove="", klass=None):
    klass = klass or ("F" if severity == "hard" else "A")
    return Finding(
        family=family,
        severity=severity,
        klass=klass,
        ids=list(ids or []),
        message=message,
        fix=fix,
        remove=remove,
    )


def normalize_url(url):
    parts = urlsplit(str(url))
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


LINK_NOT_IN_LEDGER_FIX = (
    "cite the nearest ledger URL instead (alx check --fix rewrites it when "
    "only www. or the domain suffix differs); a page you did not fetch must "
    "be fetched first"
)


def _first_registrable_label(host):
    if not host:
        return ""
    domain = _registrable_domain(host)
    return domain.split(".")[0] if domain else ""


def same_page_variant(report_url, ledger_url):
    """True when only www. / public-suffix differs; path+query match; path has ≥2 segments."""
    report = urlsplit(normalize_url(report_url))
    ledger = urlsplit(normalize_url(ledger_url))
    if report.path != ledger.path or report.query != ledger.query:
        return False
    segments = [part for part in report.path.split("/") if part]
    if len(segments) < 2:
        return False
    report_label = _first_registrable_label(report.hostname)
    ledger_label = _first_registrable_label(ledger.hostname)
    return bool(report_label) and report_label == ledger_label


def same_page_ledger_source(report_url, ledger):
    """First matching source: (source['url'], source_id) or None.
    Compare report_url against each source url AND aliases; return the source's primary url + id.
    """
    if not isinstance(ledger, dict):
        return None
    sources = ledger.get("sources", [])
    if not isinstance(sources, list):
        return None
    for source in sources:
        if not isinstance(source, dict):
            continue
        candidates = [source.get("url"), *(source.get("aliases") or [])]
        if any(
            raw and same_page_variant(report_url, raw) for raw in candidates
        ):
            url = source.get("url")
            source_id = source.get("source_id")
            if url and source_id:
                return (url, source_id)
    return None


def _http_url(url):
    scheme = urlsplit(str(url)).scheme.lower()
    return scheme in {"http", "https"}


def _foundation_urls(claim, sources_by_id):
    urls = set()
    if not isinstance(claim, dict):
        return urls
    for source_id in claim.get("source_ids") or []:
        source = sources_by_id.get(source_id, {})
        if not isinstance(source, dict):
            continue
        for raw in [source.get("url"), *(source.get("aliases") or [])]:
            if raw:
                urls.add(normalize_url(raw))
    return urls


def _ledger_url_set(ledger):
    urls = set()
    for source in ledger.get("sources", []) if isinstance(ledger, dict) else []:
        if not isinstance(source, dict):
            continue
        for raw in [source.get("url"), *(source.get("aliases") or [])]:
            if raw:
                urls.add(normalize_url(raw))
    return urls


def _ledger_url_display(ledger):
    displayed = []
    for source in ledger.get("sources", []) if isinstance(ledger, dict) else []:
        if isinstance(source, dict) and source.get("url"):
            displayed.append(source["url"])
    return displayed


def _nearest_ledger_url(url, candidates):
    if not candidates:
        return ""
    return max(
        candidates,
        key=lambda candidate: SequenceMatcher(None, url, candidate).ratio(),
    )


def _body_and_sources(text):
    sections = _h2_sections(text)
    source_indexes = [
        index
        for index, (heading, _) in enumerate(sections)
        if is_sources_heading(heading)
    ]
    if not source_indexes:
        return text, "", sections, None
    source_index = source_indexes[-1]
    source_start = sections[source_index][1]
    return text[:source_start], text[source_start:], sections, source_index


#: A standfirst date line on its own block, in either locale form
#: (`report_contract.localized_date`).
_DATE_LINE_RE = re.compile(
    r"^(?:\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}\s+[A-Za-z]+\s+\d{4})$"
)


def split_body_paragraphs(text):
    """The one body-paragraph numbering of the system (spec §6.7c).

    1-based over body prose blocks. The H1, the standfirst blockquote, the
    date line, every other heading, fenced code, tables and the Sources
    section are not numbered, so `alx claim bind C5 --paragraph N`,
    validate_report and content_gate all mean the same N.
    """
    body, _source_text, _sections, _source_index = _body_and_sources(text)
    masked = _mask_fenced_code(body)
    spans = []
    cursor = 0
    for match in re.finditer(r"\n\s*\n", masked):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(masked)))
    numbered = []
    for start, end in spans:
        stripped = masked[start:end].strip()
        if not stripped:
            continue
        first = stripped.splitlines()[0].strip()
        if first.startswith(("#", ">", "|")):
            continue
        if _DATE_LINE_RE.match(stripped):
            continue
        numbered.append((len(numbered) + 1, body[start:end].strip()))
    return numbered


def _immediate_blockquote_lines(text):
    lines = []
    found_h1 = False
    collecting = False
    for line in _mask_fenced_code(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not found_h1:
            found_h1 = True
            continue
        if found_h1 and stripped.startswith(">"):
            collecting = True
            lines.append(stripped.lstrip(">").strip())
            continue
        if collecting and stripped:
            break
        if found_h1 and stripped and not collecting:
            break
    return found_h1, lines


def _quoted_spans(text):
    # ASCII quotes pair sequentially (open == close), so length is filtered
    # after the match instead of inside the branch: a short term would
    # otherwise desynchronize the scanner onto its closing quote.
    return [
        span
        for span in _QUOTE_SPAN_RE.findall(text or "")
        if not span.startswith('"') or len(span) - 2 >= 4
    ]


def _bound_claim_source_urls(ledger, sources_by_id):
    """A bound claim cites its own sources even without a link in the body."""
    urls = set()
    claims = ledger.get("claims")
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or claim.get("include_in_report") is not True:
            continue
        if claim.get("report_paragraph") is None and not claim.get("report_excerpts"):
            continue
        for source_id in claim.get("source_ids") or []:
            source = sources_by_id.get(source_id) or {}
            if isinstance(source, dict) and source.get("url"):
                urls.add(normalize_url(source["url"]))
    return urls


def binding_findings(text, ledger):
    """Link membership, claim→paragraph mapping, Sources section (spec §6.7c)."""
    findings = []
    if not isinstance(ledger, dict):
        return [
            _finding(
                "binding/link-not-in-ledger",
                "Evidence ledger root must be an object.",
            )
        ]
    allowed = _ledger_url_set(ledger)
    displayed = _ledger_url_display(ledger)
    body, source_text, sections, source_index = _body_and_sources(text)
    for url in sorted(set(extract_markdown_urls(text))):
        if not _http_url(url):
            continue
        if normalize_url(url) in allowed:
            continue
        nearest = _nearest_ledger_url(url, displayed)
        message = f"Report URL is not present in the ledger: {url}"
        if nearest:
            message += f"; nearest ledger URL: {nearest}"
        findings.append(
            _finding(
                "binding/link-not-in-ledger",
                message,
                fix=LINK_NOT_IN_LEDGER_FIX,
            )
        )

    paragraphs = split_body_paragraphs(text)
    sources_by_id = {
        source.get("source_id"): source
        for source in ledger.get("sources", [])
        if isinstance(source, dict) and source.get("source_id")
    }
    for claim in ledger.get("claims", []) if isinstance(ledger.get("claims"), list) else []:
        if not isinstance(claim, dict) or claim.get("include_in_report") is not True:
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        bound = claim.get("report_paragraph")
        if bound is not None:
            try:
                index = int(bound)
            except (TypeError, ValueError):
                index = None
            if index is None or index < 1 or index > len(paragraphs):
                findings.append(
                    _finding(
                        "binding/claim-paragraph",
                        f"Claim {claim_id} report_paragraph {bound} is out of range.",
                        severity="warn",
                        ids=[claim_id],
                        fix=f"run `alx claim bind {claim_id} --paragraph N`",
                        remove=f"alx claim drop {claim_id} --apply",
                    )
                )
            continue
        foundation_urls = _foundation_urls(claim, sources_by_id)
        candidates = []
        for index, paragraph in paragraphs:
            paragraph_urls = {normalize_url(url) for url in extract_markdown_urls(paragraph)}
            if foundation_urls & paragraph_urls:
                candidates.append(index)
        if len(candidates) != 1:
            listed = ", ".join(str(item) for item in candidates) or "none"
            findings.append(
                _finding(
                    "binding/claim-paragraph",
                    f"ambiguous: run `alx claim bind {claim_id} --paragraph N`; candidates: {listed}",
                    severity="warn",
                    ids=[claim_id],
                    fix=f"run `alx claim bind {claim_id} --paragraph N`",
                    remove=f"alx claim drop {claim_id} --apply",
                )
            )

    if source_index is None:
        findings.append(
            _finding(
                "binding/sources-section",
                "Sources H2 must be last and equal the cited-source list.",
                severity="warn",
                fix="run `alx check --fix`",
            )
        )
    else:
        if source_index != len(sections) - 1:
            findings.append(
                _finding(
                    "binding/sources-section",
                    "Sources must be the last H2 section.",
                    severity="warn",
                    fix="run `alx check --fix`",
                )
            )
        cited = {normalize_url(url) for url in extract_markdown_urls(body)}
        cited |= _bound_claim_source_urls(ledger, sources_by_id)
        listed = {normalize_url(url) for url in extract_markdown_urls(source_text)}
        if cited != listed:
            findings.append(
                _finding(
                    "binding/sources-section",
                    "Sources section must equal the cited-source list.",
                    severity="warn",
                    fix="run `alx check --fix`",
                )
            )
    return findings


def integrity_findings(text, ledger, *, snapshot_text=None, lang):
    """Integrity checks from spec §6.7(a)."""
    findings = []
    if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
        findings.append(
            _finding(
                "integrity/control-chars",
                "Report contains C0 control characters.",
                fix="remove control characters",
            )
        )
    if "\ufffd" in text:
        findings.append(
            _finding(
                "integrity/replacement-char",
                "Report contains U+FFFD replacement characters.",
                fix="re-decode the report as UTF-8",
            )
        )
    has_h1, blockquote_lines = _immediate_blockquote_lines(text)
    if not has_h1:
        findings.append(
            _finding(
                "integrity/structure",
                "Report needs one H1 title.",
                severity="warn",
                fix="add an H1 title",
            )
        )
    if not blockquote_lines:
        findings.append(
            _finding(
                "integrity/structure",
                "Report needs a standfirst blockquote immediately under the H1.",
                severity="warn",
                fix="add the standfirst blockquote under the H1",
            )
        )
    expected_date = None
    ledger_value = ledger.get("report_date") if isinstance(ledger, dict) else None
    try:
        ledger_day = (
            date.fromisoformat(ledger_value)
            if isinstance(ledger_value, str)
            else None
        )
        if ledger_day is not None and lang:
            expected_date = localized_date(lang, ledger_day)
    except ValueError:
        expected_date = None
    if blockquote_lines and expected_date and expected_date not in blockquote_lines:
        findings.append(
            _finding(
                "integrity/date-line",
                "Date line must use the strict locale format and sit in the "
                f"immediate blockquote under the H1: {expected_date}.",
                severity="warn",
                fix="put the locale date on the immediate blockquote under the H1",
            )
        )
    if lang:
        try:
            minimum, maximum, _unit = report_length_policy(lang)
        except ValueError:
            minimum = None
        if minimum is not None:
            # R12: one length definition for every consumer (report_blocks).
            actual, label = report_length(text, lang)
            if actual < minimum or actual > maximum:
                findings.append(
                    _finding(
                        "integrity/length",
                        f"Report has {actual} {label}; threshold is {minimum}–{maximum} {label}.",
                        fix="expand or cut the report body to the length floor/ceiling",
                        severity="warn",
                    )
                )
    if snapshot_text:
        # R28 splits this family: a span still in the report but rewritten is
        # evidence tampering (HARD); a span the edit cut out is not (WARN).
        report_spans = _quoted_spans(text)
        missing = [
            span for span in _quoted_spans(snapshot_text) if span not in text
        ]
        for span in missing[:5]:
            altered = any(
                SequenceMatcher(None, span, candidate).ratio() >= 0.6
                for candidate in report_spans
            )
            findings.append(
                _finding(
                    "integrity/quotation-lost",
                    (
                        f"Quoted span altered in the report: {span}"
                        if altered
                        else f"Quoted span removed from the report: {span}"
                    ),
                    severity="hard" if altered else "warn",
                    fix="alx snapshot --restore",
                    remove="alx snapshot --restore" if altered else "",
                )
            )
    return findings


def validate_markdown(
    text,
    *,
    min_words=0,
    max_words=0,
    min_chars=0,
    max_chars=0,
    min_sources=1,
    min_sections=1,
    expected_lang=None,
):
    """Return actionable errors for a report Markdown string."""
    if not text.strip():
        return ["Report is empty."]

    errors = []
    if not re.search(r"^#\s+\S", _mask_fenced_code(text), re.MULTILINE):
        errors.append("Report needs one H1 title.")
    sections = _h2_sections(text)
    prose = _report_prose(text, sections)
    if expected_lang:
        detected = detect_language(prose)
        chinese_ambiguous = detected == "zh" and expected_lang.startswith("zh-")
        if detected != expected_lang and not chinese_ambiguous:
            errors.append(
                f"Report language is {detected}; expected {expected_lang}."
            )
        if expected_lang == "zh-CN":
            errors.extend(simplified_script_errors(text, sections=sections))
    words = re.findall(r"\b[\w'-]+\b", prose, re.UNICODE)
    if len(words) < min_words:
        errors.append(f"Report has {len(words)} words; minimum is {min_words}.")
    if max_words and len(words) > max_words:
        errors.append(f"Report has {len(words)} words; maximum is {max_words}.")
    characters = len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", prose))
    if characters < min_chars:
        errors.append(
            f"Report has {characters} non-whitespace characters; minimum is {min_chars}."
        )
    if max_chars and characters > max_chars:
        errors.append(
            f"Report has {characters} non-whitespace characters; maximum is {max_chars}."
        )

    if len(sections) < min_sections:
        errors.append(
            f"Report has {len(sections)} H2 sections; minimum is {min_sections}."
        )

    source_indexes = [
        index
        for index, (heading, _) in enumerate(sections)
        if is_sources_heading(heading)
    ]
    if not source_indexes:
        errors.append("Report needs a final H2 Sources section.")
    else:
        source_index = source_indexes[-1]
        if source_index != len(sections) - 1:
            errors.append("Sources must be the final H2 section.")
        source_start = sections[source_index][1]
        source_text = text[source_start:]
        links = extract_markdown_urls(source_text)
        if len(links) < min_sources:
            errors.append(
                f"Sources section has {len(links)} Markdown links; "
                f"minimum is {min_sources}. Use [source title](URL)."
            )
        if find_raw_urls(source_text):
            errors.append("Sources must use Markdown links, not raw URLs.")

    return errors


def validate_report_against_ledger(text, ledger):
    """Check that report links and claim locations exist in the ledger.

    R28: only the link-membership check is HARD (`binding/link-not-in-ledger`);
    excerpt placement, nearby citation and Sources listing are WARN.
    """
    if not isinstance(ledger, dict):
        return ["Evidence ledger root must be an object."]
    sources = ledger.get("sources", [])
    claims = ledger.get("claims", [])
    if not isinstance(sources, list) or not isinstance(claims, list):
        return ["Evidence ledger sources and claims must be arrays."]

    source_urls = {
        source.get("source_id"): source.get("url")
        for source in sources
        if isinstance(source, dict)
        and source.get("source_id")
        and source.get("url")
    }
    claims_by_id = {
        claim.get("claim_id"): claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    }

    def foundation_source_ids(claim_id, visited=None):
        visited = set() if visited is None else set(visited)
        if claim_id in visited:
            return set()
        visited.add(claim_id)
        claim = claims_by_id.get(claim_id, {})
        source_ids = claim.get("source_ids", [])
        foundations = set(source_ids) if isinstance(source_ids, list) else set()
        supports = claim.get("supports", [])
        if isinstance(supports, list):
            for related_id in supports:
                foundations.update(foundation_source_ids(related_id, visited))
        return foundations

    errors = []
    sections = _h2_sections(text)
    body = text
    source_starts = [
        start
        for heading, start in sections
        if is_sources_heading(heading)
    ]
    if source_starts:
        body = body[: min(source_starts)]
    source_section_urls = set(
        extract_markdown_urls(text[min(source_starts) :])
        if source_starts
        else []
    )
    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", body)
        if paragraph.strip()
    ]
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("include_in_report") is not True:
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        excerpts = claim.get("report_excerpts", [])
        if not isinstance(excerpts, list) or not excerpts:
            continue
        for excerpt in excerpts:
            normalized = re.sub(r"\s+", " ", str(excerpt)).strip()
            matching_paragraphs = [
                paragraph
                for paragraph in paragraphs
                if normalized
                in re.sub(
                    r"\s+", " ", _report_prose(paragraph, [])
                ).strip()
            ]
            if not matching_paragraphs:
                errors.append(
                    warning(
                        f"Claim {claim_id} cannot be located in the report: "
                        f"{normalized}"
                    )
                )
                continue
            expected_source_ids = foundation_source_ids(claim_id)
            expected_urls = {
                source_urls[source_id]
                for source_id in expected_source_ids
                if source_id in source_urls
            }
            if expected_urls and not any(
                expected_urls.intersection(extract_markdown_urls(paragraph))
                for paragraph in matching_paragraphs
            ):
                errors.append(
                    warning(
                        f"Claim {claim_id} has no nearby citation to its ledger source."
                    )
                )
            for url in sorted(expected_urls - source_section_urls):
                errors.append(
                    warning(
                        f"Claim {claim_id} source is missing from the final "
                        f"Sources section: {url}"
                    )
                )
    return errors


class _PdfErrors(list):
    text_chars = 0


def validate_pdf(
    path,
    *,
    min_pages=1,
    min_text_chars=1,
    min_links=0,
    expected_lang=None,
):
    """Return errors after reopening and extracting text from a rendered PDF."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        errors = _PdfErrors(
            [
                "PDF validation needs pypdf. Install dependencies with "
                "'python3 -m pip install -r requirements.txt'."
            ]
        )
        errors.text_chars = 0
        return errors

    try:
        reader = PdfReader(path)
        page_count = len(reader.pages)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        metadata = reader.metadata or {}
        root = reader.root_object
        page_sizes = [
            (float(page.mediabox.width), float(page.mediabox.height))
            for page in reader.pages
        ]
        link_count = 0
        for page in reader.pages:
            for annotation_ref in page.get("/Annots", []):
                annotation = annotation_ref.get_object()
                action = annotation.get("/A", {})
                if annotation.get("/Subtype") == "/Link" and action.get("/URI"):
                    link_count += 1
    except Exception as exc:  # pypdf exposes several backend-specific errors
        errors = _PdfErrors([f"PDF could not be reopened: {exc}"])
        errors.text_chars = 0
        return errors

    errors = _PdfErrors()
    errors.text_chars = len(text.strip())
    if page_count < min_pages:
        errors.append(f"PDF has {page_count} pages; minimum is {min_pages}.")
    if len(text.strip()) < min_text_chars:
        errors.append(
            f"PDF has {len(text.strip())} extracted text characters; "
            f"minimum is {min_text_chars}."
        )
    if link_count < min_links:
        errors.append(
            f"PDF has {link_count} external clickable links; minimum is {min_links}."
        )
    if not str(metadata.get("/Title") or "").strip():
        errors.append("PDF is missing title metadata.")
    if not str(metadata.get("/Author") or "").strip():
        errors.append("PDF is missing author metadata.")
    mark_info = root.get("/MarkInfo", {})
    if hasattr(mark_info, "get_object"):
        mark_info = mark_info.get_object()
    if not mark_info.get("/Marked") or "/StructTreeRoot" not in root:
        errors.append("PDF is not tagged for assistive technology.")
    pdf_lang = str(root.get("/Lang") or "").strip()
    if not pdf_lang:
        errors.append("PDF is missing its document language.")
    elif expected_lang and pdf_lang.casefold() != expected_lang.casefold():
        errors.append(
            f"PDF language is {pdf_lang}; expected {expected_lang}."
        )
    a4_width, a4_height = 595.28, 841.89
    for index, (width, height) in enumerate(page_sizes, start=1):
        if abs(width - a4_width) > 2 or abs(height - a4_height) > 2:
            errors.append(
                f"PDF page {index} is not A4: {width:.2f}x{height:.2f} pt."
            )
    if page_sizes and any(
        abs(width - page_sizes[0][0]) > 0.1
        or abs(height - page_sizes[0][1]) > 0.1
        for width, height in page_sizes[1:]
    ):
        errors.append("PDF page sizes are inconsistent.")
    if "/Outlines" not in root:
        errors.append("PDF is missing navigation bookmarks.")
    errors.extend(_page_quality_errors(path, expected_lang))
    return errors


def _page_quality_errors(path, expected_lang=None):
    """Render-derived layout checks: near-blank pages, header collisions.

    The visual-inspection checklist in references/pdf-production.md used to be
    enforced by eye alone, which is how a near-blank page shipped. These run the
    mechanical part of that checklist. A missing render backend downgrades to a
    warning rather than a silent pass, so the gap is visible.
    """
    try:
        from scripts import pdf_quality
    except ImportError:  # pragma: no cover - packaging fallback
        import pdf_quality
    try:
        report = pdf_quality.run_quality_checks(
            path, lang=expected_lang, check_tokens=False
        )
    except ImportError as exc:
        return [
            warning(
                "PDF page-quality checks skipped, render backend missing: "
                f"{exc}"
            )
        ]
    except Exception as exc:
        return [f"PDF page-quality checks could not run: {exc}"]
    findings = [finding.format() for finding in report.errors]
    findings.extend(
        warning(
            f"{finding.check}"
            + (f" [{finding.where}]" if finding.where else "")
            + f": {finding.message}"
        )
        for finding in report.warnings
    )
    return findings


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_rewild_receipt(report_path, receipt, *, expected_lang=None):
    """Verify that a passing Rewild receipt belongs to this exact report."""
    report_path = Path(report_path).resolve()
    if not isinstance(receipt, dict):
        return ["Rewild receipt root must be an object."]
    errors = []
    if receipt.get("schema_version") != 1:
        errors.append("Rewild receipt has an unsupported schema version.")
    if receipt.get("status") != "passed":
        errors.append("Rewild receipt does not record a passing gate.")
    recorded_report = receipt.get("report_path")
    if not recorded_report or Path(str(recorded_report)).name != report_path.name:
        errors.append("Rewild receipt belongs to a different report path.")
    if expected_lang and receipt.get("report_lang") != expected_lang:
        errors.append(
            "Rewild receipt language does not match the expected report language."
        )
    try:
        report_hash = _file_sha256(report_path)
    except OSError as exc:
        errors.append(f"Report could not be hashed for Rewild validation: {exc}")
    else:
        if receipt.get("report_sha256") != report_hash:
            errors.append(
                "Rewild receipt does not match the current report; rerun the gate."
            )
    receipt_lang = receipt.get("report_lang")
    profile = REWILD_PROFILE_DIRS.get(receipt_lang)
    if profile is None:
        errors.append("Rewild receipt has an unsupported report language.")
    else:
        canonical_checker = (
            ROOT
            / "references"
            / "rewild"
            / profile
            / "scripts"
            / "naturalness-check.py"
        ).resolve()
        try:
            recorded_checker = validated_artifact_path(
                receipt.get("checker_path"),
                "Rewild receipt Rewild checker",
            )
        except ValueError:
            recorded_checker = None
        if recorded_checker != canonical_checker:
            errors.append(
                "Rewild receipt does not use Alexandria's canonical checker."
            )
        elif receipt.get("checker_sha256") != _file_sha256(canonical_checker):
            errors.append("Alexandria's bundled Rewild checker has changed.")
    if receipt.get("review_status") != "completed":
        errors.append("Rewild receipt does not record a completed blind review.")
    for path_key, hash_key, label in (
        ("source_path", "source_sha256", "pre-Rewild source"),
        ("checker_path", "checker_sha256", "Rewild checker"),
        ("review_note_path", "review_note_sha256", "blind-review note"),
    ):
        try:
            path = validated_artifact_path(
                receipt.get(path_key),
                f"Rewild receipt {label}",
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        try:
            digest = _file_sha256(path)
        except (OSError, ValueError) as exc:
            errors.append(f"Rewild receipt {label} could not be verified: {exc}")
            continue
        if receipt.get(hash_key) != digest:
            errors.append(f"Rewild receipt {label} has changed since the gate.")
    if not errors:
        try:
            from .rewild_gate import run_gate
        except ImportError:
            from rewild_gate import run_gate

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            regenerated = work / "receipt.json"
            rerun_errors = hard_errors(
                run_gate(
                    report_path,
                    Path(receipt["source_path"]),
                    report_lang=receipt_lang,
                    review_note_path=Path(receipt["review_note_path"]),
                    receipt_path=regenerated,
                )
            )
            if not rerun_errors and regenerated.is_file():
                fresh = json.loads(regenerated.read_text(encoding="utf-8"))
                for audit_field in ("heuristic_exemptions",):
                    if fresh.get(audit_field, []) != receipt.get(
                        audit_field, []
                    ):
                        errors.append(
                            f"Rewild receipt {audit_field} do not match the "
                            "recomputed gate audit trail; the receipt was "
                            "altered after issue."
                        )
            errors.extend(
                f"Rewild gate recheck failed: {error}" for error in rerun_errors
            )
    return errors


class _InvocationParser(argparse.ArgumentParser):
    def __init__(self, *args, invocation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._invocation = invocation

    def error(self, message):
        invocation = self._invocation or " ".join(sys.argv)
        self.print_usage(sys.stderr)
        self.exit(2, f"{invocation}\n{self.prog}: error: {message}\n")


def build_parser(invocation=None):
    parser = _InvocationParser(
        description="Validate an Alexandria report",
        invocation=invocation,
    )
    parser.add_argument("markdown", help="Markdown report to validate")
    parser.add_argument("--ledger", help="Evidence ledger JSON to cross-check")
    parser.add_argument(
        "--rewild-receipt",
        help="required Rewild gate receipt bound to this exact Markdown file",
    )
    parser.add_argument(
        "--content-receipt",
        help="required content-quality receipt bound to the report and ledger",
    )
    parser.add_argument(
        "--source-fidelity-receipt",
        help="required live-source receipt bound to the evidence ledger",
    )
    parser.add_argument("--pdf", help="Rendered PDF to reopen and validate")
    parser.add_argument("--min-words", type=int, default=0)
    parser.add_argument("--max-words", type=int, default=0)
    parser.add_argument("--min-chars", type=int, default=0)
    parser.add_argument("--max-chars", type=int, default=0)
    parser.add_argument(
        "--expected-lang",
        "--lang",
        dest="expected_lang",
        choices=LANG_CHOICES,
    )
    parser.add_argument("--min-sources", type=int, default=1)
    parser.add_argument("--min-sections", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-text-chars", type=int, default=1)
    parser.add_argument("--min-links", type=int, default=0)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="structure, hashes, and receipt presence only",
    )
    parser.add_argument(
        "--final-once",
        dest="final_once",
        help="reuse a supplied fidelity result JSON instead of a live re-fetch",
    )
    # Spec §7.5 gives `--force` one job: overwriting output files. This command
    # writes none, so the flag is hidden and rejected rather than silently
    # accepted.
    parser.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    return parser


def _receipt_presence_errors(args):
    errors = []
    for flag, value, label in (
        ("--rewild-receipt", args.rewild_receipt, "Rewild gate receipt"),
        ("--content-receipt", args.content_receipt, "Content quality gate receipt"),
        (
            "--source-fidelity-receipt",
            args.source_fidelity_receipt,
            "source-fidelity receipt",
        ),
    ):
        if not value:
            errors.append(f"A {label} is required ({flag}).")
        elif not Path(value).is_file():
            errors.append(f"{label} is missing: {value}")
    return errors


def _receipt_hash_errors(args, markdown_path):
    errors = []
    try:
        report_hash = hashlib.sha256(Path(markdown_path).read_bytes()).hexdigest()
    except OSError as exc:
        return [f"Report could not be hashed: {exc}"]
    ledger_hash = None
    if args.ledger:
        try:
            ledger_hash = hashlib.sha256(Path(args.ledger).read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"Evidence ledger could not be hashed: {exc}")
    # The Rewild receipt is not ledger-bound: rewild_gate.run_gate records the
    # report, pre-Rewild source and checker hashes only. The source-fidelity
    # receipt binds claims to sources, so it records a ledger hash and no
    # report hash; the report hash lives in receipts/issue.json.
    for _flag, value, label, report_bound, ledger_bound in (
        ("--rewild-receipt", args.rewild_receipt, "Rewild gate receipt", True, False),
        (
            "--content-receipt",
            args.content_receipt,
            "Content quality gate receipt",
            True,
            True,
        ),
        (
            "--source-fidelity-receipt",
            args.source_fidelity_receipt,
            "source-fidelity receipt",
            False,
            True,
        ),
    ):
        if not value or not Path(value).is_file():
            continue
        try:
            payload = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{label} could not be read for hash check: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{label} is not a JSON object.")
            continue
        recorded = payload.get("report_sha256")
        if not recorded:
            if report_bound:
                errors.append(f"{label} does not record report_sha256.")
        elif recorded != report_hash:
            errors.append(
                f"{label} report_sha256 does not match the current report."
            )
        recorded_ledger = payload.get("ledger_sha256")
        if ledger_hash and ledger_bound:
            if not recorded_ledger:
                errors.append(f"{label} does not record ledger_sha256.")
            elif recorded_ledger != ledger_hash:
                errors.append(
                    f"{label} ledger_sha256 does not match the current ledger."
                )
    return errors


def _apply_fidelity_result(path):
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"--final-once fidelity result could not be read: {exc}"]
    if not isinstance(result, dict):
        return ["--final-once fidelity result must be a JSON object."]
    errors = []
    for item in result.get("errors") or []:
        errors.append(str(item))
    for item in result.get("mismatches") or []:
        errors.append(f"Fidelity mismatch: {item}")
    return errors


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    invocation = " ".join(["validate_report.py", *argv])
    parser = build_parser(invocation=invocation)
    args = parser.parse_args(argv)
    if args.force:
        parser.error(
            "--force is not accepted here: validate_report writes no output "
            "files, so there is nothing to overwrite."
        )
    markdown_path = Path(args.markdown)
    try:
        text = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    errors = validate_markdown(
        text,
        min_words=max(args.min_words, 0),
        max_words=max(args.max_words, 0),
        min_chars=max(args.min_chars, 0),
        max_chars=max(args.max_chars, 0),
        min_sources=max(args.min_sources, 0),
        min_sections=max(args.min_sections, 0),
        expected_lang=args.expected_lang,
    )
    if args.ledger:
        try:
            ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Evidence ledger could not be read: {exc}")
        else:
            errors.extend(validate_report_against_ledger(text, ledger))
    if args.fast:
        errors.extend(_receipt_presence_errors(args))
        errors.extend(_receipt_hash_errors(args, markdown_path))
        if args.pdf:
            errors.extend(
                validate_pdf(
                    Path(args.pdf),
                    min_pages=max(args.min_pages, 0),
                    min_text_chars=max(args.min_text_chars, 0),
                    min_links=max(args.min_links, 0),
                    expected_lang=args.expected_lang,
                )
            )
        return emit_findings(
            errors,
            ok_message=f"[OK] Report validated: {markdown_path}",
        )
    if not args.rewild_receipt:
        errors.append(
            "A Rewild gate receipt is required. Run scripts/rewild_gate.py first."
        )
    else:
        try:
            receipt = json.loads(
                Path(args.rewild_receipt).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Rewild receipt could not be read: {exc}")
        else:
            errors.extend(
                validate_rewild_receipt(
                    markdown_path,
                    receipt,
                    expected_lang=args.expected_lang,
                )
            )
    if not args.content_receipt:
        errors.append(
            "A Content quality gate receipt is required. "
            "Run scripts/content_gate.py first."
        )
    elif not args.ledger:
        errors.append(
            "Content receipt validation requires --ledger."
        )
    elif not args.source_fidelity_receipt:
        errors.append(
            "A source-fidelity receipt is required. "
            "Run scripts/source_fidelity.py --online first."
        )
    else:
        try:
            content_receipt = json.loads(
                Path(args.content_receipt).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Content receipt could not be read: {exc}")
        else:
            try:
                from .content_gate import validate_content_receipt
            except ImportError:
                from content_gate import validate_content_receipt
            content_errors = validate_content_receipt(
                markdown_path,
                Path(args.ledger),
                content_receipt,
                source_fidelity_receipt_path=Path(
                    args.source_fidelity_receipt
                ),
                expected_lang=args.expected_lang,
            )
            errors.extend(content_errors)
            if not hard_errors(content_errors):
                try:
                    source_receipt_bytes = Path(
                        args.source_fidelity_receipt
                    ).read_bytes()
                    source_receipt = json.loads(source_receipt_bytes)
                except (
                    OSError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ) as exc:
                    errors.append(
                        f"Source-fidelity receipt could not be read: {exc}"
                    )
                else:
                    if (
                        content_receipt.get(
                            "source_fidelity_receipt_sha256"
                        )
                        != hashlib.sha256(
                            source_receipt_bytes
                        ).hexdigest()
                    ):
                        errors.append(
                            "Source-fidelity receipt changed after content review."
                        )
                    elif args.final_once:
                        errors.extend(_apply_fidelity_result(args.final_once))
                    else:
                        errors.extend(
                            validate_source_fidelity_receipt_online(
                                Path(args.ledger),
                                source_receipt,
                            )
                        )
    if args.pdf:
        errors.extend(
            validate_pdf(
                Path(args.pdf),
                min_pages=max(args.min_pages, 0),
                min_text_chars=max(args.min_text_chars, 0),
                min_links=max(args.min_links, 0),
                expected_lang=args.expected_lang,
            )
        )

    return emit_findings(
        errors,
        ok_message=f"[OK] Report validated: {markdown_path}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
