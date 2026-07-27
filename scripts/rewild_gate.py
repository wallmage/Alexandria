#!/usr/bin/env python3
"""Run Alexandria's bundled Rewild checker and issue a file-bound receipt."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


def _checker_result(stdout):
    marker = stdout.rfind("\n{")
    if marker < 0:
        raise ValueError("checker did not emit its JSON result")
    return json.loads(stdout[marker + 1 :])


def _load_style_waivers(path):
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("style_waivers", []) if isinstance(data, dict) else []
    waivers = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        section = str(entry.get("section", "")).strip()
        message = str(entry.get("message", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        if section and message and len(reason) >= 10:
            waivers[(section, message)] = reason
    return waivers


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


def _clauses(text, report_lang):
    if report_lang == "en":
        parts = re.split(
            r"[.!?;,\n]+|\b(?:while|whereas|but)\b",
            text.casefold(),
        )
    else:
        parts = re.split(r"[。！？；，、,\n]+", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


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
    candidates = []
    report_count = max(1, len(report_clauses))
    source_count = max(1, len(source_clauses))
    for source_index, source_clause in enumerate(source_clauses):
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
    aligned = []
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
        aligned.append((source_clause, report_clause))
    return aligned


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


def _checker_prose(text):
    """Return report-body prose for Rewild, preserving Markdown table cells."""
    try:
        from .validate_report import _h2_sections, _report_prose
    except ImportError:
        from validate_report import _h2_sections, _report_prose

    prose = _report_prose(text, _h2_sections(text))
    return re.sub(
        r"(?m)^\s*:?-{3,}:?(?:\s+:?-{3,}:?)+\s*$",
        "",
        prose,
    )


def _clause_cause(clause, report_lang):
    if report_lang == "en":
        match = re.search(
            r"(?:caused by|due to|because of|because|owing to|resulted from|"
            r"stemmed from|arose from|originated in|driven by|triggered by|"
            r"attributed to)\s+"
            r"([^.;,\n]{1,80})",
            clause,
        )
        if match:
            return match.group(1).strip()
        match = re.search(
            r"([^.;,\n]{1,60})\s+"
            rf"(?:{EN_CAUSAL_FORWARD})\s+",
            clause,
        )
        return match.group(1).strip() if match else None
    match = re.search(
        r"(?:是|由|因)([^，。；\n]{1,30})(?:所致|導致|导致|造成)",
        clause,
    )
    if match:
        return match.group(1).strip()
    match = re.search(r"(?:由於|由于|因為|因为)([^，。；\n]{1,30})", clause)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"([^，。；\n]{1,30})(?:導致|导致|造成|引發|引发)",
        clause,
    )
    return match.group(1).strip() if match else None


def _semantic_fidelity_errors(source, report, report_lang):
    errors = []
    source_folded = f" {source.casefold()} "
    report_folded = f" {report.casefold()} "

    def contains(text, term):
        if term.isascii() and term.replace(" ", "").isalpha():
            return re.search(rf"\b{re.escape(term)}\b", text) is not None
        return term in text

    aligned = _aligned_clauses(source, report, report_lang)
    source_predicates = {
        frozenset(_carrier_predicate_tokens(clause, report_lang)[1])
        for clause in _clauses(source, report_lang)
        if _carrier_predicate_tokens(clause, report_lang)[1]
    }
    for source_clause, report_clause in aligned:
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
            errors.append(
                "Semantic negation changed in aligned claim: "
                f"'{source_clause}' → '{report_clause}'."
            )

        source_cause = _clause_cause(source_clause, report_lang)
        report_cause = _clause_cause(report_clause, report_lang)
        if source_cause is None and report_cause is not None:
            errors.append(
                "Causal claim added in aligned claim: "
                f"'{source_clause}' → '{report_clause}'."
            )
        elif source_cause is not None and report_cause is not None:
            source_tokens = _anchor_tokens(source_cause, report_lang)
            report_tokens = _anchor_tokens(report_cause, report_lang)
            if not source_tokens or not report_tokens or not (
                source_tokens & report_tokens
            ):
                errors.append(
                    "Causal substitution detected in aligned claim: "
                    f"'{source_cause}' → '{report_cause}'."
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
                errors.append(
                    "Semantic predicate association moved to another claim: "
                    f"'{source_clause}' → '{report_clause}'."
                )

    # Fallback for a short or heavily rephrased passage that could not be
    # aligned. These document-level checks are weaker but still catch a lone
    # reversal, added negation, or invented cause.
    for left, right in DIRECTION_PAIRS:
        source_left = contains(source_folded, left)
        source_right = contains(source_folded, right)
        report_left = contains(report_folded, left)
        report_right = contains(report_folded, right)
        if source_left and not source_right and report_right:
            errors.append(
                f"Semantic direction reversal: source uses '{left}', "
                f"report uses '{right}'."
            )
        if source_right and not source_left and report_left:
            errors.append(
                f"Semantic direction reversal: source uses '{right}', "
                f"report uses '{left}'."
            )
    source_causes = _causal_phrases(source, report_lang)
    report_causes = _causal_phrases(report, report_lang)
    if report_causes and not source_causes:
        errors.append("Causal claim added where the pre-Rewild report had none.")
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
    if report_lang == "en":
        count = len(re.findall(r"\b[\w'-]+\b", prose, re.UNICODE))
        minimum, maximum, unit = 7500, 15000, "words"
    else:
        count = len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", prose))
        minimum, maximum, unit = 5000, 10000, "report-body characters"
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
):
    """Return errors; write a receipt only after the exact report passes."""
    report_path = Path(report_path).resolve()
    source_path = Path(source_path).resolve()
    review_note_path = Path(review_note_path).resolve()
    receipt_path = Path(receipt_path).resolve()
    receipt_path.unlink(missing_ok=True)

    errors = []
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
    report_text = report_path.read_text(encoding="utf-8")
    source_text = source_path.read_text(encoding="utf-8")
    review_note, review_errors = _load_review_note(
        review_note_path,
        report_path=report_path,
        source_path=source_path,
        report_lang=report_lang,
    )
    if review_errors:
        return review_errors
    errors.extend(
        _semantic_fidelity_errors(source_text, report_text, report_lang)
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
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    try:
        result = _checker_result(completed.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return [f"Rewild checker failed: {exc}. {detail}"]

    warnings = result.get("warnings", [])
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
        waivers = _load_style_waivers(waiver_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Style-waiver file could not be read: {exc}"]
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
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
    parser.add_argument("--receipt", required=True, help="gate receipt JSON to write")
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
    )
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[OK] Rewild gate passed: {Path(args.receipt).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
