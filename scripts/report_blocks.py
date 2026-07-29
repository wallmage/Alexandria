"""Shared visible-block model for Alexandria Markdown reports."""

import re
from dataclasses import dataclass

try:
    from .report_contract import canonical_visible_text
except ImportError:
    from report_contract import canonical_visible_text

SOURCE_HEADINGS = frozenset(
    {
        "sources",
        "references",
        "source list",
        "来源",
        "資料來源",
        "资料来源",
        "参考资料",
        "參考資料",
    }
)

_TRANSITION_PREFIX = re.compile(
    r"(?ix)^"
    r"(?:"
    r"(?:this|the\s+(?:next|following|previous))\s+"
    r"(?:section|chapter|part|report)\s+"
    r"(?:examines|explains|describes|outlines|covers|discusses|"
    r"turns\s+to|sets\s+out)"
    r"|"
    r"(?:本|下|上一)(?:節|节|章|部分|報告|报告).{0,12}?"
    r"(?:說明|说明|介紹|介绍|討論|讨论|概述|轉向|转向)"
    r")"
    r"(?:\s*[:：—–-]\s*|\s+)"
)


@dataclass(frozen=True)
class ReportBlock:
    """One rendered Markdown block after presentation syntax is removed."""

    raw: str
    text: str
    assertion_text: str
    kind: str
    start: int
    end: int
    in_bibliography: bool
    heading_level: int | None = None


@dataclass(frozen=True)
class Heading:
    """A Markdown heading outside fenced code."""

    title: str
    level: int
    start: int
    end: int


def mask_fenced_code(text):
    """Blank fenced code without changing offsets or line endings."""
    masked = []
    fence_char = None
    fence_length = 0

    def hide(line):
        return "".join(char if char in "\r\n" else " " for char in line)

    for line in text.splitlines(keepends=True):
        if fence_char is None:
            opener = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if opener:
                marker = opener.group(1)
                fence_char = marker[0]
                fence_length = len(marker)
                masked.append(hide(line))
            else:
                masked.append(line)
            continue

        closing = re.match(r"^ {0,3}([`~]{3,})[ \t]*(?:\r?\n)?$", line)
        masked.append(hide(line))
        if (
            closing
            and set(closing.group(1)) == {fence_char}
            and len(closing.group(1)) >= fence_length
        ):
            fence_char = None
            fence_length = 0
    return "".join(masked)


