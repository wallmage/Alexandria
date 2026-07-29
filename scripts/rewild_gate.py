#!/usr/bin/env python3
"""Run Alexandria's bundled Rewild checker and issue a file-bound receipt."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from artifact_safety import artifact_collision_errors  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIDELITY_NOTES_SCHEMA = ROOT / "references" / "rewild-fidelity-notes.schema.json"
PROFILES = {
    "en": ("rewild", "en"),
    "zh-CN": ("rewild-zh", "zh"),
    "zh-HK": ("rewild-hk", "hk"),
}
REQUIRED_FIDELITY_CHECKS = {
    "facts_and_figures",
    "attribution_and_uncertainty",
    "direction_and_negation",
    "causality",
}
DIRECTION_PAIRS = (
    ("increase", "decrease"),
    ("increased", "decreased"),
    ("increasing", "decreasing"),
    ("rise", "fall"),
    ("rose", "fell"),
    ("rising", "falling"),
    ("climb", "decline"),
    ("climbed", "declined"),
    ("climbing", "declining"),
    ("surge", "plunge"),
    ("surged", "plunged"),
    ("surging", "plunging"),
    ("widen", "narrow"),
    ("widened", "narrowed"),
    ("widening", "narrowing"),
    ("growth", "contraction"),
    ("grow", "contract"),
    ("grew", "contracted"),
    ("growing", "contracting"),
    ("expand", "shrink"),
    ("expanded", "shrank"),
    ("expanding", "shrinking"),
    ("improve", "worsen"),
    ("improved", "worsened"),
    ("higher", "lower"),
    ("above", "below"),
    ("profit", "loss"),
    ("gain", "lose"),
    ("gained", "lost"),
    ("strengthen", "weaken"),
    ("strengthened", "weakened"),
    ("outperform", "underperform"),
    ("outperformed", "underperformed"),
    ("outperforming", "underperforming"),
    ("advance", "retreat"),
    ("advanced", "retreated"),
    ("positive", "negative"),
    ("surplus", "deficit"),
    ("accept", "reject"),
    ("accepted", "rejected"),
    ("approve", "reject"),
    ("approved", "rejected"),
    ("accelerate", "decelerate"),
    ("double", "halve"),
    ("doubled", "halved"),
    ("doubling", "halving"),
    ("twice", "half"),
    ("上升", "下降"),
    ("上升", "下跌"),
    ("增加", "减少"),
    ("增加", "減少"),
    ("增长", "下降"),
    ("增長", "下跌"),
    ("改善", "恶化"),
    ("改善", "惡化"),
    ("擴大", "收縮"),
    ("扩大", "收缩"),
    ("接受", "拒绝"),
    ("接受", "拒絕"),
    ("批准", "否决"),
    ("批准", "否決"),
    ("强化", "削弱"),
    ("強化", "削弱"),
    ("高于", "低于"),
    ("高於", "低於"),
    ("盈利", "亏损"),
    ("盈利", "虧損"),
    ("加快", "放缓"),
    ("加快", "放緩"),
    ("上升", "回落"),
    ("走高", "下降"),
    ("走高", "下跌"),
)
NEGATIONS = {
    "en": (
        "not",
        "no",
        "none",
        "never",
        "without",
        "unable",
        "incapable",
        "cannot",
        "can't",
        "couldn't",
        "didn't",
        "doesn't",
        "don't",
        "hadn't",
        "hasn't",
        "haven't",
        "isn't",
        "shouldn't",
        "wasn't",
        "weren't",
        "won't",
        "wouldn't",
    ),
    "zh-CN": ("不", "未", "无", "没有", "并非", "无法"),
    "zh-HK": ("不", "未", "無", "沒有", "並非", "無法"),
}
EN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "while",
    "with",
}
EN_CAUSAL_FORWARD = (
    r"causes?|caused|triggers?|triggered|drives?|drove|produces?|produced|"
    r"leads? to|led to|results? in|resulted in|explains?|explained|"
    r"determines?|determined|gives? rise to|gave rise to|"
    r"is responsible for|was responsible for"
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Findings quote clause pairs with a Unicode arrow, and a legacy Windows
# console is often cp1252, where printing one raises UnicodeEncodeError and
# hides the failure behind a traceback. Messages are transliterated to ASCII
# for such a stream instead of being lost.
_CONSOLE_FALLBACKS = {
    "→": "->",
    "←": "<-",
    "—": "-",
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
}


def _console_safe(text, stream=None):
    """Return ``text`` reduced to characters the stream can actually encode."""
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        pass
    else:
        return text
    for character, replacement in _CONSOLE_FALLBACKS.items():
        text = text.replace(character, replacement)
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return text.encode(encoding, "backslashreplace").decode(
            encoding, "replace"
        )
    return text


def _checker_result(stdout):
    value = stdout.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(value):
            if char != "{":
                continue
            try:
                result, end = decoder.raw_decode(value[index:])
            except json.JSONDecodeError:
                continue
            if not value[index + end :].strip():
                return result
    raise ValueError("checker did not emit its JSON result")


def _load_style_waivers(path):
    """Return (waivers, errors).

    A malformed waiver used to be skipped in silence, so the agent saw the
    unresolved style warning instead of the reason its waiver was ignored.
    Every rejected entry now names its index and the rule it broke, and the
    gate fails closed on the diagnostics rather than proceeding with a
    partially loaded waiver set.
    """
    if path is None:
        return {}, []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("style_waivers", []) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}, [
            "Style-waiver file must be a JSON object with a 'style_waivers' "
            "array."
        ]
    waivers = {}
    errors = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"Style waiver {index} must be a JSON object.")
            continue
        section = str(entry.get("section", "")).strip()
        message = str(entry.get("message", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        if not section:
            errors.append(
                f"Style waiver {index} needs the checker's exact 'section'."
            )
        if not message:
            errors.append(
                f"Style waiver {index} needs the checker's exact 'message'."
            )
        if len(reason) < 10:
            errors.append(
                f"Style waiver {index} has a 'reason' of {len(reason)} "
                "characters after trimming; the minimum is 10."
            )
        if section and message and len(reason) >= 10:
            waivers[(section, message)] = reason
    return waivers, errors


def _fidelity_notes_schema_errors(data):
    """Validate a notes file against Alexandria's bundled JSON Schema."""
    try:
        from .validate_ledger import validate_schema
    except ImportError:
        from validate_ledger import validate_schema

    try:
        schema = json.loads(FIDELITY_NOTES_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            "Alexandria's bundled fidelity-notes schema could not be read: "
            f"{exc}"
        ]
    return [
        f"Fidelity notes file does not match {FIDELITY_NOTES_SCHEMA.name}: "
        f"{error}"
        for error in validate_schema(data, schema)
    ]


