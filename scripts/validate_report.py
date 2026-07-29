#!/usr/bin/env python3
"""Deterministic structural checks for Alexandria Markdown and PDF reports."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from .render_binding import (
        validate_render_binding,
        validate_render_receipt,
    )
    from .report_blocks import (
        SOURCE_HEADINGS,
        bibliography_ranges,
        h2_sections,
        mask_fenced_code,
        validation_report_blocks,
        visible_report_blocks,
        visible_report_prose,
    )
    from .report_contract import detect_language
    from .source_fidelity import validate_source_fidelity_receipt_online
except ImportError:
    from render_binding import validate_render_binding, validate_render_receipt
    from report_blocks import (
        SOURCE_HEADINGS,
        bibliography_ranges,
        h2_sections,
        mask_fenced_code,
        validation_report_blocks,
        visible_report_blocks,
        visible_report_prose,
    )
    from report_contract import detect_language
    from source_fidelity import validate_source_fidelity_receipt_online

try:
    from .validate_ledger import (
        FRESHNESS_WINDOW_DAYS,
        HUMAN_HARM_PATTERN,
        NEGATIVE_EXISTENCE_PATTERN,
        PROTECTED_LIVING_STATUSES,
        SENSITIVE_PRIVATE_PATTERN,
        evidence_coverage_errors,
        mentions_person_alias,
    )
except ImportError:
    from validate_ledger import (
        FRESHNESS_WINDOW_DAYS,
        HUMAN_HARM_PATTERN,
        NEGATIVE_EXISTENCE_PATTERN,
        PROTECTED_LIVING_STATUSES,
        SENSITIVE_PRIVATE_PATTERN,
        evidence_coverage_errors,
        mentions_person_alias,
    )

LANG_CHOICES = ("en", "zh-CN", "zh-HK")
ROOT = Path(__file__).resolve().parents[1]
S2T_CHARACTER_MAP = (
    ROOT / "references" / "rewild" / "opencc" / "STCharacters.txt"
)
REWILD_PROFILE_DIRS = {
    "en": "rewild",
    "zh-CN": "rewild-zh",
    "zh-HK": "rewild-hk",
}

_STRUCTURAL_LABEL_EXACT = frozenset(
    {
        "analysis",
        "audit",
        "background",
        "body",
        "category",
        "conclusion",
        "conclusions",
        "context",
        "corroborating source",
        "key takeaways",
        "date",
        "documentation",
        "evidence",
        "executive summary",
        "expected result",
        "finding",
        "findings",
        "impact",
        "implication",
        "implications",
        "introduction",
        "key process",
        "limitation",
        "limitations",
        "measure",
        "method",
        "methodology",
        "metric",
        "name",
        "next steps",
        "normal source title",
        "official source",
        "option",
        "options",
        "outlook",
        "overview",
        "owner",
        "parse",
        "period",
        "primary source",
        "recommendation",
        "recommendations",
        "reference",
        "references",
        "render",
        "reopen",
        "report",
        "result",
        "results",
        "risk",
        "risks",
        "scenario",
        "scenarios",
        "source",
        "sources",
        "stage",
        "status",
        "summary",
        "supported finding",
        "timeline",
        "title",
        "unrelated finding",
        "value",
        "ways forward",
        "what this means",
        "why it matters",
        "current state",
        "year",
    }
)
_CJK_STRUCTURAL_LABEL_EXACT = frozenset(
    {
    "分析",
    "背景",
    "結論",
    "结论",
    "摘要",
    "概覽",
    "概览",
    "方法",
    "限制",
    "建議",
    "建议",
    "展望",
    "來源",
    "来源",
    "參考資料",
    "参考资料",
    "指標",
    "指标",
    "結果",
    "结果",
    "風險",
    "风险",
    "影響",
    "影响",
    "下一步",
    "主要流程",
    "階段",
    "阶段",
    "預期結果",
    "预期结果",
    "解析",
    "重開",
    "重开",
    "未來展望",
    "未来展望",
    "測試資料來源",
    "测试资料来源",
    }
)
_IDENTITY_METADATA_LINE = re.compile(
    r"(?i)^\s*>\s*(client|prepared[\s_-]*by)\s*:\s*(.+?)\s*$"
)
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
        or HUMAN_HARM_PATTERN.search(label)
        or SENSITIVE_PRIVATE_PATTERN.search(label)
        or NEGATIVE_EXISTENCE_PATTERN.search(label)
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
    cjk_suffixes = (
        "公司",
        "有限公司",
        "集團",
        "集团",
        "基金會",
        "基金会",
        "研究院",
        "研究所",
        "大學",
        "大学",
        "協會",
        "协会",
        "團隊",
        "团队",
    )
    return len(label) <= 5 or label.endswith(cjk_suffixes)


def _assertion_text_without_safe_identity_metadata(block):
    """Remove only schema-valid typed identity lines from evidence prose."""
    assertion_text = block.assertion_text
    for line in block.raw.splitlines():
        match = _IDENTITY_METADATA_LINE.fullmatch(line)
        if not match or not _is_safe_identity_label(match.group(2)):
            continue
        rendered_line = re.sub(r"^\s*>\s*", "", line).strip()
        assertion_text = assertion_text.replace(rendered_line, " ", 1)
    return re.sub(r"\s+", " ", assertion_text).strip()


def _assertion_units(text):
    """Split a rendered block into independently checkable statements."""
    return [
        unit.strip()
        for unit in re.split(
            r"(?<=[!?！？。；;])\s*|(?<=\.)\s+",
            text.strip(),
        )
        if unit.strip()
    ]


def _is_explicit_structural_label(block, text):
    """Recognize only bounded navigation/schema labels, not arbitrary prose."""
    markdown_link_labels = {
        re.sub(r"(?<!\\)[*_~`]+", "", label).strip()
        for label in re.findall(r"(?<!!)\[([^\]\n]+)\]\(", block.raw)
    }
    if (
        block.kind not in {"heading", "table_header", "table_row_label"}
        and not block.in_bibliography
        and text not in markdown_link_labels
    ):
        return False
    label = text.strip()
    if (
        not label
        or len(label) > 80
        or re.search(r"[.!?！？。；;]|\d", label)
    ):
        return False
    folded = label.casefold()
    return (
        folded in _STRUCTURAL_LABEL_EXACT
        or label in _CJK_STRUCTURAL_LABEL_EXACT
    )


def _h2_sections(text):
    return h2_sections(text)


def _mask_fenced_code(text):
    return mask_fenced_code(text)


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
        if heading.casefold() in SOURCE_HEADINGS
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
    """Return report body prose without Sources, URLs, markup, or code."""
    del sections
    text = mask_fenced_code(text)

    def hide(match):
        return "".join(
            character if character in "\r\n" else " "
            for character in match.group(0)
        )

    text = re.sub(
        r"<pre\b.*?</pre>",
        hide,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"(?m)^(?: {4}|\t).*$", hide, text)
    text = re.sub(r"`[^`\n]*`", hide, text)
    return visible_report_prose(text)


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
        if heading.casefold() in SOURCE_HEADINGS
    ]
    if not source_indexes:
        errors.append("Report needs a final H2 Sources section.")
    else:
        if len(source_indexes) != 1:
            errors.append(
                "Report must contain exactly one H2 Sources section."
            )
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
        source_tail_blocks = [
            block
            for block in visible_report_blocks(text)
            if block.start >= source_start
        ]
        if source_tail_blocks:
            errors.append(
                "The terminal Sources section may contain only bibliography "
                "entries; move visible narrative before Sources."
            )

    return errors


def _searched_within_window(value, report_day):
    try:
        searched = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return 0 <= (report_day - searched).days <= FRESHNESS_WINDOW_DAYS


def validate_report_against_ledger(text, ledger):
    """Check that report links and claim locations exist in the ledger."""
    if not isinstance(ledger, dict):
        return ["Evidence ledger root must be an object."]
    sources = ledger.get("sources", [])
    claims = ledger.get("claims", [])
    if not isinstance(sources, list) or not isinstance(claims, list):
        return ["Evidence ledger sources and claims must be arrays."]

    ledger_urls = {
        source.get("url")
        for source in sources
        if isinstance(source, dict) and source.get("url")
    }
    source_urls = {
        source.get("source_id"): source.get("url")
        for source in sources
        if isinstance(source, dict)
        and source.get("source_id")
        and source.get("url")
    }
    source_titles_by_url = {
        source.get("url"): re.sub(
            r"\s+",
            " ",
            str(source.get("title")),
        ).strip()
        for source in sources
        if isinstance(source, dict)
        and source.get("url")
        and source.get("title")
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
    for url in sorted(set(extract_markdown_urls(text)) - ledger_urls):
        errors.append(f"Report URL is not present in the ledger: {url}")

    blocks = validation_report_blocks(text)
    source_ranges = bibliography_ranges(text)
    terminal_source_range = source_ranges[-1] if source_ranges else None
    source_section_urls = set(
        extract_markdown_urls(text[slice(*terminal_source_range)])
        if terminal_source_range
        else []
    )
    normalized_paragraphs = [
        (block, block.text, block.assertion_text)
        for block in blocks
        if block.text
    ]
    validation_units = [
        (block, unit, unit)
        for block, _, _ in normalized_paragraphs
        for unit in _assertion_units(
            _assertion_text_without_safe_identity_metadata(block)
        )
    ]
    excerpt_claims = []
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("include_in_report") is not True:
            continue
        for excerpt in claim.get("report_excerpts", []):
            normalized = re.sub(r"\s+", " ", str(excerpt)).strip()
            if normalized:
                excerpt_claims.append((normalized, claim))

    decision_pattern = re.compile(
        r"(?i)\b(?:choose|select|prefer|recommend(?:ed|ation)?|wins?|"
        r"advantage|stronger option|safer default)\b|"
        r"(?:選擇|选择|建議|建议|推薦|推荐|較強|较强|更適合|更适合)"
    )
    cited_source_urls = {
        source_urls[source_id]
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
        for source_id in foundation_source_ids(claim.get("claim_id"))
        if source_id in source_urls
    }
    try:
        report_day = date.fromisoformat(str(ledger.get("report_date")))
    except (TypeError, ValueError):
        report_day = None
    for block, normalized_paragraph, assertion_text in validation_units:
        paragraph = block.raw
        if not assertion_text:
            continue
        mapped_claims = [
            claim
            for excerpt, claim in excerpt_claims
            if (
                excerpt in normalized_paragraph
                or normalized_paragraph in excerpt
            )
        ]
        if HUMAN_HARM_PATTERN.search(
            normalized_paragraph
        ) or SENSITIVE_PRIVATE_PATTERN.search(normalized_paragraph):
            mapped_person_ids = {
                person_id
                for claim in mapped_claims
                for person_id in claim.get("person_ids", [])
            }
            for person in ledger.get("people", []):
                if (
                    isinstance(person, dict)
                    and person.get("living_status")
                    in PROTECTED_LIVING_STATUSES
                    and mentions_person_alias(normalized_paragraph, person)
                    and person.get("person_id") not in mapped_person_ids
                ):
                    errors.append(
                        "Protected-person harm in the report is not mapped to "
                        f"the correct reviewed claim: {person.get('person_id')}."
                    )
        if not mapped_claims:
            metadata_only = bool(
                re.fullmatch(
                    r"(?:[A-Za-z]+\s+)?(?:"
                    r"[0-9]{4}年[0-9]{1,2}月(?:[0-9]{1,2}日)?|"
                    r"[0-9]{4}(?:[-/][0-9]{1,2})"
                    r"(?:[-/][0-9]{1,2})?|[0-9]{4}|"
                    r"[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|"
                    r"[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})",
                    assertion_text.strip(),
                )
            )
            exact_source_title = (
                block.in_bibliography
                and any(
                    source_titles_by_url.get(url) == assertion_text
                    for url in extract_markdown_urls(block.raw)
                )
            )
            if not (
                metadata_only
                or _is_explicit_structural_label(block, assertion_text)
                or exact_source_title
            ):
                errors.append(
                    "Report unit carries externally checkable assertions but "
                    "maps to no ledger claim: "
                    + assertion_text[:120]
                )
        if mapped_claims:
            mapped_evidence = []
            for claim in mapped_claims:
                mapped_evidence.extend(
                    (
                        str(claim.get("claim") or ""),
                        str(claim.get("extract_or_location") or ""),
                    )
                )
                for entry in claim.get("source_evidence", []):
                    if isinstance(entry, dict):
                        mapped_evidence.append(
                            str(entry.get("extract_or_location") or "")
                        )
            errors.extend(
                "Report assertion is not carried by its mapped ledger claim: "
                + error
                for error in evidence_coverage_errors(
                    {
                        "claim_id": "report unit",
                        "kind": "fact",
                        "claim": assertion_text,
                        "extract_or_location": " ".join(mapped_evidence),
                    }
                )
            )
        if decision_pattern.search(normalized_paragraph) and not mapped_claims:
            paragraph_urls = set(extract_markdown_urls(paragraph))
            if not paragraph_urls:
                errors.append(
                    "Decision language is not traceable to a mapped claim or "
                    f"nearby citation: {normalized_paragraph[:120]}"
                )
            elif not paragraph_urls & cited_source_urls:
                errors.append(
                    "Decision language cites no source that backs a ledger "
                    f"claim: {normalized_paragraph[:120]}"
                )
        if NEGATIVE_EXISTENCE_PATTERN.search(normalized_paragraph):
            search_records = [
                claim.get("evidence_of_absence")
                for claim in mapped_claims
                if isinstance(claim.get("evidence_of_absence"), dict)
            ]
            complete = [
                record
                for record in search_records
                if record.get("queries")
                and record.get("expected_locations")
                and record.get("searched_at")
            ]
            if not complete:
                errors.append(
                    "Negative existence claim has no evidence-of-absence "
                    f"search record: {normalized_paragraph[:120]}"
                )
            elif report_day and not any(
                _searched_within_window(record.get("searched_at"), report_day)
                for record in complete
            ):
                errors.append(
                    "Negative existence claim rests on a search older than "
                    f"{FRESHNESS_WINDOW_DAYS} days: "
                    f"{normalized_paragraph[:120]}"
                )

    for claim in claims:
        if not isinstance(claim, dict) or claim.get("include_in_report") is not True:
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        excerpts = claim.get("report_excerpts", [])
        if not isinstance(excerpts, list) or not excerpts:
            errors.append(f"Report location is missing for claim {claim_id}.")
            continue
        for excerpt in excerpts:
            normalized = re.sub(r"\s+", " ", str(excerpt)).strip()
            matching_paragraphs = [
                paragraph
                for block, paragraph, _ in normalized_paragraphs
                if normalized
                in paragraph
            ]
            if not matching_paragraphs:
                errors.append(
                    f"Claim {claim_id} cannot be located in the report: {normalized}"
                )
                continue
            expected_source_ids = foundation_source_ids(claim_id)
            expected_urls = {
                source_urls[source_id]
                for source_id in expected_source_ids
                if source_id in source_urls
            }
            if expected_urls and not any(
                expected_urls.intersection(extract_markdown_urls(block.raw))
                for block, paragraph, _ in normalized_paragraphs
                if paragraph in matching_paragraphs
            ):
                errors.append(
                    f"Claim {claim_id} has no nearby citation to its ledger source."
                )
            for url in sorted(expected_urls - source_section_urls):
                errors.append(
                    f"Claim {claim_id} source is missing from the final Sources section: {url}"
                )
    return errors


def validate_pdf(
    path,
    *,
    min_pages=1,
    min_text_chars=1,
    min_links=0,
    expected_lang=None,
    artifact_paths=None,
    render_receipt_path=None,
):
    """Return errors after reopening and extracting text from a rendered PDF."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return [
            "PDF validation needs pypdf. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ]

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
        return [f"PDF could not be reopened: {exc}"]

    errors = []
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
    if artifact_paths is not None:
        if render_receipt_path is None:
            errors.append(
                "A renderer-issued render receipt is required to verify the "
                "exact PDF output."
            )
            errors.extend(
                validate_render_binding(
                    metadata.get("/Keywords"),
                    *artifact_paths,
                )
            )
        else:
            errors.extend(
                validate_render_receipt(
                    path,
                    render_receipt_path,
                    *artifact_paths,
                    pdf_binding=metadata.get("/Keywords"),
                )
            )
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
    warning on stderr rather than a silent pass, so the gap is visible.
    """
    try:
        from scripts import pdf_quality
    except ImportError:  # pragma: no cover - packaging fallback
        import pdf_quality
    try:
        report = pdf_quality.run_quality_checks(
            path, lang=expected_lang, check_tokens=True
        )
    except ImportError as exc:
        print(
            f"[WARN] PDF page-quality checks skipped, render backend missing: {exc}",
            file=sys.stderr,
        )
        return []
    except Exception as exc:
        return [f"PDF page-quality checks could not run: {exc}"]
    for finding in report.warnings:
        print(f"[WARN] {finding.format()}", file=sys.stderr)
    return [finding.format() for finding in report.errors]


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
            recorded_checker = Path(receipt.get("checker_path", "")).resolve()
        except (OSError, TypeError):
            recorded_checker = None
        if recorded_checker != canonical_checker:
            errors.append(
                "Rewild receipt does not use Alexandria's canonical checker."
            )
        elif receipt.get("checker_sha256") != _file_sha256(canonical_checker):
            errors.append("Alexandria's bundled Rewild checker has changed.")
    if receipt.get("review_status") != "completed":
        errors.append("Rewild receipt does not record a completed blind review.")
    if not isinstance(receipt.get("style_waivers"), list):
        errors.append("Rewild receipt style_waivers must be an array.")
    for path_key, hash_key, label in (
        ("source_path", "source_sha256", "pre-Rewild source"),
        ("checker_path", "checker_sha256", "Rewild checker"),
        ("review_note_path", "review_note_sha256", "blind-review note"),
    ):
        value = receipt.get(path_key)
        if not value:
            errors.append(f"Rewild receipt is missing the {label} path.")
            continue
        path = Path(value)
        try:
            digest = _file_sha256(path)
        except OSError as exc:
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
            waiver_path = None
            style_waivers = receipt.get("style_waivers", [])
            if style_waivers:
                waiver_path = work / "style-waivers.json"
                waiver_path.write_text(
                    json.dumps(
                        {"style_waivers": style_waivers},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            # The notes must come from the hash-bound file on disk, never
            # from the receipt's own embedded copies: replaying
            # receipt-embedded notes would make any tampered receipt
            # self-validating.
            fidelity_notes_path = None
            recorded_notes_path = receipt.get("fidelity_notes_path")
            recorded_notes_sha = receipt.get("fidelity_notes_sha256")
            if receipt.get("fidelity_notes") and not recorded_notes_path:
                errors.append(
                    "Rewild receipt records acknowledged findings but no "
                    "bound fidelity-notes file."
                )
            if recorded_notes_path:
                notes_file = Path(recorded_notes_path)
                if not notes_file.is_file():
                    errors.append(
                        "Rewild receipt's fidelity-notes file is missing: "
                        f"{recorded_notes_path}"
                    )
                elif _file_sha256(notes_file) != recorded_notes_sha:
                    errors.append(
                        "Fidelity-notes file does not match the hash "
                        "recorded in the Rewild receipt."
                    )
                else:
                    fidelity_notes_path = notes_file
            if errors:
                return errors
            rerun_errors = run_gate(
                report_path,
                Path(receipt["source_path"]),
                report_lang=receipt_lang,
                review_note_path=Path(receipt["review_note_path"]),
                receipt_path=regenerated,
                waiver_path=waiver_path,
                fidelity_notes_path=fidelity_notes_path,
            )
            if not rerun_errors and regenerated.is_file():
                fresh = json.loads(regenerated.read_text(encoding="utf-8"))
                for audit_field in ("heuristic_exemptions", "fidelity_notes"):
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


def build_parser():
    parser = argparse.ArgumentParser(description="Validate an Alexandria report")
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
    parser.add_argument(
        "--render-receipt",
        help="renderer-issued receipt for the exact PDF bytes",
    )
    parser.add_argument("--min-words", type=int, default=0)
    parser.add_argument("--max-words", type=int, default=0)
    parser.add_argument("--min-chars", type=int, default=0)
    parser.add_argument("--max-chars", type=int, default=0)
    parser.add_argument("--expected-lang", choices=LANG_CHOICES)
    parser.add_argument("--min-sources", type=int, default=1)
    parser.add_argument("--min-sections", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-text-chars", type=int, default=1)
    parser.add_argument("--min-links", type=int, default=0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
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
            if not content_errors and not errors:
                try:
                    source_receipt = json.loads(
                        Path(args.source_fidelity_receipt).read_text(
                            encoding="utf-8"
                        )
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(
                        f"Source-fidelity receipt could not be re-read: {exc}"
                    )
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
                artifact_paths=(
                    (
                        markdown_path,
                        Path(args.ledger),
                        Path(args.rewild_receipt),
                        Path(args.content_receipt),
                        Path(args.source_fidelity_receipt),
                    )
                    if all(
                        (
                            args.ledger,
                            args.rewild_receipt,
                            args.content_receipt,
                            args.source_fidelity_receipt,
                        )
                    )
                    else None
                ),
                render_receipt_path=(
                    Path(args.render_receipt)
                    if args.render_receipt
                    else Path(args.pdf).with_suffix(".render.json")
                ),
            )
        )

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Report validated: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