def _strip_inline_presentation(text):
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s<>]+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?<!\\)[*_~`]+", "", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", text)
    return text


def normalize_visible_text(raw, *, kind):
    """Strip Markdown presentation syntax while preserving rendered words."""
    lines = raw.splitlines()
    normalized = []
    for line in lines:
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s{0,3}>\s?", "", line)
        line = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", line)
        if re.fullmatch(
            r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*",
            line,
        ):
            continue
        line = re.sub(r"^\s*\[![A-Za-z][A-Za-z0-9_-]*\]\s*", "", line)
        if kind == "table":
            line = line.replace("|", " ")
        normalized.append(line)
    text = _strip_inline_presentation("\n".join(normalized))
    text = canonical_visible_text(text)
    return re.sub(r"\s+", " ", text).strip()


def strip_structural_prefix(text):
    """Remove only a leading navigation phrase, retaining its assertion."""
    return _TRANSITION_PREFIX.sub("", text, count=1).strip()


def headings(text):
    """Return headings outside fenced code."""
    masked = mask_fenced_code(text)
    found = []
    for match in re.finditer(
        r"(?m)^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\n|$)",
        masked,
    ):
        raw_title = text[match.start(2) : match.end(2)]
        title = normalize_visible_text(raw_title, kind="heading")
        found.append(
            Heading(
                title=title,
                level=len(match.group(1)),
                start=match.start(),
                end=match.end(),
            )
        )
    return found


def h2_sections(text):
    """Return legacy ``(title, start)`` H2 section tuples."""
    return [
        (heading.title, heading.start)
        for heading in headings(text)
        if heading.level == 2
    ]


def bibliography_ranges(text):
    """Return every source-headed H2 range, bounded by the next H2."""
    sections = [
        heading for heading in headings(text) if heading.level == 2
    ]
    ranges = []
    for index, heading in enumerate(sections):
        if heading.title.casefold() not in SOURCE_HEADINGS:
            continue
        end = sections[index + 1].start if index + 1 < len(sections) else len(text)
        ranges.append((heading.start, end))
    return ranges


def _is_bibliography_entry(raw):
    """Return whether a block contains only strict Markdown source links."""
    entries = [line.strip() for line in raw.splitlines() if line.strip()]
    if not entries:
        return False
    return all(
        re.fullmatch(
            r"(?:[-+*]|\d+[.)])?\s*"
            r"\[[^\]\n]+\]\("
            r"(?:<https?://[^>\s]+>|https?://[^\s)]+(?:\([^)]*\)[^\s)]*)?)"
            r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?"
            r"\)\s*",
            line,
        )
        is not None
        for line in entries
    )


def _block_kind(line):
    if re.match(r"^ {0,3}#{1,6}[ \t]+", line):
        return "heading"
    if re.match(r"^ {0,3}>", line):
        return "blockquote"
    if re.match(r"^\s*\|", line) or line.count("|") >= 2:
        return "table"
    if re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", line):
        return "list"
    return "paragraph"


def report_blocks(text):
    """Parse all non-fenced Markdown into rendered, source-aware blocks."""
    masked = mask_fenced_code(text)
    lines = masked.splitlines(keepends=True)
    ranges = bibliography_ranges(text)
    parsed = []
    buffered = []
    buffered_kind = None
    buffered_start = 0
    offset = 0
    in_table = False

    def flush(end):
        nonlocal buffered, buffered_kind, buffered_start
        if not buffered:
            return
        raw = text[buffered_start:end].rstrip("\r\n")

        def append(block_text, kind):
            heading_match = re.match(r"^ {0,3}(#{1,6})[ \t]+", raw)
            heading_level = (
                len(heading_match.group(1)) if heading_match else None
            )
            in_source_section = any(
                start <= buffered_start < range_end
                for start, range_end in ranges
            )
            is_source_heading = (
                heading_level == 2
                and block_text.casefold() in SOURCE_HEADINGS
            )
            in_bibliography = in_source_section and (
                is_source_heading or _is_bibliography_entry(raw)
            )
            parsed.append(
                ReportBlock(
                    raw=raw,
                    text=block_text,
                    assertion_text=strip_structural_prefix(block_text),
                    kind=kind,
                    start=buffered_start,
                    end=end,
                    in_bibliography=in_bibliography,
                    heading_level=heading_level,
                )
            )

        if buffered_kind in {"table", "table_header"}:
            row = raw.strip()
            if row.startswith("|"):
                row = row[1:]
            if row.endswith("|") and not row.endswith(r"\|"):
                row = row[:-1]
            for cell_index, cell in enumerate(re.split(r"(?<!\\)\|", row)):
                block_text = normalize_visible_text(
                    cell,
                    kind="paragraph",
                )
                if block_text and not re.fullmatch(
                    r":?-{3,}:?",
                    block_text,
                ):
                    cell_kind = buffered_kind
                    if buffered_kind == "table" and cell_index == 0:
                        cell_kind = "table_row_label"
                    append(block_text, cell_kind)
        else:
            block_text = normalize_visible_text(raw, kind=buffered_kind)
            if block_text:
                append(block_text, buffered_kind)
        buffered = []
        buffered_kind = None

    for line in lines:
        line_end = offset + len(line)
        if not line.strip():
            flush(offset)
            in_table = False
            offset = line_end
            continue
        kind = _block_kind(line)
        if kind == "table":
            flush(offset)
            table_kind = "table" if in_table else "table_header"
            buffered = [line]
            buffered_kind = table_kind
            buffered_start = offset
            flush(line_end)
            in_table = True
        elif kind == "heading":
            flush(offset)
            buffered = [line]
            buffered_kind = kind
            buffered_start = offset
            flush(line_end)
            in_table = False
        elif kind == "list":
            # Every rendered <li> is an independent claim/citation boundary.
            # Joining adjacent bullets lets one item's URL or evidence satisfy
            # another item, so flush before starting each list item.
            flush(offset)
            buffered = [line]
            buffered_kind = kind
            buffered_start = offset
            in_table = False
        elif (
            buffered
            and buffered_kind == "list"
            and kind == "paragraph"
            and re.match(r"^\s{2,}\S", line)
        ):
            buffered.append(line)
            in_table = False
        elif buffered and kind != buffered_kind:
            flush(offset)
            buffered = [line]
            buffered_kind = kind
            buffered_start = offset
            in_table = False
        else:
            if not buffered:
                buffered_start = offset
                buffered_kind = kind
            buffered.append(line)
            in_table = False
        offset = line_end
    flush(len(text))
    return parsed


def visible_report_blocks(text):
    """Return every visible non-bibliography block."""
    return [
        block for block in report_blocks(text) if not block.in_bibliography
    ]


def validation_report_blocks(text):
    """Return narrative blocks plus source labels that may assert claims."""
    return [
        block
        for block in report_blocks(text)
        if (
            not block.in_bibliography
            or block.heading_level != 2
        )
    ]


def mask_bibliography(text):
    """Blank only recognized bibliography blocks while preserving offsets."""
    masked = list(text)
    for block in report_blocks(text):
        if not block.in_bibliography:
            continue
        masked[block.start : block.end] = (
            character if character in "\r\n" else " "
            for character in text[block.start : block.end]
        )
    return "".join(masked)


def visible_report_prose(text):
    """Return normalized visible prose shared by report and Rewild gates."""
    pieces = []
    for block in visible_report_blocks(text):
        if pieces:
            pieces.append("\n" if block.kind == "heading" else "\n\n")
        pieces.append(block.text)
    return "".join(pieces)