def _load_fidelity_notes(path):
    """Load reviewed intentional-edit acknowledgments; return (notes, errors).

    The report-bound blind review is authoritative for semantic equivalence;
    the deterministic clause checks are backstops. When the review demands a
    correction that genuinely changes meaning against the pre-Rewild source,
    the primary agent must document it here: each entry quotes the source
    fragment, the report fragment, and a specific reason. Fragments are
    matched case-insensitively as substrings of the compared prose (see
    ``_fragment_matches``), so only letter case may differ from the quoted
    text. An entry suppresses only the semantic findings that quote both
    fragments, every entry must match at least one finding, and all
    suppressions are recorded in the receipt.

    The file is validated against the bundled
    ``references/rewild-fidelity-notes.schema.json`` and every rejected entry produces a diagnostic naming its index and the
    exact rule it broke; a file with any rejected entry fails the gate rather
    than silently contributing fewer notes.
    """
    if path is None:
        return [], []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("fidelity_notes") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [], [
            "Fidelity notes file must be a JSON object with a "
            "'fidelity_notes' array."
        ]
    if len(entries) > MAX_FIDELITY_NOTES:
        return [], [
            f"{len(entries)} fidelity notes exceed the limit of "
            f"{MAX_FIDELITY_NOTES}; a report needing more acknowledged "
            "meaning changes must be re-drafted, not annotated."
        ]
    notes = []
    errors = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"Fidelity note {index} must be a JSON object.")
            continue
        values = {}
        complete = True
        for name, minimum in (
            ("source_fragment", MIN_FIDELITY_FRAGMENT),
            ("report_fragment", MIN_FIDELITY_FRAGMENT),
            ("reason", MIN_FIDELITY_REASON),
        ):
            value = str(entry.get(name, "")).strip()
            if len(value) < minimum:
                complete = False
                errors.append(
                    f"Fidelity note {index} has a '{name}' of {len(value)} "
                    f"characters after trimming; the minimum is {minimum}."
                )
            values[name] = value
        # One note may acknowledge several findings on the same clause pair,
        # and the receipt records it once per finding; duplicates are the
        # same acknowledgment, not extra unused waivers.
        if complete and values not in notes:
            notes.append(values)
    errors.extend(_fidelity_notes_schema_errors(data))
    if errors:
        return [], errors
    return notes, []


# Acknowledgments are a narrow escape hatch, not a waiver channel: a small
# fixed budget per report, and never for the findings below, which are the
# clearest corruption signals and are corrected by re-drafting, not by a note.
MAX_FIDELITY_NOTES = 8
MIN_FIDELITY_FRAGMENT = 15
MIN_FIDELITY_REASON = 40
# A reversed direction and an invented or swapped cause corrupt a claim just
# as completely; "causality" is one of the four mandatory fidelity checks, so
# a fabricated causal link cannot be signed away by an acknowledgment either.
UNACKNOWLEDGEABLE_FINDINGS = (
    "Semantic direction reversal",
    "Unmatched directional claim",
    "Causal claim added",
    "Causal substitution detected",
)
# The split-remnant heuristics suppress the same class of finding as a
# fidelity note, so they are rationed the same way. A report producing more
# structural remnants than this was restructured, not copy-edited, and its
# fidelity must be re-established by re-drafting rather than by exemption.
MAX_HEURISTIC_EXEMPTIONS = 8
# Share of the shorter clause list that must remain unaligned before the
# whole-document direction and causal comparison is trusted.
DOCUMENT_FALLBACK_COVERAGE = 0.2


def _finding_clause_pair(error):
    """Extract the quoted source/report clause pair a finding is about."""
    match = re.search(r"'(.*)' → '(.*)'\.$", error, re.DOTALL)
    if match:
        return (match.group(1), match.group(2))
    return (error, error)


def _fragment_matches(fragment, text):
    """Report whether a quoted note fragment occurs in ``text``.

    The contract is deliberately forgiving in exactly one dimension: the
    fragment must be quoted verbatim, but letter case is ignored, because a
    review-mandated edit often only re-cases a word and an agent should not
    burn a retry loop on that. Nothing else is normalized — whitespace,
    punctuation, and wording must match the compared prose.
    """
    return fragment.casefold() in text.casefold()


def _apply_fidelity_notes(semantic_errors, notes):
    """Split semantic findings into (remaining, acknowledged, unused_notes).

    A note documents exactly one edit, so it is bound to one clause pair and
    to at most one finding of each type on that pair. It may not acknowledge
    a second, unrelated pair that contains the same fragments, and repeated
    identical clauses elsewhere in the document raise duplicate findings that
    remain errors: an identical edit at another location is another edit.
    """
    remaining = []
    acknowledged = []
    used = [False] * len(notes)
    note_pair = [None] * len(notes)
    note_types = [set() for _ in notes]
    for error in semantic_errors:
        pair = _finding_clause_pair(error)
        source_side, report_side = pair
        finding_type = error.split(":", 1)[0]
        matched = None
        if not error.startswith(UNACKNOWLEDGEABLE_FINDINGS):
            for index, note in enumerate(notes):
                # Each fragment must match its OWN side of the clause pair;
                # matching against the whole finding text would let a note
                # with swapped or cross-side fragments suppress findings it
                # does not document.
                if (
                    _fragment_matches(note["source_fragment"], source_side)
                    and _fragment_matches(note["report_fragment"], report_side)
                    and note_pair[index] in (None, pair)
                    and finding_type not in note_types[index]
                ):
                    matched = index
                    break
        if matched is None:
            remaining.append(error)
        else:
            note_pair[matched] = pair
            note_types[matched].add(finding_type)
            used[matched] = True
            acknowledged.append(
                {
                    "finding": error,
                    "source_fragment": notes[matched]["source_fragment"],
                    "report_fragment": notes[matched]["report_fragment"],
                    "reason": notes[matched]["reason"],
                }
            )
    unused = [note for index, note in enumerate(notes) if not used[index]]
    return remaining, acknowledged, unused


