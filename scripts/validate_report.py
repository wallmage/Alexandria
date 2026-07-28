#!/usr/bin/env python3
"""Deterministic structural checks for Alexandria Markdown and PDF reports."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

SOURCE_HEADINGS = {
    "sources",
    "references",
    "来源",
    "資料來源",
    "参考资料",
    "參考資料",
}
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
TRADITIONAL_MARKERS = set("這個為與報發後裡麼還說對時國學術據點體現關於會開")
SIMPLIFIED_MARKERS = set("这个为与报发后里么还说对时国学术据点体现关于会开")


def _h2_sections(text):
    masked = _mask_fenced_code(text)
    return [
        (match.group(1).strip(), match.start())
        for match in re.finditer(r"^##\s+(.+?)\s*$", masked, re.MULTILINE)
    ]


def _mask_fenced_code(text):
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
    return re.findall(r"https?://[^\s<>]+", "".join(masked))


def detect_language(text):
    han_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if han_count <= latin_count * 0.3:
        return "en"
    traditional = sum(text.count(char) for char in TRADITIONAL_MARKERS)
    simplified = sum(text.count(char) for char in SIMPLIFIED_MARKERS)
    if traditional == simplified:
        return "zh"
    return "zh-HK" if traditional > simplified else "zh-CN"


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
    source_starts = [
        start
        for heading, start in sections
        if heading.casefold() in SOURCE_HEADINGS
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

    sections = _h2_sections(text)
    body = text
    source_starts = [
        start
        for heading, start in sections
        if heading.casefold() in SOURCE_HEADINGS
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
            errors.append(f"Report location is missing for claim {claim_id}.")
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
                expected_urls.intersection(extract_markdown_urls(paragraph))
                for paragraph in matching_paragraphs
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
    mark_info = root.get("/MarkInfo", {})
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
    return errors


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
    if receipt.get("report_path") != str(report_path):
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
            rerun_errors = run_gate(
                report_path,
                Path(receipt["source_path"]),
                report_lang=receipt_lang,
                review_note_path=Path(receipt["review_note_path"]),
                receipt_path=regenerated,
                waiver_path=waiver_path,
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
    parser.add_argument("--pdf", help="Rendered PDF to reopen and validate")
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
            errors.extend(
                validate_content_receipt(
                    markdown_path,
                    Path(args.ledger),
                    content_receipt,
                    expected_lang=args.expected_lang,
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

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Report validated: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