def _load_review_note(
    path,
    *,
    report_path,
    source_path,
    report_lang,
):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"Blind-review note must be valid JSON: {exc}"]
    if not isinstance(data, dict) or data.get("status") != "completed":
        return None, ["Blind-review note must record status 'completed'."]
    expected_profile = PROFILES[report_lang][0]
    bindings = (
        ("schema_version", 1),
        ("report_sha256", file_sha256(report_path)),
        ("source_sha256", file_sha256(source_path)),
        ("report_lang", report_lang),
        ("profile", expected_profile),
    )
    mismatches = [
        name for name, expected in bindings if data.get(name) != expected
    ]
    if mismatches:
        return None, [
            "Blind-review note does not match the reviewed report, source, "
            "language, or profile: " + ", ".join(mismatches)
        ]
    checks = data.get("fidelity_checks")
    if not isinstance(checks, dict):
        return None, ["Blind-review note is missing fidelity_checks."]
    missing = sorted(
        name for name in REQUIRED_FIDELITY_CHECKS if checks.get(name) is not True
    )
    if missing:
        return None, [
            "Blind-review note has incomplete fidelity checks: "
            + ", ".join(missing)
        ]
    findings = data.get("findings")
    if not isinstance(findings, list):
        return None, ["Blind-review note findings must be an array."]
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            return None, [f"Blind-review finding {index + 1} must be an object."]
        category = finding.get("category")
        finding_text = str(finding.get("finding", "")).strip()
        disposition = finding.get("disposition")
        reason = str(finding.get("reason", "")).strip()
        if category not in {"style", "region", "fidelity"}:
            return None, [
                f"Blind-review finding {index + 1} has an invalid category."
            ]
        if disposition not in {"resolved", "rejected"}:
            return None, [
                f"Blind-review finding {index + 1} has no valid disposition."
            ]
        if not finding_text:
            return None, [
                f"Blind-review finding {index + 1} has no finding text."
            ]
        if category in {"region", "fidelity"} and disposition != "resolved":
            return None, [
                f"Blind-review finding {index + 1} is an unresolved "
                f"{category} defect."
            ]
        if len(reason) < 10:
            return None, [
                f"Blind-review finding {index + 1} needs a specific reason."
            ]
    return data, []


def _causal_phrases(text, report_lang):
    if report_lang == "en":
        folded = text.casefold()
        patterns = (
            r"(?:caused by|due to|because of|because|owing to|resulted from|"
            r"stemmed from|arose from|originated in|driven by|triggered by|"
            r"attributed to)\s+"
            r"([^.;,\n]{1,80})",
            rf"([^.;,\n]{{1,60}})\s+(?:{EN_CAUSAL_FORWARD})\s+",
        )
        return [
            re.sub(r"\s+", " ", match.group(1)).strip()
            for pattern in patterns
            for match in re.finditer(pattern, folded)
        ]
    patterns = (
        r"(?:是|由|因)([^，。；\n]{1,30})(?:所致|導致|导致|造成)",
        r"(?:由於|由于|因為|因为)([^，。；\n]{1,30})",
        r"([^，。；\n]{1,30})(?:導致|导致|造成|引發|引发)",
    )
    return [
        re.sub(r"\s+", "", match.group(1))
        for pattern in patterns
        for match in re.finditer(pattern, text)
    ]


@lru_cache(maxsize=4096)
def _clauses(text, report_lang):
    if report_lang == "en":
        parts = re.split(
            r"[.!?;,\n]+|\b(?:while|whereas|but)\b",
            text.casefold(),
        )
    else:
        parts = re.split(r"[。！？；，、,\n]+", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


@lru_cache(maxsize=8192)
def _anchor_tokens(clause, report_lang):
    stripped = clause.casefold()
    for left, right in DIRECTION_PAIRS:
        stripped = stripped.replace(left, " ").replace(right, " ")
    for token in NEGATIONS[report_lang]:
        stripped = stripped.replace(token.strip(), " ")
    if report_lang == "en":
        words = re.findall(r"[a-z0-9][a-z0-9'-]*", stripped)
        return {word for word in words if word not in EN_STOPWORDS}
    stripped = re.sub(
        r"(?:所致|導致|导致|造成|由於|由于|因為|因为|是|由|因)",
        "",
        stripped,
    )
    chars = "".join(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", stripped))
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[index : index + 2] for index in range(len(chars) - 1)}


@lru_cache(maxsize=8192)
def _raw_tokens(text, report_lang):
    if report_lang == "en":
        return {
            word
            for word in re.findall(r"[a-z0-9][a-z0-9'-]*", text.casefold())
            if word not in EN_STOPWORDS
        }
    chars = "".join(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", text))
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[index : index + 2] for index in range(len(chars) - 1)}


@lru_cache(maxsize=8192)
def _carrier_predicate_tokens(clause, report_lang):
    folded = clause.casefold()
    markers = [term for pair in DIRECTION_PAIRS for term in pair]
    markers.extend(token.strip() for token in NEGATIONS[report_lang])
    if report_lang == "en":
        markers.extend(
            (
                "caused by",
                "due to",
                "because of",
                "because",
                "owing to",
                "resulted from",
                "stemmed from",
                "arose from",
                "originated in",
                "driven by",
                "triggered by",
                "attributed to",
            )
        )
    else:
        markers.extend(("是", "由於", "由于", "因為", "因为", "所致"))
    positions = [
        (folded.find(marker), marker)
        for marker in markers
        if marker and folded.find(marker) > 0
    ]
    if positions:
        index, marker = min(positions)
        carrier = _raw_tokens(folded[:index], report_lang)
        predicate = _raw_tokens(
            folded[index + (0 if marker in _direction_terms(folded) else len(marker)) :],
            report_lang,
        )
        if carrier and predicate:
            return carrier, predicate

    if report_lang == "en":
        words = [
            word
            for word in re.findall(r"[a-z0-9][a-z0-9'-]*", folded)
            if word not in EN_STOPWORDS
        ]
        if len(words) >= 2:
            return set(words[:-1]), {words[-1]}
        return set(words), set()

    chars = "".join(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", folded))
    if len(chars) >= 4:
        return _raw_tokens(chars[:-2], report_lang), _raw_tokens(
            chars[-2:], report_lang
        )
    return _raw_tokens(chars, report_lang), set()


def _aligned_clauses(source, report, report_lang):
    source_clauses = _clauses(source, report_lang)
    report_clauses = _clauses(report, report_lang)

    # First pair clauses that survived editing byte-identically. Without this
    # pre-pass, an inserted or split sentence shifts clause indices and the
    # fuzzy matcher cross-pairs unchanged neighbours, producing false
    # negation/association findings on text the editor never touched.
    unmatched_report = {}
    for index, clause in enumerate(report_clauses):
        unmatched_report.setdefault(clause, []).append(index)
    identical = []
    leftover_source = []
    for source_index, source_clause in enumerate(source_clauses):
        positions = unmatched_report.get(source_clause)
        if positions:
            report_index = positions.pop(0)
            identical.append((source_index, report_index))
        else:
            leftover_source.append(source_index)
    matched_report = {report_index for _, report_index in identical}

    candidates = []
    report_count = max(1, len(report_clauses))
    source_count = max(1, len(source_clauses))
    for source_index in leftover_source:
        source_clause = source_clauses[source_index]
        source_carrier, _ = _carrier_predicate_tokens(
            source_clause, report_lang
        )
        source_tokens = source_carrier or _anchor_tokens(
            source_clause, report_lang
        )
        expected_index = round(source_index * report_count / source_count)
        nearby = range(
            max(0, expected_index - 6),
            min(report_count, expected_index + 7),
        )
        for report_index in nearby:
            if report_index in matched_report:
                continue
            report_clause = report_clauses[report_index]
            report_carrier, _ = _carrier_predicate_tokens(
                report_clause, report_lang
            )
            report_tokens = report_carrier or _anchor_tokens(
                report_clause, report_lang
            )
            if not source_tokens or not report_tokens:
                continue
            overlap = len(source_tokens & report_tokens) / min(
                len(source_tokens), len(report_tokens)
            )
            distance_penalty = abs(source_index - report_index) * 0.02
            candidates.append(
                (
                    overlap - distance_penalty,
                    source_index,
                    report_index,
                    source_clause,
                    report_clause,
                )
            )
    aligned = [
        (source_clauses[source_index], report_clauses[report_index], report_index)
        for source_index, report_index in identical
    ]
    used_source = set()
    used_report = set()
    for score, source_index, report_index, source_clause, report_clause in sorted(
        candidates, reverse=True
    ):
        if score < 0.34:
            continue
        if source_index in used_source or report_index in used_report:
            continue
        used_source.add(source_index)
        used_report.add(report_index)
        aligned.append((source_clause, report_clause, report_index))
    return aligned


@lru_cache(maxsize=8192)
def _direction_terms(clause):
    return {
        term
        for pair in DIRECTION_PAIRS
        for term in pair
        if (
            re.search(rf"\b{re.escape(term)}\b", clause)
            if term.isascii() and term.replace(" ", "").isalpha()
            else term in clause
        )
    }


def _has_negation(clause, report_lang):
    folded = clause.casefold()
    if report_lang == "en":
        return any(
            re.search(rf"\b{re.escape(token)}\b", folded)
            for token in NEGATIONS[report_lang]
        )
    return any(token in folded for token in NEGATIONS[report_lang])


def _predicate_is_negated(clause, predicate, report_lang):
    """Return whether a negation governs this predicate, not merely its clause."""
    folded = clause.casefold()
    if report_lang == "en":
        match = re.search(rf"\b{re.escape(predicate.casefold())}\b", folded)
        if match is None:
            return False
        prefix_words = re.findall(
            r"[a-z]+(?:n't)?", folded[max(0, match.start() - 36) : match.start()]
        )
        return any(
            token in NEGATIONS["en"]
            for token in prefix_words[-3:]
        )
    index = folded.find(predicate.casefold())
    if index < 0:
        return False
    prefix = folded[max(0, index - 6) : index]
    return any(token in prefix for token in NEGATIONS[report_lang])


def _checker_prose(text):
    """Return report-body prose for Rewild, preserving Markdown table cells."""
    try:
        from .report_blocks import visible_report_prose
    except ImportError:
        from report_blocks import visible_report_prose

    return visible_report_prose(text)


# Sentinels stand in for Markdown links while citation groups are matched.
# They are private-use characters, so they cannot occur in report prose.
_LINK_OPEN = "\ue000"
_LINK_CLOSE = "\ue001"
_LINK_SENTINEL = re.compile(f"{_LINK_OPEN}(\\d+){_LINK_CLOSE}")
_CITATION_GROUP = re.compile(
    rf"\s*\(\s*{_LINK_OPEN}\d+{_LINK_CLOSE}"
    rf"(?:\s*[;,]\s*{_LINK_OPEN}\d+{_LINK_CLOSE})*\s*\)"
)


def _markdown_link_spans(text):
    """Yield ``(start, end, label)`` for Markdown links, parens and all.

    A destination may itself contain balanced parentheses — Wikipedia titles
    such as ``.../Bar_(baz)`` are the common case — so the destination is
    scanned with a depth counter instead of being matched by a character
    class. A pattern that stops at the first ``)`` leaves the remainder of
    the URL and a stray bracket in the prose, which the clause aligner then
    reads as a claim.
    """
    spans = []
    for match in re.finditer(r"\]\(", text):
        label_start = text.rfind("[", 0, match.start())
        if label_start == -1:
            continue
        label = text[label_start + 1 : match.start()]
        if "[" in label or "]" in label:
            continue
        index = match.end()
        depth = 1
        escaped = False
        while index < len(text):
            char = text[index]
            index += 1
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
        else:
            continue
        if spans and label_start < spans[-1][1]:
            continue
        spans.append((label_start, index, label))
    return spans


def _fidelity_prose(text):
    """Checker prose with citation apparatus removed for clause comparison.

    Markdown citation groups such as ``([title](url); [title](url))`` split on
    commas and parentheses into clause fragments like ``codex changelog)``,
    which the aligner then treats as claims and flags whenever an edit
    reorders them. Citations are validated separately by validate_report, so
    the semantic comparison should see only the sentence prose around them.
    """
    try:
        from .report_blocks import mask_bibliography
    except ImportError:
        from report_blocks import mask_bibliography

    # Preserve bibliography classification before link destinations are
    # replaced by sentinels; the replacement is intentionally not valid
    # Markdown and therefore cannot itself be recognized as a source entry.
    text = mask_bibliography(text)

    # Strip citations from the raw Markdown BEFORE prose extraction: the
    # prose pass flattens links to their titles, after which citation groups
    # are indistinguishable from ordinary parentheticals. Links are replaced
    # by sentinels first so the group pattern never has to reason about the
    # parentheses inside a destination.
    labels = []
    pieces = []
    cursor = 0
    for start, end, label in _markdown_link_spans(text):
        pieces.append(text[cursor:start])
        pieces.append(f"{_LINK_OPEN}{len(labels)}{_LINK_CLOSE}")
        labels.append(label)
        cursor = end
    pieces.append(text[cursor:])
    marked = _CITATION_GROUP.sub("", "".join(pieces))
    text = _LINK_SENTINEL.sub(lambda match: labels[int(match.group(1))], marked)
    return _checker_prose(text)


def _causal_relation(clause, report_lang):
    """Return the causal (cause, effect) anchors expressed by one clause."""
    def effect_identity(effect):
        carrier, _ = _carrier_predicate_tokens(effect, report_lang)
        return carrier or _anchor_tokens(effect, report_lang)

    if report_lang == "en":
        match = re.search(
            r"(?P<effect>[^.;,\n]{1,120}?)\s+"
            r"(?P<marker>caused by|due to|because of|because|owing to|"
            r"resulted from|stemmed from|arose from|originated in|driven by|"
            r"triggered by|attributed to)\s+"
            r"(?P<cause>[^.;,\n]{1,120})",
            clause,
        )
        if match:
            if _predicate_is_negated(
                clause, match.group("marker"), report_lang
            ):
                return None
            return (
                _anchor_tokens(match.group("cause"), report_lang),
                effect_identity(match.group("effect")),
            )
        match = re.search(
            r"(?P<cause>[^.;,\n]{1,120}?)\s+"
            rf"(?P<marker>{EN_CAUSAL_FORWARD})\s+"
            r"(?P<effect>[^.;,\n]{1,120})",
            clause,
        )
        if match is None or _predicate_is_negated(
            clause, match.group("marker"), report_lang
        ):
            return None
        return (
            _anchor_tokens(match.group("cause"), report_lang),
            effect_identity(match.group("effect")),
        )
    match = re.search(
        r"(?P<effect>[^，。；\n]{1,50}?)(?:是|由|因)"
        r"(?P<cause>[^，。；\n]{1,50}?)(?:所致|導致|导致|造成)",
        clause,
    )
    if match:
        return (
            _anchor_tokens(match.group("cause"), report_lang),
            effect_identity(match.group("effect")),
        )
    match = re.search(
        r"(?P<effect>[^，。；\n]{1,50}?)(?:由於|由于|因為|因为)"
        r"(?P<cause>[^，。；\n]{1,50})",
        clause,
    )
    if match:
        return (
            _anchor_tokens(match.group("cause"), report_lang),
            effect_identity(match.group("effect")),
        )
    match = re.search(
        r"(?P<cause>[^，。；\n]{1,50}?)(?:導致|导致|造成|引發|引发)"
        r"(?P<effect>[^，。；\n]{1,50})",
        clause,
    )
    if match is None:
        return None
    return (
        _anchor_tokens(match.group("cause"), report_lang),
        effect_identity(match.group("effect")),
    )


def _causal_relations_compatible(source_relation, report_relation):
    """Require both the cause and the claimed effect to survive an edit."""
    if source_relation is None or report_relation is None:
        return False
    source_cause, source_effect = source_relation
    report_cause, report_effect = report_relation
    return bool(
        source_cause
        and source_effect
        and report_cause
        and report_effect
        and source_cause.intersection(report_cause)
        and source_effect.intersection(report_effect)
    )


def _clause_cause(clause, report_lang):
    """Compatibility helper for callers that only need cause presence."""
    relation = _causal_relation(clause, report_lang)
    return relation[0] if relation is not None else None


def _semantic_fidelity_errors(source, report, report_lang, exemptions=None):
    """Return semantic findings; append heuristic exemptions when requested.

    The split-remnant heuristics below excuse a narrow, structurally
    recognizable class of sentence-split artifacts. They are not silent:
    every excused finding is appended to ``exemptions`` (when a list is
    supplied) and the gate records them in the receipt for audit.
    """
    errors = []
    if exemptions is None:
        exemptions = []
    def contains(text, term):
        if term.isascii() and term.replace(" ", "").isalpha():
            return re.search(rf"\b{re.escape(term)}\b", text) is not None
        return term in text

    aligned = _aligned_clauses(source, report, report_lang)
    source_clauses = _clauses(source, report_lang)
    report_clauses = _clauses(report, report_lang)
    source_predicates = {
        frozenset(_carrier_predicate_tokens(clause, report_lang)[1])
        for clause in source_clauses
        if _carrier_predicate_tokens(clause, report_lang)[1]
    }

    for source_clause, report_clause, report_index in aligned:
        source_directions = _direction_terms(source_clause)
        report_directions = _direction_terms(report_clause)
        for left, right in DIRECTION_PAIRS:
            if left in source_directions and right in report_directions:
                errors.append(
                    "Semantic direction reversal in aligned claim: "
                    f"'{source_clause}' → '{report_clause}'."
                )
            if right in source_directions and left in report_directions:
                errors.append(
                    "Semantic direction reversal in aligned claim: "
                    f"'{source_clause}' → '{report_clause}'."
                )

        source_negated = _has_negation(source_clause, report_lang)
        report_negated = _has_negation(report_clause, report_lang)
        if source_negated != report_negated:
            # A sentence split cuts the source clause into exactly two
            # ordered pieces in reading order: the aligned clause must be
            # the prefix, and the clause immediately FOLLOWING it in the
            # report must equal the negated remainder. Substring membership
            # alone is not enough — an inner cut that strands a leading
            # negation flips scope, and a remnant placed before the prefix
            # reorders the negation relative to its content.
            split_moved_out = False
            if (
                source_negated
                and not report_negated
                and source_clause.startswith(report_clause)
                and report_index + 1 < len(report_clauses)
            ):
                residual = source_clause[len(report_clause) :].strip(
                    " \t,;:—–-"
                )
                split_moved_out = (
                    _has_negation(residual, report_lang)
                    and report_clauses[report_index + 1] == residual
                )
            if not split_moved_out:
                errors.append(
                    "Semantic negation changed in aligned claim: "
                    f"'{source_clause}' → '{report_clause}'."
                )
            else:
                exemptions.append(
                    "Negation excused as adjacent split remnant: "
                    f"'{source_clause}' → '{report_clause}'."
                )

        source_relation = _causal_relation(source_clause, report_lang)
        report_relation = _causal_relation(report_clause, report_lang)
        if source_relation is None and report_relation is not None:
            errors.append(
                "Causal claim added in aligned claim: "
                f"'{source_clause}' → '{report_clause}'."
            )
        elif (
            source_relation is not None
            and report_relation is not None
            and not _causal_relations_compatible(
                source_relation, report_relation
            )
        ):
            errors.append(
                "Causal substitution detected in aligned claim: "
                f"'{source_clause}' → '{report_clause}'."
            )

        _, source_predicate = _carrier_predicate_tokens(
            source_clause, report_lang
        )
        _, report_predicate = _carrier_predicate_tokens(
            report_clause, report_lang
        )
        if source_predicate and report_predicate:
            own_overlap = len(source_predicate & report_predicate) / min(
                len(source_predicate), len(report_predicate)
            )
            other_overlap = max(
                (
                    len(predicate & report_predicate)
                    / min(len(predicate), len(report_predicate))
                    for predicate in source_predicates
                    if predicate and predicate != source_predicate
                ),
                default=0,
            )
            if own_overlap < 0.34 and other_overlap >= 0.75:
                # A split remnant is the PREFIX of its source clause, and the
                # trimmed tail must be the very next clause in the report —
                # the same rule the negation exemption applies above. Plain
                # substring containment excused far too much: an inner cut,
                # a reordering, or a remnant re-attached to a different
                # carrier elsewhere in the document all "contain" and would
                # have been waived without any adjacency or ordering test.
                split_remnant = False
                if source_clause.startswith(report_clause):
                    residual = source_clause[len(report_clause) :].strip(
                        " \t,;:—–-"
                    )
                    split_remnant = bool(residual) and (
                        report_index + 1 < len(report_clauses)
                        and report_clauses[report_index + 1] == residual
                    )
                if not split_remnant:
                    errors.append(
                        "Semantic predicate association moved to another claim: "
                        f"'{source_clause}' → '{report_clause}'."
                    )
                else:
                    exemptions.append(
                        "Association excused as split remnant subset: "
                        f"'{source_clause}' → '{report_clause}'."
                    )

    # Document-level comparison compares term co-occurrence across the whole
    # text and cannot tell which claim a term belongs to, so it is sound only
    # while clause alignment explains almost nothing. The trigger is coverage,
    # not "nothing aligned": the identical-clause pre-pass pairs any surviving
    # boilerplate line, so a wholesale rewrite that keeps one heading fragment
    # used to switch this backstop off entirely.
    source_clause_count = len(source_clauses)
    coverage = len(aligned) / max(
        1, min(source_clause_count, len(report_clauses))
    )
    if coverage <= DOCUMENT_FALLBACK_COVERAGE:
        fallback_source = source
        fallback_report = report
        comparison_source_clauses = source_clauses
        comparison_report_clauses = report_clauses
        compare_fallback_directions = True
    else:
        # Broad alignment must not hide one entirely rewritten clause. Compare
        # the residual clauses as their own mini-document: this keeps the
        # whole-text backstop precise without letting nine preserved clauses
        # excuse a fabricated causal or reversed directional assertion in the
        # tenth.
        unmatched_source = list(source_clauses)
        matched_report_indexes = set()
        for source_clause, _, report_index in aligned:
            with suppress(ValueError):
                unmatched_source.remove(source_clause)
            matched_report_indexes.add(report_index)
        unmatched_report = [
            clause
            for index, clause in enumerate(report_clauses)
            if index not in matched_report_indexes
        ]
        fallback_source = " ".join(unmatched_source)
        fallback_report = " ".join(unmatched_report)
        comparison_source_clauses = unmatched_source
        comparison_report_clauses = unmatched_report
        source_residual_carriers = {
            token
            for clause in unmatched_source
            for token in _carrier_predicate_tokens(clause, report_lang)[0]
        }
        report_residual_carriers = {
            token
            for clause in unmatched_report
            for token in _carrier_predicate_tokens(clause, report_lang)[0]
        }
        compare_fallback_directions = bool(
            source_residual_carriers & report_residual_carriers
        )

    if fallback_report:
        fallback_source_folded = f" {fallback_source.casefold()} "
        fallback_report_folded = f" {fallback_report.casefold()} "
        for left, right in DIRECTION_PAIRS if compare_fallback_directions else ():
            source_left = contains(fallback_source_folded, left)
            source_right = contains(fallback_source_folded, right)
            report_left = contains(fallback_report_folded, left)
            report_right = contains(fallback_report_folded, right)
            if source_left and not source_right and report_right and not report_left:
                errors.append(
                    f"Semantic direction reversal: source uses '{left}', "
                    f"report uses '{right}'."
                )
            if source_right and not source_left and report_left and not report_right:
                errors.append(
                    f"Semantic direction reversal: source uses '{right}', "
                    f"report uses '{left}'."
                )
        source_relations = [
            relation
            for clause in comparison_source_clauses
            if (relation := _causal_relation(clause, report_lang)) is not None
        ]
        report_relations = [
            relation
            for clause in comparison_report_clauses
            if (relation := _causal_relation(clause, report_lang)) is not None
        ]
        added_cause = any(
            not any(
                _causal_relations_compatible(source_relation, report_relation)
                for source_relation in source_relations
            )
            for report_relation in report_relations
        )
        if added_cause:
            errors.append(
                "Causal claim added in unmatched claim."
                if coverage > DOCUMENT_FALLBACK_COVERAGE
                else "Causal claim added where the pre-Rewild report had none."
            )
        if coverage > DOCUMENT_FALLBACK_COVERAGE:
            for report_clause in unmatched_report:
                directions = _direction_terms(report_clause)
                asserted_directions = {
                    direction
                    for direction in directions
                    if not _predicate_is_negated(
                        report_clause, direction, report_lang
                    )
                }
                if asserted_directions:
                    errors.append(
                        "Unmatched directional claim added or replaced: "
                        f"'{report_clause}'."
                    )
    return errors


def _length_errors(text, report_lang):
    try:
        from .validate_report import (
            _h2_sections,
            _report_prose,
            detect_language,
            simplified_script_errors,
        )
    except ImportError:
        from validate_report import (
            _h2_sections,
            _report_prose,
            detect_language,
            simplified_script_errors,
        )

    prose = _report_prose(text, _h2_sections(text))
    detected = detect_language(prose)
    chinese_ambiguous = detected == "zh" and report_lang.startswith("zh-")
    if detected != report_lang and not chinese_ambiguous:
        return [
            f"Rewild report language is {detected}; expected {report_lang}."
        ]
    errors = []
    if report_lang == "zh-CN":
        errors.extend(
            simplified_script_errors(
                text,
                sections=_h2_sections(text),
            )
        )
    try:
        from .report_contract import report_length_policy
    except ImportError:
        from report_contract import report_length_policy

    if report_lang == "en":
        count = len(re.findall(r"\b[\w'-]+\b", prose, re.UNICODE))
    else:
        count = len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", prose))
    minimum, maximum, unit = report_length_policy(report_lang)
    if count < minimum:
        errors.append(
            f"Rewild report has {count} {unit}; minimum is {minimum}."
        )
    if count > maximum:
        errors.append(
            f"Rewild report has {count} {unit}; maximum is {maximum}."
        )
    return errors


def run_gate(
    report_path,
    source_path,
    *,
    report_lang,
    review_note_path,
    receipt_path,
    waiver_path=None,
    fidelity_notes_path=None,
    force=False,
):
    """Return errors; write a receipt only after the exact report passes."""
    report_path = Path(report_path).resolve()
    source_path = Path(source_path).resolve()
    review_note_path = Path(review_note_path).resolve()
    receipt_path = Path(receipt_path).resolve()
    errors = artifact_collision_errors(
        {
            "final report": report_path,
            "pre-Rewild source": source_path,
            "blind-review note": review_note_path,
            "style waivers": waiver_path,
            "fidelity notes": fidelity_notes_path,
        },
        {"Rewild receipt": receipt_path},
    )
    if errors:
        return errors
    if receipt_path.exists() and not force:
        return [
            f"Rewild receipt already exists: {receipt_path}. "
            "Use --force to replace it."
        ]
    if report_lang not in PROFILES:
        return [f"Unsupported report language: {report_lang}"]
    for label, path in (
        ("report", report_path),
        ("pre-Rewild source", source_path),
        ("blind-review note", review_note_path),
    ):
        if not path.is_file():
            errors.append(f"{label} file is missing: {path}")
    if errors:
        return errors
    texts = {}
    for label, path in (
        ("report", report_path),
        ("pre-Rewild source", source_path),
    ):
        try:
            texts[label] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A mis-encoded draft is an ordinary authoring mistake; it must
            # read as a gate failure, not as an uncaught traceback.
            errors.append(f"{label} file must be UTF-8 text: {exc}")
    if errors:
        return errors
    report_text = texts["report"]
    source_text = texts["pre-Rewild source"]
    review_note, review_errors = _load_review_note(
        review_note_path,
        report_path=report_path,
        source_path=source_path,
        report_lang=report_lang,
    )
    if review_errors:
        return review_errors
    if file_sha256(report_path) == file_sha256(source_path) and any(
        isinstance(finding, dict)
        and finding.get("disposition") == "resolved"
        for finding in review_note.get("findings", [])
    ):
        return [
            "Pre-Rewild source and final report are identical, but the "
            "review note claims resolved findings."
        ]
    heuristic_exemptions = []
    semantic_errors = _semantic_fidelity_errors(
        _fidelity_prose(source_text),
        _fidelity_prose(report_text),
        report_lang,
        exemptions=heuristic_exemptions,
    )
    if len(heuristic_exemptions) > MAX_HEURISTIC_EXEMPTIONS:
        return [
            f"{len(heuristic_exemptions)} heuristic split-remnant exemptions "
            f"exceed the limit of {MAX_HEURISTIC_EXEMPTIONS}; a report with "
            "this much structural churn must be re-checked against the "
            "pre-Rewild source and re-drafted, not exempted."
        ]
    try:
        fidelity_notes, note_errors = _load_fidelity_notes(fidelity_notes_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"Fidelity notes must be valid UTF-8 JSON: {exc}"]
    if note_errors:
        return note_errors
    fidelity_note_ok = any(
        isinstance(finding, dict)
        and finding.get("category") == "fidelity"
        and finding.get("disposition") == "resolved"
        for finding in review_note.get("findings", [])
    )
    if fidelity_notes and not fidelity_note_ok:
        return [
            "Fidelity notes require at least one resolved fidelity finding "
            "in the bound blind-review note."
        ]
    # The per-report budget is enforced once, in _load_fidelity_notes, so an
    # oversized file is rejected before any of it is trusted.
    source_prose = _fidelity_prose(source_text)
    report_prose = _fidelity_prose(report_text)
    for note in fidelity_notes:
        if not _fragment_matches(note["source_fragment"], source_prose):
            return [
                "Fidelity note source fragment is not in the pre-Rewild "
                f"source: '{note['source_fragment']}'."
            ]
        if not _fragment_matches(note["report_fragment"], report_prose):
            return [
                "Fidelity note report fragment is not in the report: "
                f"'{note['report_fragment']}'."
            ]
    semantic_errors, acknowledged_findings, unused_notes = _apply_fidelity_notes(
        semantic_errors, fidelity_notes
    )
    if len(acknowledged_findings) > MAX_FIDELITY_NOTES:
        return [
            f"Fidelity notes acknowledged {len(acknowledged_findings)} "
            f"semantic findings, above the limit of {MAX_FIDELITY_NOTES}; "
            "a report changing meaning this often must be re-drafted."
        ]
    errors.extend(semantic_errors)
    errors.extend(
        "Fidelity note matched no semantic finding: "
        f"'{note['source_fragment']}' → '{note['report_fragment']}'."
        for note in unused_notes
    )
    errors.extend(_length_errors(report_text, report_lang))

    profile, checker_lang = PROFILES[report_lang]
    checker = (
        ROOT
        / "references"
        / "rewild"
        / profile
        / "scripts"
        / "naturalness-check.py"
    )
    with tempfile.TemporaryDirectory(prefix="alexandria-rewild-") as directory:
        checker_report = Path(directory) / "report-body.txt"
        checker_source = Path(directory) / "pre-rewild-body.txt"
        checker_report.write_text(_checker_prose(report_text), encoding="utf-8")
        checker_source.write_text(_checker_prose(source_text), encoding="utf-8")
        command = [
            sys.executable,
            str(checker),
            str(checker_report),
            "--source",
            str(checker_source),
            "--lang",
            checker_lang,
            "--json",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return ["Rewild checker timed out after 300 seconds."]
    try:
        result = _checker_result(completed.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return [f"Rewild checker failed: {exc}. {detail}"]

    warnings = result.get("warnings", [])
    # The checker exits 0 with a clean report and 1 when it raised warnings;
    # anything else means it stopped early, crashed, or was killed, and its
    # JSON describes a partial analysis. Trusting an empty warning list from
    # such a run would pass the gate on work that never finished.
    expected_returncode = 1 if warnings else 0
    if completed.returncode != expected_returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return [
            f"Rewild checker exited with status {completed.returncode} after "
            f"reporting {len(warnings)} warning(s); its analysis is "
            f"incomplete. {detail}".strip()
        ]
    hard_warnings = [
        warning
        for warning in warnings
        if str(warning.get("section", "")).startswith(
            ("Fidelity", "Region", "AI vocabulary")
        )
        or (
            report_lang == "zh-HK"
            and str(warning.get("section", "")).startswith("Hong Kong flavor")
        )
    ]
    if hard_warnings:
        errors.extend(
            [
            "Hard Rewild warning remains: "
            f"{warning.get('section')}: {warning.get('message')}"
            for warning in hard_warnings
            ]
        )
    if report_lang == "zh-HK":
        hk_lines = [
            line
            for section in result.get("sections", [])
            if str(section.get("title", "")).startswith("Hong Kong flavor")
            for line in section.get("lines", [])
        ]
        for line in hk_lines:
            message = str(line.get("message", ""))
            if "register reads as " in message and "書面語 (" not in message:
                errors.append(
                    "Hard Rewild warning remains: Hong Kong report register "
                    f"is not standard written Chinese: {message}"
                )
            if message.startswith("Cantonese potential complements"):
                errors.append(
                    "Hard Rewild warning remains: Cantonese syntax in a "
                    f"professional Hong Kong report: {message}"
                )
    if errors:
        return errors

    try:
        waivers, waiver_errors = _load_style_waivers(waiver_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"Style-waiver file could not be read: {exc}"]
    if waiver_errors:
        return waiver_errors
    style_warnings = [
        warning for warning in warnings if warning not in hard_warnings
    ]
    missing_waivers = [
        warning
        for warning in style_warnings
        if (
            str(warning.get("section", "")),
            str(warning.get("message", "")),
        )
        not in waivers
    ]
    if missing_waivers:
        return [
            "Unresolved style warning: "
            f"{warning.get('section')}: {warning.get('message')}"
            for warning in missing_waivers
        ]

    receipt = {
        "schema_version": 1,
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "report_lang": report_lang,
        "checker_lang": checker_lang,
        "report_path": str(report_path),
        "report_sha256": file_sha256(report_path),
        "source_path": str(source_path),
        "source_sha256": file_sha256(source_path),
        "checker_path": str(checker),
        "checker_sha256": file_sha256(checker),
        "review_note_path": str(review_note_path),
        "review_note_sha256": file_sha256(review_note_path),
        "review_status": review_note["status"],
        "style_waivers": [
            {
                "section": warning.get("section"),
                "message": warning.get("message"),
                "reason": waivers[
                    (
                        str(warning.get("section", "")),
                        str(warning.get("message", "")),
                    )
                ],
            }
            for warning in style_warnings
        ],
        "fidelity_notes_path": (
            str(Path(fidelity_notes_path).resolve())
            if fidelity_notes_path
            else None
        ),
        "fidelity_notes_sha256": (
            file_sha256(fidelity_notes_path) if fidelity_notes_path else None
        ),
        "fidelity_notes": acknowledged_findings,
        "heuristic_exemptions": heuristic_exemptions,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=receipt_path.parent,
            prefix=f".{receipt_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(receipt, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(receipt_path)
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise
    return []


def build_parser():
    parser = argparse.ArgumentParser(description="Run Alexandria's Rewild gate")
    parser.add_argument("report", help="edited report Markdown")
    parser.add_argument("--source", required=True, help="pre-Rewild report Markdown")
    parser.add_argument("--lang", required=True, choices=PROFILES)
    parser.add_argument(
        "--review-note",
        required=True,
        help="blind-review findings and dispositions",
    )
    parser.add_argument("--style-waivers", help="JSON reasons for retained warnings")
    parser.add_argument(
        "--fidelity-notes",
        help="JSON acknowledgments for review-mandated intentional edits",
    )
    parser.add_argument("--receipt", required=True, help="gate receipt JSON to write")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing Rewild receipt",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    errors = run_gate(
        args.report,
        args.source,
        report_lang=args.lang,
        review_note_path=args.review_note,
        receipt_path=args.receipt,
        waiver_path=args.style_waivers,
        fidelity_notes_path=args.fidelity_notes,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(
                _console_safe(f"[FAIL] {error}", sys.stderr),
                file=sys.stderr,
            )
        return 1
    print(
        _console_safe(
            f"[OK] Rewild gate passed: {Path(args.receipt).resolve()}",
            sys.stdout,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
