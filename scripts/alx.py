#!/usr/bin/env python3
"""Alexandria's single entry point: one CLI over the research gates.

`alx` is thin orchestration over the existing modules used as libraries
(spec 09-14-01 §5). Free text enters only through files; every command
appends one worklog line and prints the elapsed/remaining footer last.
"""

import argparse
import glob
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The host can start `alx` with a bare interpreter that has none of the
#: rendering or validation packages. Discovery and relocation use stdlib only
#: and run before any of them is needed.
RUNTIME_PACKAGES = ("jsonschema", "weasyprint", "pypdf", "pypdfium2", "markdown", "PIL")
RUNTIME_MISSING = (
    "RUNTIME MISSING — install it: sh {root}/scripts/install.sh"
    "   (Windows: & '{root}\\scripts\\install.ps1'), then rerun this command. "
    "Never pip-install into a host interpreter."
)


def runtime_directory():
    """$ALEXANDRIA_RUNTIME_DIR, else ~/.alexandria/runtime."""
    return Path(os.environ.get("ALEXANDRIA_RUNTIME_DIR") or Path.home() / ".alexandria/runtime")


def runtime_command():
    """The managed interpreter invocation, or None when no runtime is installed.

    The manifest install_runtime.py writes lives in the runtime first and next
    to SKILL.md second: refreshing the installed skill copy deletes the latter.
    """
    runtime = runtime_directory()
    # micromamba.exe aborts on its second start when no root prefix is set;
    # the installer pins the runtime's own, so every relocation does too.
    os.environ.setdefault("MAMBA_ROOT_PREFIX", str(runtime / "mamba"))
    for manifest in (runtime / ".runtime.json", ROOT / ".runtime.json"):
        if manifest.is_file():
            command = json.loads(manifest.read_text(encoding="utf-8"))["command"]
            return [str(item) for item in command]
    windows = sys.platform == "win32"
    mamba = runtime / ("Library/bin/micromamba.exe" if windows else "bin/micromamba")
    if mamba.is_file():
        return [str(mamba), "--no-rc", "run", "--prefix", str(runtime / "env"), "python"]
    python = runtime / ("env/python.exe" if windows else "env/bin/python")
    if python.is_file():
        return [str(python)]
    return None


def runtime_packages_present():
    return all(importlib.util.find_spec(name) is not None for name in RUNTIME_PACKAGES)


def relocate(argv):
    """Re-run this command under the managed runtime; None means run here."""
    if os.environ.get("ALEXANDRIA_REEXEC") == "1":
        return None
    if sys.version_info >= (3, 10) and runtime_packages_present():
        return None
    command = runtime_command()
    if command is None:
        print(RUNTIME_MISSING.format(root=ROOT), file=sys.stderr)
        return 2
    print(f"alx: relocating to managed runtime {command[0]}", file=sys.stderr)
    return subprocess.run(
        command + [str(Path(__file__).resolve()), *argv],
        env={**os.environ, "ALEXANDRIA_REEXEC": "1"},
        check=False,
    ).returncode


# Before importing skill modules: a host interpreter older than 3.10 cannot
# even import them, so relocation must happen here, not in main().
if __name__ == "__main__":
    _code = relocate(sys.argv[1:])
    if _code is not None:
        sys.exit(_code)

from scripts import (  # noqa: E402
    content_gate,
    gate_severity,
    report_blocks,
    report_contract,
    rewild_gate,
    source_fidelity,
    validate_ledger,
    validate_report,
)

LANGUAGES = ("en", "zh-CN", "zh-HK")
ARCHETYPES = (
    "person",
    "organization",
    "artifact",
    "event",
    "concept",
    "system",
    "hybrid",
)
PROVENANCES = (
    "primary_independent",
    "primary_interested",
    "secondary_independent",
    "secondary_dependent",
    "unverified",
)
EVIDENCE_TYPES = (
    "accountable_record",
    "peer_reviewed",
    "preprint",
    "official_documentation",
    "dataset_or_test",
    "reported_interview",
    "news_report",
    "opinion_or_forecast",
    "marketing",
    "anecdote",
)
SOURCE_ROLES = (
    "subject_official",
    "counterparty_official",
    "independent_analysis",
    "empirical_data",
    "affected_stakeholder",
    "expert_interpretation",
    "historical_record",
)
ACCOUNTABILITY_BASES = (
    "none",
    "court_or_regulator_record",
    "named_source_investigation",
    "subject_admission",
)
REVIEW_KINDS = ("rewild", "content")

CONTENT_SCORE_KEYS = (
    "question_answered",
    "evidence_strength",
    "evidence_coverage",
    "reasoning_integrity",
    "counterevidence",
    "explanatory_depth",
    "decision_value",
    "writing_clarity",
)
CONTENT_CHECK_KEYS = (
    "central_judgment_answers_question",
    "priority_coverage_resolved",
    "key_claims_traceable",
    "source_independence_calibrated",
    "counterevidence_tested",
    "uncertainty_visible",
    "recommendations_or_implications_supported",
    "forecasts_conditional",
    "section_value_density_reviewed",
    "length_is_substantive_not_padded",
)

#: J10: `report_blocks` owns the note prefixes so the rewild/content checks can
#: mask the machine-written note. The literal stays as the fallback until that
#: export lands.
VERIFICATION_NOTE_PREFIX = getattr(
    report_blocks,
    "VERIFICATION_NOTE_PREFIXES",
    {
        "en": "Verification note:",
        "zh-CN": "核查说明：",
        "zh-HK": "核實說明：",
    },
)

#: Every printed remedy (spec D14, ruling R6). Commands parse; the rest are the
#: closed imperative list of spec §6 plus the two length imperatives of R6.
REMEDY_TEMPLATES = {
    "fetch-refresh": "alx fetch --id {source_id} --refresh",
    "fetch-url": "alx fetch {url}",
    "claim-add": "alx claim add {file}",
    "claim-drop": "alx claim drop {claim_id} --apply",
    "claim-bind": "alx claim bind {claim_id}:{paragraph}",
    "source-set-url": "alx source set {source_id} --url {url}",
    "ledger-merge": "alx ledger merge {file}",
    "source-set": "alx source set {source_id} --provenance primary_independent",
    "source-family-justification": (
        "alx source set {source_id} --family-justification family-justification.txt"
    ),
    "find": "alx find {source_id} {keyword}",
    "snapshot-restore": "alx snapshot --restore",
    "review-start": "alx review start {kind}",
    "review-iter": "alx review start {kind} --iter",
    "review-stale": "re-read the changed paragraphs, then alx review finish {kind}",
    "review-quality": (
        "edit reviews/content.json (raise the score / set checks true / "
        "fill sections / disposition fixed / excerpt ≥40 chars from "
        "report.md), then alx review finish content"
    ),
    "checker-timeout": "alx check again — the checker has a 120 s budget",
    "check": "alx check",
    "check-fix": "alx check --fix",
    "issue": "alx issue",
    "render": "alx render",
    "set-field": "set field {field} in {file}",
    # Addendum 6: a claim field re-enters the ledger only through `claim add`.
    "set-field-claim": "set field {field} in {file}, then alx claim add {file}",
    # J4: a refresh alone leaves the recorded probe contexts behind; only
    # `claim add` re-binds them, so the remedy is the two-step sequence.
    "refresh-rebind": "alx fetch --id {source_id}, then alx claim add {file}",
    "extend-quote": "extend the quote in {file}",
    "paste-passage": (
        "paste the closest passage as extract_or_location in {file}, "
        "or alx find {source_id} {keyword}"
    ),
    "extend-report": "extend the report body in report.md",
    "delete-paragraph": "delete paragraph {paragraph} of report.md",
    "remove-link": "remove link {url} from report.md",
    "edit-prose": "(edit prose; warning, never blocks)",
    # Ruling R9: inserting a link leaves the visible text unchanged, so it is a
    # mechanical delta and never stales a review.
    "add-link": (
        "write [{claim_id}] at the end of the sentence in paragraph "
        "{paragraph} of report.md, then alx check --fix"
    ),
    "add-link-claim": (
        "write [{claim_id}] at the end of the sentence that states claim "
        "{claim_id} in report.md, then alx check --fix"
    ),
}

#: Ruling R8 plus spec §6's closed imperative list: what a printed remedy may
#: say when it is not an `alx` command.
CLOSED_IMPERATIVES = (
    re.compile(r"^set field \S+ in \S+$"),
    re.compile(r"^set field \S+ in \S+, then alx claim add \S+$"),
    # J2: a brief/people/coverage/synthesis field re-enters through the merge.
    re.compile(r"^set field \S+ in \S+ via alx ledger merge$"),
    # R23: a synthesis field names no claim file; the merge is the whole repair.
    re.compile(r"^set field \S+, then alx ledger merge \S+$"),
    re.compile(r"^alx fetch --id S\d+, then alx claim add \S+$"),
    # A month-day extract cannot be found under the claim's full date: the
    # repair is a second extract stating the year, or the source's own wording.
    re.compile(
        r"^add a second extract from S\d+ that states the year "
        r"\(alx find S\d+ [^()]+\), or reword the claim to the source's "
        r"form \(.+\)$"
    ),
    re.compile(r"^extend the quote in \S+$"),
    re.compile(
        r"^paste the closest passage as extract_or_location in \S+, "
        r"or alx find S\d+ \S+$"
    ),
    re.compile(r"^re-read the changed paragraphs, then alx review finish \S+$"),
    re.compile(
        r"^edit reviews/content\.json \(raise the score / set checks true / "
        r"fill sections / disposition fixed / excerpt ≥40 chars from "
        r"report\.md\), then alx review finish content$"
    ),
    re.compile(r"^alx check again — the checker has a 120 s budget$"),
    re.compile(r"^alx claim bind C\d+:<paragraph>$"),
    re.compile(r"^.+ not rendered:.+$"),
    re.compile(r"^.*must be readable UTF-8 text:.*$"),
    re.compile(r"^Unsupported report language: .+$"),
    re.compile(r"^extend the report body in report\.md$"),
    re.compile(r"^delete paragraph \d+ of report\.md$"),
    re.compile(r"^remove link \S+ from report\.md$"),
    re.compile(r"^\(edit prose; warning, never blocks\)$"),
    re.compile(
        r"^write \[C\d+\] at the end of the sentence in paragraph \d+ of "
        r"report\.md, then alx check --fix$"
    ),
    re.compile(
        r"^write \[C\d+\] at the end of the sentence that states claim C\d+ "
        r"in report\.md, then alx check --fix$"
    ),
    re.compile(
        r"^cite the nearest ledger URL instead \(alx check --fix rewrites it when "
        r"only www\. or the domain suffix differs\); a page you did not fetch must "
        r"be fetched first$"
    ),
)

#: Class A families for the findings `alx` itself emits (spec §6.10); every
#: other hard family of its own defaults to Class F. Findings produced by
#: another module carry their own `klass` and are never re-classed here.
#: `integrity/length` is split by severity: below the floor it arrives as a
#: warning (Class A), above the ceiling it is hard and therefore Class F with a
#: `delete paragraph` remedy.
CLASS_A_FAMILIES = frozenset(
    {
        "tooling/receipt",
        "tooling/render",
        "review/rewild",
        "rewild/checker",
        "integrity/structure",
        "integrity/date-line",
        "binding/sources-section",
    }
)

#: Ruling R10: the spec §6.7 mechanical-repair list is the whitelist for
#: printing `Fix: alx check --fix`. A finding of any other family may not
#: advertise it, whichever module wrote the remedy, because `--fix` repairs
#: nothing there and a weak model would simply re-run it. `Fix: alx check`
#: (bare) is never an honest remedy for anything.
MECHANICAL_FIX_FAMILIES = frozenset(
    {
        "ledger/source-ids",  # source_ids derived from source_evidence
        "ledger/person",  # person_ids derived from registered names (R15)
        "ledger/source-family",  # source_family from the registrable domain
        "ledger/freshness",  # accessed / verified_at refreshed from cache meta
        "binding/excerpt-missing",  # excerpt writes for unambiguous mappings
        "binding/sources-section",  # Sources regeneration
        "integrity/date-line",  # date-line whitespace normalization
    }
)

#: The families `alx` emits itself; everything else it prints comes from the
#: gate modules below and keeps that module's family name and class.
OWN_FAMILIES = (
    "binding/excerpt-missing",
    "binding/leftover-prose",
    "fidelity/cache-detached",
    "fidelity/undecodable",
    "fidelity/unreachable",
    "integrity/encoding",
    "review/content-missing",
    "review/content-stale",
    "review/rewild",
    "tooling/receipt",
    "tooling/render",
)

#: Every finding family `alx` can print, from itself and from T1-T4 (ruling R6:
#: the parse test walks this registry so no remedy escapes D14). One name set:
#: each producing module owns the spelling of its own families.
FAMILIES = tuple(
    sorted(
        set(validate_ledger.FAMILIES)
        | set(source_fidelity.FAMILIES)
        | set(rewild_gate.FAMILIES)
        | set(content_gate.FAMILIES)
        | set(validate_report.FAMILIES)
        | set(OWN_FAMILIES)
    )
)

#: Offline these are fabrication findings (Class F): a cache is present and the
#: extract does not survive in it. Live, the same families mean the network was
#: unusable beyond the policy quorum.
ONLINE_CLASS_A_FAMILIES = frozenset(
    {
        "fidelity/unreachable",
        "fidelity/undecodable",
    }
)

#: Spec §7.2.5: the receipt tolerates this share of unverified sampled pairs.
#: Past it, each unverified pair is a Class-A finding of its own.
UNVERIFIED_STATUSES = frozenset({"unreachable", "undecodable"})
UNVERIFIED_QUORUM = 0.25

#: Spec §6.11 subprocess budgets. The rasterizer keeps its own 90 s
#: (`render_pdf_pages.SUBPROCESS_TIMEOUT_S`, used by `render_pages`); md_to_pdf
#: runs no subprocess.
FETCH_TIMEOUT_SECONDS = 20
REWILD_CHECKER_TIMEOUT_SECONDS = 120
ONLINE_CAP_MINUTES = 4
EXCERPT_CHARS = 60
MIN_EXTRACT_CHARS = 20
# JS-rendered or bot-blocked pages return HTTP 200 with no readable body
MIN_SOURCE_TEXT_CHARS = 200
# a CJK character carries a word, so a CJK page clears the floor with fewer
MIN_SOURCE_CJK_CHARS = 80
MAX_WINDOW_CHARS = 300
MAX_FINDING_CHARS = 800


def remedy(key, **values):
    """Return one pinned remedy string from the registry."""
    return REMEDY_TEMPLATES[key].format(**values)


def set_field(field, file):
    """Addendum 6: a claim input is only back in the ledger after `claim add`."""
    key = "set-field-claim" if str(file).startswith("claims/") else "set-field"
    return remedy(key, field=field, file=file)


def add_link(paragraph, claim_id):
    """Ruling R9: cite the claim where it is stated; `n` when it is known."""
    if paragraph:
        return remedy("add-link", claim_id=claim_id or "C1", paragraph=paragraph)
    return remedy("add-link-claim", claim_id=claim_id or "C1")


Finding = gate_severity.Finding


def render_grouped(findings, *, per_family=5, verbose=False):
    """R28: the HARD/WARN tier is the whole story; no class label is printed."""
    return gate_severity.render_grouped(
        findings, per_family=per_family, with_class=False, verbose=verbose
    )


def _render_reminders(findings):
    """R38.8: REMINDERS must not nest the HARD header."""
    return "\n".join(
        line
        for line in render_grouped(findings).splitlines()
        if not line.startswith("=== HARD")
    )


def _checker_fix(message):
    text = str(message)
    if "timed out" in text.casefold() or "120 s" in text or "120 second" in text:
        return remedy("checker-timeout")
    if "readable" in text.casefold() or text.startswith("Unsupported"):
        return text
    return remedy("checker-timeout")


def finding_class(family, severity, *, online=False):
    """Class F unless the family is listed as availability/tooling."""
    if severity == "warn":
        return "A"
    if online and family in ONLINE_CLASS_A_FAMILIES:
        return "A"
    return "A" if family in CLASS_A_FAMILIES else "F"


#: Ruling R28: families `alx` emits that never block `issue`. They are printed
#: with their fix and listed in the delivery notes.
WARN_FAMILIES = frozenset(
    {
        "tooling/receipt",
        "tooling/render",
        "review/rewild",
        "review/content",
        "review/content-missing",
        "review/content-stale",
        "fidelity/unreachable",
        "fidelity/undecodable",
    }
)

#: R33 (user 09-16): only whole-report defects refuse `issue` — no snapshot,
#: a report under two thirds of the length floor, an unrestorable encoding,
#: a broken PDF at render. An unsupported figure, a Rewild meaning reversal
#: and an unfixed critical review finding are warnings that name the fix.
REFUSE_FAMILIES = frozenset()
#: R33 (user): these warnings are repeated by `issue` as reminders — the report
#: still issues, the agent is told what is not fixed yet.
REMINDER_FAMILIES = frozenset(
    {"ledger/quantity", "fidelity/semantic", "content/critical-finding"}
)
REMINDER_HEADER = "=== REMINDERS (not fixed yet; warnings, never block) ==="
BLOCKED_HEADER = "=== BLOCKED (fix, then alx issue again) ==="
STALE_FIDELITY_WARN = (
    "WARNING: source-fidelity receipt predates the ledger or report; skipped "
    "(alx issue --live refreshes it)"
)


def finding(family, message, *, severity="hard", ids=(), fix="", remove=""):
    if family in WARN_FAMILIES:
        severity = "warn"
    return Finding(
        family=family,
        severity=severity,
        klass=finding_class(family, severity),
        ids=list(ids),
        message=message,
        fix=fix,
        remove=remove,
    )


def hard_findings(findings):
    return [item for item in findings if item.severity != "warn"]


def class_f_findings(findings):
    return [item for item in hard_findings(findings) if item.klass == "F"]


def _is_refuse_finding(item):
    return item.family in REFUSE_FAMILIES or item.family == "integrity/encoding"


def _length_counts(ws, state):
    lang = state.get("lang", "en")
    try:
        text = ws.report_text()
    except UnicodeDecodeError:
        return None
    count, unit = report_blocks.report_length(text, lang)
    floor, _ceiling, _unit = report_contract.report_length_policy(lang)
    return count, floor, unit


def _length_below_two_thirds(ws, state):
    counts = _length_counts(ws, state)
    if counts is None:
        return False
    count, floor, _unit = counts
    return count < (floor * 2) // 3


def _refuse_fix(item):
    if item.family == "ledger/quantity":
        claim_id = _pick_id(item, "C")
        base = item.fix or "alx find S1 <figure> then correct the claim or extract"
        drop = f", or {remedy('claim-drop', claim_id=claim_id)}" if claim_id else ""
        if drop and "claim drop" not in base:
            return base.rstrip(".") + drop
        return base
    if item.family == "fidelity/semantic":
        return item.fix or str(item.message).rstrip(".")
    if item.family == "content/critical-finding":
        return (
            "fix the report and record the disposition in reviews/content.json, "
            "then alx review finish content"
        )
    if item.family == "integrity/encoding":
        return item.fix or remedy("snapshot-restore")
    if item.family == "integrity/length":
        return "deepen (research, counterevidence, implications), never pad"
    if item.family == "issue/snapshot":
        return "alx snapshot"
    return item.fix


def _collect_refusals(ws, state, _ledger, findings):
    items = []
    for item in findings:
        if _is_refuse_finding(item):
            items.append(replace(item, fix=_refuse_fix(item), severity="hard"))
    if ws.latest_snapshot() is None:
        items.append(
            finding(
                "issue/snapshot",
                "no snapshot; the Rewild step never started "
                "(humanize, alx check, then alx issue).",
                fix="alx snapshot",
            )
        )
    if _length_below_two_thirds(ws, state):
        count, floor, unit = _length_counts(ws, state)
        if not any(item.family == "integrity/length" for item in items):
            items.append(
                finding(
                    "integrity/length",
                    f"Report has {count} {unit}; below two thirds of the floor "
                    f"({floor} {unit}).",
                    fix="deepen (research, counterevidence, implications), never pad",
                )
            )
        else:
            items = [
                replace(
                    item,
                    fix="deepen (research, counterevidence, implications), never pad",
                )
                if item.family == "integrity/length"
                else item
                for item in items
            ]
    return items


def _render_blocked(items):
    lines = [BLOCKED_HEADER]
    for family, members in gate_severity.group(items).items():
        lines.append(f"[{family}] {len(members)}")
        for item in members:
            tail = str(item.message).rstrip(".") + "."
            fix = item.fix or _refuse_fix(item)
            if fix:
                tail += f" Fix: {fix}."
            lines.append(f"  {tail}")
    return "\n".join(lines)


def _check_display_findings(ws, state, findings):
    shown = []
    for item in findings:
        promote = (
            item.family == "integrity/length" and _length_below_two_thirds(ws, state)
        ) or (_is_refuse_finding(item) and item.family != "integrity/encoding")
        if promote:
            shown.append(replace(item, severity="hard", fix=_refuse_fix(item)))
        else:
            shown.append(item)
    if ws.latest_snapshot() is None:
        shown.append(
            finding(
                "issue/snapshot",
                "no snapshot; the Rewild step never started "
                "(humanize, alx check, then alx issue).",
                fix="alx snapshot",
            )
        )
    return shown


_ID_RE = {"C": re.compile(r"^C\d+$"), "S": re.compile(r"^S\d+$")}
_URL_IN_MESSAGE = re.compile(r"https?://[^\s;,)]+")


def _pick_id(item, prefix):
    for value in item.ids or ():
        if _ID_RE[prefix].match(str(value)):
            return str(value)
    match = re.search(rf"\b{prefix}\d+\b", str(item.message))
    return match.group(0) if match else None


def _find_keyword(message):
    """`alx find` takes a KEYWORD: the term the producer quoted, never an id."""
    for quoted in re.findall(r"'([^']+)'", str(message)):
        token = re.split(r"\s+", quoted.strip())[0]
        token = re.sub(r"[^\w,.\-\u4e00-\u9fff]", "", token)
        if token and not _ID_RE["C"].match(token) and not _ID_RE["S"].match(token):
            return token
    return ""


def _quote_or_find(item, source_id, claim_id):
    """The quoted term when there is one, else the closed quote imperative."""
    keyword = _find_keyword(item.message)
    fix = (
        remedy("find", source_id=source_id or "S1", keyword=keyword)
        if keyword
        else remedy("extend-quote", file="claims/*.json")
    )
    return fix, remedy("claim-drop", claim_id=claim_id) if claim_id else ""


def _drop_or_refresh(item):
    claim_id = _pick_id(item, "C")
    if claim_id:
        return remedy("claim-drop", claim_id=claim_id)
    source_id = _pick_id(item, "S")
    if source_id:
        return remedy("fetch-refresh", source_id=source_id)
    return ""


#: family -> (fix, remove) builders. Every printed remedy passes through here so
#: the parse test over this one registry covers everything `alx` can print (R6).
def _remedies(item, *, paragraphs=0, claim_files=None):
    family = item.family
    claim_id = _pick_id(item, "C")
    source_id = _pick_id(item, "S")
    restore = remedy("snapshot-restore")
    if family in {
        "integrity/control-chars",
        "integrity/replacement-char",
        "integrity/quotation-lost",
        "integrity/encoding",
        "fidelity/quotation-lost",
        "fidelity/rewild",
        "fidelity/semantic",
        "rewild/region",
    }:
        return "", restore
    if family == "integrity/length":
        if item.severity == "warn":
            return remedy("extend-report"), ""
        return "", remedy("delete-paragraph", paragraph=max(paragraphs, 1))
    if family in {"integrity/structure", "integrity/date-line"}:
        return remedy("edit-prose"), ""
    if family == "binding/link-not-in-ledger":
        match = _URL_IN_MESSAGE.search(item.message)
        url = match.group(0) if match else ""
        if not url:
            return "", ""
        return (
            validate_report.LINK_NOT_IN_LEDGER_FIX,
            remedy("remove-link", url=url),
        )
    if family in {"binding/claim-paragraph", "binding/paragraph"}:
        listed = re.search(r"candidates:\s*([^\n]+)", str(item.message))
        numbers = []
        if listed and listed.group(1).strip() != "none":
            numbers = [
                part.strip()
                for part in listed.group(1).split(",")
                if part.strip().isdigit()
            ]
        drop = remedy("claim-drop", claim_id=claim_id) if claim_id else ""
        if numbers:
            return (
                remedy(
                    "claim-bind",
                    claim_id=claim_id or "C1",
                    paragraph=int(numbers[0]),
                ),
                drop,
            )
        return f"alx claim bind {claim_id or 'C1'}:<paragraph>", drop
    if family == "binding/excerpt-missing":
        return (
            remedy("check-fix"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family == "binding/leftover-prose":
        number = re.search(r"paragraph (\d+)", item.message)
        return (
            remedy("delete-paragraph", paragraph=int(number.group(1)) if number else 1),
            "",
        )
    if family == "binding/sources-section":
        return remedy("check-fix"), ""
    if family in {"fidelity/cache-missing", "fidelity/cache-detached"}:
        return remedy("fetch-refresh", source_id=source_id or "S1"), ""
    if family == "fidelity/context-changed":
        # J4: the refresh alone keeps the old probe contexts; `claim add`
        # re-confirms the extract and re-binds them, which clears the finding.
        # K5: name the file that holds this claim, so the printed command runs.
        return (
            remedy(
                "refresh-rebind",
                source_id=source_id or "S1",
                file=(claim_files or {}).get(claim_id) or "claims/*.json",
            ),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family == "fidelity/mismatch":
        if "Closest passage in" in str(item.message):
            keyword = _find_keyword(item.message)
            return (
                remedy(
                    "paste-passage",
                    source_id=source_id or "S1",
                    file=(claim_files or {}).get(claim_id) or "claims/*.json",
                    keyword=keyword or "the-missing-window",
                ),
                remedy("claim-drop", claim_id=claim_id) if claim_id else "",
            )
        return _quote_or_find(item, source_id, claim_id)
    if family == "ledger/extract-length":
        return (
            remedy("extend-quote", file="claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family in ONLINE_CLASS_A_FAMILIES:
        return (
            remedy("fetch-refresh", source_id=source_id or "S1"),
            _drop_or_refresh(item),
        )
    if family == "tooling/render":
        text = str(item.message).rstrip(".")
        if "not rendered" in text:
            return text, ""
        return remedy("render"), ""
    if family.startswith("tooling/"):
        return remedy("issue"), _drop_or_refresh(item)
    if family == "ledger/claim-input":
        return (
            set_field("claim-input", "claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family == "ledger/person":
        return remedy("ledger-merge", file="people.json"), ""
    if family == "ledger/https":
        match = _URL_IN_MESSAGE.search(item.message)
        https = re.sub(r"^http://", "https://", match.group(0)) if match else ""
        if not https:
            return "", ""
        return (
            remedy("source-set-url", source_id=source_id or "S1", url=https),
            "",
        )
    if family == "ledger/host-conflict":
        return remedy("source-family-justification", source_id=source_id or "S1"), ""
    if family in {
        "ledger/provenance",
        "ledger/key-claim",
        "ledger/source-family",
        "ledger/undated-reason",
        "ledger/portfolio",
    }:
        return remedy("source-set", source_id=source_id or "S1"), _drop_or_refresh(item)
    if family in {"ledger/coverage", "ledger/synthesis"}:
        return remedy("ledger-merge", file="coverage.json"), _drop_or_refresh(item)
    if family in {
        "ledger/quantity",
        "ledger/status",
        "ledger/direction",
        "ledger/derived",
    }:
        return _quote_or_find(item, source_id, claim_id)
    if family == "ledger/triangulation":
        return (
            set_field("triangulation", "claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family == "ledger/reference":
        return (
            set_field("supports", "claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family == "ledger/excluded-supports":
        return (
            set_field("supports", "claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family.startswith("content/") or family.startswith("review/content"):
        if family.endswith("-stale"):
            return remedy("review-stale", kind="content"), ""
        if family.endswith("-missing"):
            return remedy("review-start", kind="content"), ""
        return remedy("review-quality"), ""
    if family.startswith("review/rewild"):
        if "missing" in str(item.message):
            return remedy("review-start", kind="rewild"), ""
        return remedy("review-stale", kind="rewild"), ""
    if family in {"rewild/ai-vocabulary", "rewild/style", "rewild/length"}:
        return remedy("edit-prose"), ""
    if family == "rewild/checker":
        return _checker_fix(item.message), ""
    if family.startswith("rewild/"):
        return remedy("issue"), ""
    if family == "ledger/schema":
        # J2: one derivation of the field, shared with T2, so the remedy can
        # never name a field the schema error did not name.
        location, _, detail = item.message.partition(": ")
        return validate_ledger.schema_remedy(location, detail), _drop_or_refresh(item)
    # Ruling R10: the fallback for an unmatched family is never `check --fix`.
    if adopted_class(item) == "A":
        return remedy("edit-prose"), ""
    return _quote_or_find(item, source_id, claim_id)


is_finding = gate_severity.is_finding

_FINDING_FIELDS = ("family", "severity", "klass", "ids", "message", "fix", "remove")


def as_findings(items):
    """T1 stores findings as `asdict` payloads and imports its own `Finding`.

    Both forms must survive into classification: a dict is rebuilt, any
    finding-shaped object is kept (`isinstance` would drop the other copy of
    the class), and anything else is ignored.
    """
    findings = []
    for item in items or []:
        if isinstance(item, dict):
            item = Finding(
                **{name: item[name] for name in _FINDING_FIELDS if name in item}
            )
        if is_finding(item):
            findings.append(item)
    return findings


def adopted_class(item, *, online=False):
    """The producing module's class wins (spec §6.10); `alx` only fills gaps."""
    if item.severity == "warn":
        return "A"
    if online and item.family in ONLINE_CLASS_A_FAMILIES:
        return "A"
    klass = getattr(item, "klass", "")
    if klass in {"F", "A"}:
        return klass
    return finding_class(item.family, item.severity)


#: Families whose printed remedy `alx` owns even when the producer offers one:
#: the producers' generic advice here is not the repair the finding needs
#: (an http url is re-fetched under its https form; a host conflict is resolved
#: by a family_justification, never by re-declaring provenance; J4: a refresh
#: alone never clears a changed context, only the refresh plus `claim add`).
REMEDY_OVERRIDES = frozenset(
    {
        "ledger/https",
        "ledger/host-conflict",
        "fidelity/context-changed",
        "binding/link-not-in-ledger",
    }
)

_EMBEDDED_REMEDY = re.compile(r"\s*(?:Fix|Remove):\s*`?[^`.\n]+`?\.?\s*$")
_BARE_SET_FIELD = re.compile(r"^set field (\S+)$")
_PARSER_FOR_REMEDIES = None


def valid_remedy(text):
    """Spec D14: a printed remedy parses as `alx ...` or is a closed imperative."""
    global _PARSER_FOR_REMEDIES
    text = str(text or "").strip().strip("`")
    if not text:
        return False
    if any(pattern.match(text) for pattern in CLOSED_IMPERATIVES):
        return True
    if text.startswith("alx "):
        if _PARSER_FOR_REMEDIES is None:
            _PARSER_FOR_REMEDIES = build_parser()
        with redirect_stderr(io.StringIO()):
            try:
                _PARSER_FOR_REMEDIES.parse_args(shlex.split(text)[1:])
            except (SystemExit, ValueError):
                return False
        return True
    return False


_LEDGER_MERGE_FIELDS = ("brief", "people", "coverage", "synthesis")


def _named_file(item):
    """Claim findings are edited in the claim inputs; the rest in the ledger."""
    return (
        "claims/*.json"
        if any(str(value).startswith("C") for value in item.ids or ())
        else "ledger.json"
    )


#: Both placeholders a producer may write for "the claim's own input file".
CLAIM_FILE_PLACEHOLDERS = ("claims/*.json", "claims/<file>")


def _with_claim_file(text, item, claim_files):
    """K5: a producer remedy names the real claim input when `alx` knows it.

    `claims/<file>` is never runnable, so it becomes the real file, or the glob
    that `claim add` expands.
    """
    if not text:
        return text
    named = (claim_files or {}).get(_pick_id(item, "C")) or "claims/*.json"
    for placeholder in CLAIM_FILE_PLACEHOLDERS:
        text = str(text).replace(placeholder, named)
    return text


def _completed_remedy(text, item):
    """`set field x` from a producer becomes the closed imperative in full."""
    match = _BARE_SET_FIELD.match(str(text or "").strip())
    if match:
        field = match.group(1)
        root = field.split(".", 1)[0]
        if root in _LEDGER_MERGE_FIELDS:
            return f"set field {field}, then alx ledger merge ledger-patch.json"
        return set_field(field, _named_file(item))
    return text


def _strip_embedded_remedies(message):
    """Producers that append `Fix:`/`Remove:` to the prose must not print twice."""
    text = str(message).rstrip()
    while True:
        shorter = _EMBEDDED_REMEDY.sub("", text)
        if shorter == text:
            return text
        text = shorter


def _fit(message, ids, fix, remove):
    """Item 6: the line stays under 800 chars; the remedy is never truncated."""
    prefix = f"{', '.join(ids)}: " if ids else ""
    tail = ""
    if fix:
        tail += f" Fix: {fix}."
    if remove:
        tail += f" Remove: `{remove}`."
    budget = MAX_FINDING_CHARS - len("  ") - len(prefix) - len(tail) - 1
    # A message may carry continuation lines (the portfolio vocabulary); the cap
    # is per printed line, not per message.
    body = []
    for line in message.rstrip(".").split("\n"):
        if len(line) > budget:
            # Minor 2: a budget at or below zero still cuts the message; the ids
            # and the remedy are never truncated, so only they may overrun.
            line = line[: max(budget - 1, 0)].rstrip() + "\u2026"
        body.append(line)
    return "\n".join(body)


def honest_fix(family, text):
    """Ruling R10: which `Fix:` a family is allowed to advertise."""
    text = str(text or "").strip().strip("`")
    if text == remedy("check"):
        return False
    if text == remedy("check-fix"):
        return family in MECHANICAL_FIX_FAMILIES
    return True


def adopt(findings, *, online=False, paragraphs=0, claim_files=None):
    """Fill a Fix only when the producer printed none; never replace one."""
    adopted = []
    seen = set()
    for item in findings:
        if not is_finding(item):
            text = str(item)
            item = finding(
                "ledger/schema",
                text.removeprefix(gate_severity.WARNING_PREFIX),
                severity="warn" if gate_severity.is_warning(text) else "hard",
            )
        key = (item.family, tuple(item.ids or ()), item.message)
        if key in seen:
            continue
        seen.add(key)
        klass = adopted_class(item, online=online)
        producer_fix = str(item.fix or "").strip()
        fix = (
            _with_claim_file(_completed_remedy(producer_fix, item), item, claim_files)
            if producer_fix
            else ""
        )
        remove = _completed_remedy(getattr(item, "remove", ""), item)
        remove = remove if valid_remedy(remove) else ""
        if klass == "A":
            remove = ""
        if not producer_fix:
            fix, filled_remove = _remedies(
                item, paragraphs=paragraphs, claim_files=claim_files
            )
            fix = _with_claim_file(fix, item, claim_files)
            if not remove:
                remove = filled_remove
            if klass == "A":
                remove = ""
        if remove and remove == fix:
            fix = ""
        message = _strip_embedded_remedies(item.message)
        adopted.append(
            Finding(
                family=item.family,
                severity=item.severity,
                klass=klass,
                ids=list(item.ids or []),
                message=_fit(message, list(item.ids or []), fix, remove),
                fix=fix,
                remove=remove,
            )
        )
    return adopted


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _now():
    return datetime.now(timezone.utc)


class Workspace:
    """The report directory layout of spec §5."""

    def __init__(self, directory):
        self.dir = Path(directory).resolve()
        self.report = self.dir / "report.md"
        self.ledger_path = self.dir / "ledger.json"
        self.sources = self.dir / "sources"
        self.claims = self.dir / "claims"
        self.reviews = self.dir / "reviews"
        self.receipts = self.dir / "receipts"
        self.alx = self.dir / ".alx"
        self.state_path = self.alx / "state.json"
        self.worklog = self.dir / "worklog.md"

    def load_state(self):
        return _read_json(self.state_path)

    def save_state(self, state):
        _write_json(self.state_path, state)

    def load_ledger(self):
        return _read_json(self.ledger_path)

    def save_ledger(self, ledger):
        _write_json(self.ledger_path, ledger)

    def report_text(self):
        return self.report.read_bytes().decode("utf-8")

    def cache_paths(self, source_id):
        return (
            self.sources / f"{source_id}.txt",
            self.sources / f"{source_id}.meta.json",
        )

    def snapshots(self):
        base = self.dir / "report.pre-rewild.md"
        found = [base] if base.exists() else []
        iterations = sorted(
            self.dir.glob("report.pre-rewild.iter*.md"),
            key=lambda path: int(re.search(r"iter(\d+)", path.name).group(1)),
        )
        return found + iterations

    def latest_snapshot(self):
        snapshots = self.snapshots()
        return snapshots[-1] if snapshots else None

    def review_dir(self, kind, iteration):
        return self.alx / "reviews" / kind / str(iteration)


def _minutes(state):
    start = datetime.fromisoformat(state["start_time"])
    deadline = datetime.fromisoformat(state["deadline"])
    now = _now()
    elapsed = max(0, int((now - start).total_seconds() // 60))
    left = (deadline - now).total_seconds()
    remaining = 0 if left <= 0 else math.ceil(left / 60)
    return elapsed, remaining


def _emit(ws, state, command, summary, lines, *, worklog=True):
    """Print the command output, append the worklog line, print the footer."""
    for line in lines:
        print(line)
    elapsed, remaining = _minutes(state)
    stamp = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    if worklog:
        with ws.worklog.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {command} {summary}\n")
    shown = max(remaining, 0)
    suffix = (
        " — stop polishing: alx issue, then alx render"
        if 1 <= shown <= 8
        else " — time is up: alx issue, then alx render, deliver"
        if shown == 0
        else ""
    )
    print(f"elapsed {max(elapsed, 0)} min, remaining {shown} min{suffix}")


#: D7: a stalled rewild checker costs its 120 s once per command, not once per
#: invocation. After the first timeout the rest of the command skips the
#: subprocess and reuses that one Class A note.
_CHECKER_TIMED_OUT = False


def _checker_timeout():
    return 0 if _CHECKER_TIMED_OUT else REWILD_CHECKER_TIMEOUT_SECONDS


def _note_checker_timeout(messages):
    global _CHECKER_TIMED_OUT
    if any("timed out" in str(message) for message in messages):
        _CHECKER_TIMED_OUT = True
    return messages


def _open(args):
    """Return (workspace, state, ledger) for an initialized directory."""
    global _CHECKER_TIMED_OUT
    _CHECKER_TIMED_OUT = False
    ws = Workspace(args.dir)
    if not ws.state_path.exists():
        raise SystemExit(
            f"No Alexandria workspace in {ws.dir}. Run `alx init {ws.dir} "
            "--lang en --subject subject.txt` first."
        )
    return ws, ws.load_state(), ws.load_ledger()


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

_QUOTED_SPAN_RE = re.compile(
    r"「([^」]{4,}?)」|『([^』]{4,}?)』|“([^”]{4,}?)”|‘([^’]{4,}?)’|\"([^\"\n]{4,}?)\""
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_url(value):
    """lowercase scheme/host, strip fragment, utm_*, trailing slash (spec §6.7c)."""
    parts = urlsplit(str(value or "").strip())
    query = "&".join(
        item
        for item in parts.query.split("&")
        if item and not item.casefold().startswith("utm_")
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


def quoted_spans(text):
    spans = []
    for match in _QUOTED_SPAN_RE.finditer(str(text or "")):
        span = next(group for group in match.groups() if group is not None)
        spans.append(span.strip())
    return [span for span in spans if len(span) >= 4]


def _blocks(text):
    """Return (start, end, text) for every blank-line separated block."""
    blocks = []
    start = 0
    for match in re.finditer(r"\n[ \t]*\n", text + "\n\n"):
        end = min(match.start(), len(text))
        if text[start:end].strip():
            blocks.append((start, end, text[start:end]))
        start = match.end()
        if start >= len(text):
            break
    return blocks


def sources_heading_offset(text):
    offset = None
    for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE):
        if validate_report.is_sources_heading(match.group(1).strip()):
            offset = match.start()
    return offset


def _fallback_split_body_paragraphs(text):
    """The local copy of T3's numbering, used until its export lands."""
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    masked = _FENCE_RE.sub(lambda match: " " * len(match.group(0)), body)
    numbered = []
    number = 0
    for start, end, block in _blocks(masked):
        first = block.lstrip().splitlines()[0]
        if first.startswith(("#", ">", "```", "|")):
            continue
        number += 1
        numbered.append((number, body[start:end]))
    return numbered


def body_paragraphs(text):
    """Numbered body paragraphs: (number, start, end, text).

    J3: one numbering for the whole skill. `validate_report` owns it, so the
    `--paragraph N` `alx` prints is the N the binding rules mean; `alx` only
    adds the offsets its own paragraph deletion needs.
    """
    splitter = getattr(validate_report, "split_body_paragraphs", None)
    numbered = (
        splitter(text) if splitter is not None
        else _fallback_split_body_paragraphs(text)
    )
    # K3: match whole blank-line blocks in order, never `find()` on the prose.
    # A standfirst that clones paragraph 1 is a different block (`> …`), and two
    # body paragraphs that differ only by their citation URL are two blocks.
    blocks = _blocks(text)
    located = []
    cursor = 0
    for number, block in numbered:
        for index in range(cursor, len(blocks)):
            start, end, raw = blocks[index]
            if raw.strip() == block.strip():
                located.append((number, start, end, block))
                cursor = index + 1
                break
    return located


def markdown_links(text):
    return [(match.group(1), match.group(2)) for match in _LINK_RE.finditer(text)]


def masked_prose(text):
    """Link-stripped, whitespace-folded prose used by the freshness diff."""
    stripped = _LINK_RE.sub(lambda match: match.group(1), text)
    return re.sub(r"\s+", " ", stripped).strip()


def sentence_window(text, start, length, context):
    """Sentence-bounded verbatim window, no ellipsis, <= 300 chars."""
    left = max(0, start - context)
    right = min(len(text), start + length + context)
    boundaries = "。！？!?；;\n"
    head = start
    while head > left and text[head - 1] not in boundaries:
        head -= 1
    tail = start + length
    while tail < right and text[tail - 1] not in boundaries:
        tail += 1
    window = text[head:tail].strip()
    if len(window) > MAX_WINDOW_CHARS:
        window = window[:MAX_WINDOW_CHARS].strip()
    return window


# --------------------------------------------------------------------------
# fetch and cache
# --------------------------------------------------------------------------


def cached(ws, source_id):
    """`source_fidelity.read_cache` over the workspace cache directory."""
    return source_fidelity.read_cache(ws.sources, source_id)


def cache_matches(text, meta):
    """`write_cache` appends at most one newline to the hashed visible text."""
    digests = {_sha256_text(text)}
    if text.endswith("\n"):
        digests.add(_sha256_text(text[:-1]))
    return meta.get("text_sha256") in digests


def cache_urls(meta):
    known = {
        normalize_url(meta.get("url", "")),
        normalize_url(meta.get("final_url", "")),
    }
    known.update(normalize_url(alias) for alias in meta.get("aliases") or [])
    return {item for item in known if item}


def _registrable_domain(url):
    return validate_ledger._registrable_domain(url)


def _next_id(items, prefix, key):
    used = {
        int(item[key][1:])
        for item in items
        if isinstance(item.get(key), str) and item[key][1:].isdigit()
    }
    number = 1
    while number in used:
        number += 1
    return f"{prefix}{number}"


def _source_by_url(ledger, url):
    normalized = normalize_url(url)
    for source in ledger.get("sources", []):
        known = {normalize_url(source.get("url", ""))}
        known.update(normalize_url(alias) for alias in source.get("aliases", []))
        if normalized in known:
            return source
    return None


# --------------------------------------------------------------------------
# probes (T1 owns them; alx only supplies the (claim, source, text) triple)
# --------------------------------------------------------------------------


def claim_probe_findings(ws, ledger, claim):
    """`source_fidelity.probe_findings` per (claim, source) pair, plus cache gaps."""
    sources = {
        source.get("source_id"): source
        for source in ledger.get("sources", [])
        if isinstance(source, dict)
    }
    claim_id = claim.get("claim_id", "")
    findings = []
    for record in claim.get("source_evidence") or []:
        source_id = record.get("source_id", "")
        entry = cached(ws, source_id)
        if entry is None:
            findings.append(
                finding(
                    "fidelity/cache-missing",
                    f"{source_id} has no fetched cache; the extract cannot be probed.",
                    ids=[claim_id, source_id],
                )
            )
            continue
        text, meta = entry
        findings.extend(
            source_fidelity.probe_findings(
                claim, sources.get(source_id, {"source_id": source_id}), text,
                cache_meta=meta,
                # R22: probe THIS entry; a second passage from the same page is
                # legitimate evidence and must be checked on its own.
                extract=record.get("extract_or_location"),
            )
        )
    return findings


def record_probe_contexts(ws, claim):
    """Ruling R1: bind the probe contexts of a freshly accepted claim."""
    for record in claim.get("source_evidence") or []:
        source_id = record.get("source_id", "")
        if cached(ws, source_id) is None:
            continue
        source_fidelity.record_probe_contexts(
            ws.sources,
            source_id,
            claim.get("claim_id", ""),
            source_fidelity.probe_strings(record.get("extract_or_location", "")),
        )


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def _skeleton_report(subject, lang, report_day):
    date_line = report_contract.localized_date(lang, report_day)
    floor, ceiling, unit = report_contract.report_length_policy(lang)
    if lang == "en":
        standfirst = (
            "Standfirst placeholder: one sentence on what this report decides. "
            f"Target {floor}–{ceiling} {unit}."
        )
        sources = "## Sources"
    else:
        standfirst = (
            "导语占位：一句话说明本报告要回答的问题。"
            f"目标 {floor}–{ceiling} 字（正文字数）。"
        )
        sources = "## 资料来源"
    return f"# {subject}\n\n> {standfirst}\n> {date_line}\n\n{sources}\n"


def _skeleton_ledger(args, subject, question, reader, report_day):
    ledger = {
        "schema_version": 4,
        "subject": subject,
        "research_question": question,
        "brief": {
            "intended_reader": reader,
            "decision_or_use": question,
            "archetype": args.archetype,
            "report_language": args.lang,
            "editorial_mode": "analytical",
            "scope": {
                "time_horizon": "Set in `alx ledger merge`.",
                "geography": "Set in `alx ledger merge`.",
                "inclusions": [],
                "exclusions": [],
            },
        },
        "people": [],
        "report_date": report_day.isoformat(),
        "coverage": [],
        "sources": [],
        "claims": [],
        "excluded_claims": [],
        "synthesis": {
            "central_judgment_claim_ids": [],
            "counterevidence_claim_ids": [],
            "adversarial_tests": [],
            "implications": [],
            "decisions_or_takeaways": [],
            "scenarios": [],
            # The schema types this as an array; a placeholder string made every
            # fresh workspace open with a HARD ledger/schema finding.
            "limitations": [],
            "research_stop_reason": "Set in `alx ledger merge`.",
        },
        "unresolved_questions": [],
    }
    if args.archetype == "person":
        ledger["people"].append(
            {
                "person_id": "P1",
                "name": subject,
                "aliases": [],
                "public_role": "public",
                "relationship": "primary_subject",
            }
        )
    return ledger


def cmd_init(args):
    ws = Workspace(args.directory)
    # Field test 6: the archetype default is a silent inference; say so.
    origin = "given" if getattr(args, "archetype", None) else "inferred"
    args.archetype = getattr(args, "archetype", None) or "hybrid"
    if ws.ledger_path.exists() and not args.force:
        try:
            state, ledger = ws.load_state(), ws.load_ledger()
        except (OSError, ValueError):
            state = ledger = None
        if state is not None:
            print(
                f"workspace exists: {ws.dir} — keeping it "
                "(alx init --force resets it)"
            )
            print(f"Next: {_next_command(ws, state, ledger)}")
            return 0
        print(f"workspace at {ws.dir} is incomplete; re-initializing it")
    subject_text = _input_path(args, args.subject).read_text(encoding="utf-8").strip()
    lines = [line.strip() for line in subject_text.splitlines() if line.strip()]
    subject = lines[0] if lines else "Untitled subject"
    question = lines[1] if len(lines) > 1 else subject
    reader = (
        _input_path(args, args.reader).read_text(encoding="utf-8").strip()
        if args.reader
        else "Unspecified reader; set it with `alx ledger merge`."
    )
    for directory in (ws.dir, ws.sources, ws.claims, ws.reviews, ws.receipts, ws.alx):
        directory.mkdir(parents=True, exist_ok=True)
    report_day = date.today()
    ws.save_ledger(_skeleton_ledger(args, subject, question, reader, report_day))
    ws.report.write_text(
        _skeleton_report(subject, args.lang, report_day), encoding="utf-8"
    )
    started = _now()
    state = {
        "start_time": started.isoformat(),
        "deadline": (started + timedelta(minutes=args.budget_minutes)).isoformat(),
        "lang": args.lang,
        "archetype": args.archetype,
        "counters": {"fetch": 0, "claims": 0, "check": 0, "issue": 0},
        "reviews": {
            kind: {"iteration": 0, "finished": False} for kind in REVIEW_KINDS
        },
        "bindings": {},
        "mechanical_deletions": [],
        "last_check": {},
        "humanization": "pending",
    }
    ws.save_state(state)
    ws.worklog.touch()
    length_floor, length_ceiling, length_unit = report_contract.report_length_policy(
        args.lang
    )
    _emit(
        ws,
        state,
        "init",
        f"{args.lang} {args.archetype} workspace",
        [
            f"Workspace ready: {ws.dir}",
            f"archetype: {args.archetype} ({origin}) — change with "
            "`alx init … --archetype <name>`",
            f"language: {args.lang} — change with "
            f"`alx init … --lang <{'|'.join(LANGUAGES)}>`",
            f"target length: {length_floor}–{length_ceiling} {length_unit} "
            "(alx check prints the count)",
            "Next: `alx fetch <url> ...` for 8-15 reachable sources.",
        ],
    )
    return 0


# --------------------------------------------------------------------------
# fetch / source set
# --------------------------------------------------------------------------


#: `published` is a schema `date`, but a scraped page offers a timestamp or a
#: localized form; anything that is not a date the ledger can carry is dropped.
_PUBLISHED_ISO_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})")
_PUBLISHED_SLASH_RE = re.compile(r"^([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})")
_PUBLISHED_CJK_RE = re.compile(r"^([0-9]{4})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日")


def _normalized_published(value):
    """Item A3: a published stamp is kept only as `YYYY-MM-DD`, else dropped."""
    text = str(value or "").strip()
    iso = _PUBLISHED_ISO_RE.match(text)
    if iso:
        return iso.group(1)
    for pattern in (_PUBLISHED_SLASH_RE, _PUBLISHED_CJK_RE):
        match = pattern.match(text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _upsert_source(ledger, source_id, result, args, aliases):
    domain = _registrable_domain(result.final_url) or ""
    existing = next(
        (
            source
            for source in ledger["sources"]
            if source.get("source_id") == source_id
        ),
        None,
    )
    source = existing or {"source_id": source_id}
    source.update(
        {
            "title": result.title or result.final_url,
            "url": result.final_url,
            "aliases": sorted(set(aliases) - {result.final_url}),
            "publisher": domain.split(".")[0].title() or domain,
            "accessed": date.today().isoformat(),
            "source_family": domain,
            "published": _normalized_published(
                result.published or source.get("published")
            ),
        }
    )
    source.setdefault("author", None)
    source["provenance"] = args.provenance or source.get("provenance", "unverified")
    source["evidence_type"] = args.type or source.get("evidence_type", "news_report")
    source["roles"] = args.role or source.get("roles", ["independent_analysis"])
    source["accountability_basis"] = args.accountability or source.get(
        "accountability_basis", "none"
    )
    if existing is None:
        ledger["sources"].append(source)
    return source


def _is_cjk(ch):
    return "\u3040" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af"


def _fetch_one(ws, state, ledger, args, url, lines):
    parsed = urlsplit(url)
    if parsed.scheme.casefold() not in {"http", "https"}:
        lines.append(f"{url} REJECTED (non-http scheme) — not added")
        return False
    aliases = [url]
    target = url
    if parsed.scheme.casefold() == "http":
        target = urlunsplit(("https",) + tuple(parsed)[1:])
    existing = _source_by_url(ledger, target) or _source_by_url(ledger, url)
    if existing is not None:
        lines.append(f"{existing['source_id']} already in the ledger: {existing['url']}")
        return True
    result = source_fidelity.fetch_document(
        target,
        cache_dir=ws.sources,
        refresh=False,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    source_id = _next_id(ledger["sources"], "S", "source_id")
    if result.status == "unreachable":
        # The real class is printed, never relabelled `plaintext-http`: an agent
        # told the host is dead does not retry it over https.
        suffix = " — not added"
        if target != url:
            suffix += f"; https was tried in place of {url}"
        lines.append(
            f"{source_id} UNREACHABLE ({result.reason_class}: {result.reason})"
            f"{suffix}"
        )
        return False
    if result.status != "ok":
        lines.append(f"{source_id} UNDECODABLE ({result.reason_class}) — not added")
        return False
    text = result.text.strip()
    n = len(text)
    cjk = sum(_is_cjk(ch) for ch in text)
    if n < MIN_SOURCE_TEXT_CHARS and cjk < MIN_SOURCE_CJK_CHARS:
        lines.append(
            f"{source_id} EMPTY ({n} chars; no readable text: JS-rendered, "
            "bot-blocked or scanned) — not added"
        )
        return False
    aliases.extend(result.aliases)
    aliases.append(target)
    result.aliases = sorted(set(aliases))
    source_fidelity.write_cache(ws.sources, source_id, result)
    _upsert_source(ledger, source_id, result, args, result.aliases)
    text, _meta = cached(ws, source_id)
    lines.append(
        f"{source_id} OK {len(text)} chars {result.charset} "
        f'"{result.title}" {result.final_url}'
    )
    return True


def _refresh_one(ws, state, ledger, args, source_id, lines):
    source = next(
        (item for item in ledger["sources"] if item.get("source_id") == source_id),
        None,
    )
    if source is None:
        lines.append(f"{source_id} is not in the ledger — nothing to refresh")
        return False
    entry = cached(ws, source_id)
    previous = entry[1].get("text_sha256") if entry else None
    result = source_fidelity.fetch_document(
        source["url"],
        cache_dir=ws.sources,
        refresh=True,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    if result.status != "ok":
        lines.append(
            f"{source_id} UNREACHABLE ({result.reason_class}: {result.reason}) "
            "— cache kept"
        )
        return False
    result.aliases = sorted(set(result.aliases) | set(source.get("aliases", [])))
    source_fidelity.write_cache(ws.sources, source_id, result)
    source["accessed"] = date.today().isoformat()
    text, _meta = cached(ws, source_id)
    lines.append(
        f"{source_id} OK {len(text)} chars {result.charset} "
        f'"{result.title}" {result.final_url}'
    )
    if previous and previous != result.text_sha256:
        affected = [
            claim["claim_id"]
            for claim in ledger.get("claims", [])
            if source_id in claim.get("source_ids", [])
        ]
        if affected:
            lines.append(
                f"{source_id} text changed; claims {','.join(affected)} need re-probe"
            )
        else:
            lines.append(f"{source_id} text changed; no claims use it yet")
    return True


def _input_path(args, path):
    """C3: an input path resolves against cwd first, then against `--dir`."""
    candidate = Path(path)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    under_dir = Path(args.dir) / candidate
    return under_dir if under_dir.exists() else candidate


#: C4: the three classification flags are validated inside the command, so a
#: bad value is one warning next to the default that stands, not a parser exit.
_CLASSIFICATION_FLAGS = (
    ("--provenance", "provenance", PROVENANCES, "unverified"),
    ("--type", "type", EVIDENCE_TYPES, "news_report"),
    ("--role", "role", SOURCE_ROLES, "independent_analysis"),
)


def _classification_warnings(args):
    """Report every unknown classification value; keep the known ones."""
    messages = []
    for flag, dest, choices, default in _CLASSIFICATION_FLAGS:
        value = getattr(args, dest, None)
        values = value if isinstance(value, list) else [value]
        bad = [item for item in values if item is not None and item not in choices]
        for item in bad:
            messages.append(
                f"unknown {flag} {item!r}; stored as {default} "
                f"(choices: {', '.join(choices)})"
            )
        if bad:
            setattr(args, dest, [item for item in values if item in choices] or None)
    return messages


def cmd_fetch(args):
    ws, state, ledger = _open(args)
    lines = _classification_warnings(args)
    if args.id:
        _refresh_one(ws, state, ledger, args, args.id, lines)
    else:
        if not args.urls:
            print("`alx fetch` needs one or more URLs.", file=sys.stderr)
            return 1
        for url in args.urls:
            _fetch_one(ws, state, ledger, args, url, lines)
    ws.save_ledger(ledger)
    state["counters"]["fetch"] = state["counters"].get("fetch", 0) + 1
    ws.save_state(state)
    _emit(ws, state, "fetch", f"{len(ledger['sources'])} sources", lines)
    return 0


def cmd_source_set(args):
    ws, state, ledger = _open(args)
    source = next(
        (item for item in ledger["sources"] if item.get("source_id") == args.source_id),
        None,
    )
    if source is None:
        print(f"{args.source_id} is not in the ledger.", file=sys.stderr)
        return 1
    lines = _classification_warnings(args)
    if args.provenance:
        source["provenance"] = args.provenance
    if args.type:
        source["evidence_type"] = args.type
    if args.role:
        source["roles"] = args.role
    if args.accountability:
        source["accountability_basis"] = args.accountability
    if args.published:
        source["published"] = args.published
    if args.undated_reason:
        source["undated_reason"] = _input_path(args, args.undated_reason).read_text(
            encoding="utf-8"
        ).strip()
    if args.family_justification:
        source["family_justification"] = _input_path(args, args.family_justification).read_text(
            encoding="utf-8"
        ).strip()
    if args.accountability_note:
        source["accountability_note"] = _input_path(args, args.accountability_note).read_text(
            encoding="utf-8"
        ).strip()
    if getattr(args, "url", None):
        source["url"] = args.url
    ws.save_ledger(ledger)
    lines.append(f"{args.source_id} classification updated.")
    _emit(
        ws,
        state,
        "source set",
        f"{args.source_id} classification",
        lines,
    )
    return 0


# --------------------------------------------------------------------------
# find / show
# --------------------------------------------------------------------------


def _find_sources(ledger, value):
    """`all`, one id, or a comma list, in ledger order for `all`."""
    if str(value).strip() == "all":
        return [
            source.get("source_id")
            for source in ledger.get("sources", [])
            if isinstance(source, dict) and source.get("source_id")
        ]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _script_character_maps():
    """One table for `find` and the fidelity probe (R37.2)."""
    return source_fidelity._script_character_maps()


def _script_variants(keyword):
    """`find` keyword plus its Traditional and Simplified transliterations."""
    s2t, t2s = _script_character_maps()
    variants = [
        keyword,
        "".join(s2t.get(char, char) for char in keyword),
        "".join(t2s.get(char, char) for char in keyword),
    ]
    return list(dict.fromkeys(variants))


def cmd_find(args):
    ws, state, ledger = _open(args)
    source_ids = _find_sources(ledger, args.sources)
    caches = {}
    lines = []
    emitted = {}
    for source_id in source_ids:
        entry = cached(ws, source_id)
        if entry is None:
            lines.append(f"{source_id} has no cache; run alx fetch")
            continue
        caches[source_id] = entry[0]
    for keyword in args.keywords:
        hits = 0
        variants = _script_variants(keyword)
        for source_id, text in caches.items():
            # A Simplified keyword has to hit a Traditional source, and back.
            starts = {}
            for variant in variants:
                for match in re.finditer(re.escape(variant), text, re.IGNORECASE):
                    starts.setdefault(match.start(), len(variant))
            for index, start in enumerate(sorted(starts), start=1):
                if index > args.max:
                    break
                window = sentence_window(text, start, starts[start], args.context)
                spans = emitted.setdefault(source_id, [])
                if any(lo <= start < hi for lo, hi in spans):
                    hits += 1
                    continue
                pos = 0
                while True:
                    found = text.find(window, pos)
                    if found < 0:
                        found = start
                        break
                    if found <= start < found + len(window):
                        break
                    pos = found + 1
                spans.append((found, found + len(window)))
                hits += 1
                # One line per hit: the paste line is the window, so printing
                # the prose window as well doubled `find` output for nothing.
                lines.append(
                    f"{source_id} #{index} extract_or_location: "
                    + json.dumps(window, ensure_ascii=False)
                )
        if not hits:
            lines.append(f"no source contains {keyword}")
    _emit(ws, state, "find", f"{args.sources} {' '.join(args.keywords)}", lines)
    return 0


# --------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------


#: Spec §6.4 names exactly which families run for one claim-input object; the
#: ledger-wide rules (coverage, synthesis, portfolio, provenance) belong to
#: §6.7(b) and cannot hold before `ledger merge` has run.
CLAIM_ADD_FAMILIES = frozenset(
    {
        "ledger/claim-input",
        "ledger/extract-length",
        "ledger/quantity",
        "ledger/status",
        "ledger/direction",
        "ledger/derived",
        "ledger/person",
        "ledger/reference",
        "ledger/excluded-supports",
        "fidelity/mismatch",
        # `fidelity/context-changed` is deliberately absent: spec §7.2.6 makes
        # `claim add` the re-confirm step of the remedy, so it probes without
        # context comparison (a lost extract is still fidelity/mismatch) and
        # then rebinds the contexts. `check` and `issue` compare them.
        "fidelity/cache-missing",
    }
)

def _warn_lines(claim_id, warns):
    """Advice printed under a WARN header, after the claim's result line."""
    if not warns:
        return []
    return [f"{claim_id} WARN"] + [
        f"  [{item.family}] {item.message} — fix: {item.fix}" for item in warns
    ]


def _evidence_record_index(claim, item_finding):
    for value in item_finding.ids or ():
        text = str(value)
        if text.startswith("source_evidence[") and text.endswith("]"):
            try:
                return int(text[16:-1])
            except ValueError:
                continue
    source_id = _pick_id(item_finding, "S") or ""
    extract = None
    message = str(item_finding.message)
    for record in claim.get("source_evidence") or []:
        if not isinstance(record, dict) or record.get("source_id") != source_id:
            continue
        piece = record.get("extract_or_location") or ""
        if piece and piece[:60] in message:
            extract = piece
            break
    evidence = claim.get("source_evidence") or []
    for index, record in enumerate(evidence, start=1):
        if not isinstance(record, dict):
            continue
        if extract is not None:
            if (
                record.get("source_id") == source_id
                and record.get("extract_or_location") == extract
            ):
                return index
        elif record.get("source_id") == source_id:
            return index
    return None


def _claim_add_mismatch_lines(ws, claim, claim_id, item_finding):
    source_id = _pick_id(item_finding, "S") or ""
    index = _evidence_record_index(claim, item_finding)
    extract = ""
    evidence = claim.get("source_evidence") or []
    if index and 1 <= index <= len(evidence) and isinstance(evidence[index - 1], dict):
        extract = evidence[index - 1].get("extract_or_location") or ""
    if not extract:
        for record in evidence:
            if isinstance(record, dict) and record.get("source_id") == source_id:
                extract = record.get("extract_or_location") or ""
                break
    if not extract:
        extract = claim.get("extract_or_location") or ""
    searched = str(extract)[:60] + "…"
    loc = (
        f"source_evidence[{index}] ({source_id})"
        if index
        else source_id
    )
    lines = [
        f"{claim_id} FAIL [fidelity/mismatch] {loc} not found verbatim "
        f"(searched: {searched})"
    ]
    entry = cached(ws, source_id)
    text = entry[0] if entry else ""
    passage = source_fidelity.closest_passage(text, extract)
    if passage is None:
        keyword = source_fidelity._find_keyword(extract)
        lines.append(
            f"  no similar passage in {source_id} — alx find {source_id} {keyword}"
        )
    else:
        lines.append(
            f"  {source_id} extract_or_location: "
            + json.dumps(passage, ensure_ascii=False)
        )
    return lines


def _batch_findings(ws, ledger, item, seen_ids):
    """Only what `alx` owns: batch uniqueness and cache presence (spec §6.4)."""
    findings = []
    claim_id = item.get("claim_id")
    if isinstance(claim_id, str) and claim_id in seen_ids:
        findings.append(
            finding(
                "ledger/claim-input",
                f"{claim_id} appears twice in this batch; ids are unique.",
                ids=[claim_id],
            )
        )
    known = {source.get("source_id") for source in ledger.get("sources", [])}
    for record in item.get("source_evidence") or []:
        if not isinstance(record, dict):
            continue
        source_id = record.get("source_id", "")
        if source_id not in known:
            findings.append(
                finding(
                    "ledger/claim-input",
                    f"{source_id or '<missing>'} is not a fetched source.",
                    ids=[claim_id or ""],
                )
            )
        elif cached(ws, source_id) is None:
            findings.append(
                finding(
                    "fidelity/cache-missing",
                    f"{source_id} has no fetched cache; the extract cannot be probed.",
                    ids=[claim_id or "", source_id],
                )
            )
    return findings


def expand_claim_input(ws, item, ledger):
    """`validate_ledger.expand_claim_input` with this workspace's cache meta.

    T2 owns the ledger-schema defaults (ruling: one place owns them); `alx`
    only supplies the cache metadata the expansion reads.
    """
    source_ids = []
    for record in item.get("source_evidence") or []:
        source_id = record.get("source_id")
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    cache_meta = {}
    for source_id in source_ids:
        entry = cached(ws, source_id)
        if entry is not None:
            cache_meta[source_id] = entry[1]
    return validate_ledger.expand_claim_input(item, ledger, cache_meta=cache_meta)


def expand_file_globs(values):
    """K5: `alx` prints `claims/*.json`, so `alx` expands it.

    A remedy is copied verbatim, sometimes into a runner that does no shell
    globbing; an unexpanded pattern must name its files, not raise.
    """
    expanded = []
    for value in values:
        if not value:
            continue
        text = str(value)
        matches = sorted(glob.glob(text)) if glob.has_magic(text) else []
        # A pattern that matches nothing stays itself, so it still reports as
        # the missing file it is.
        expanded.extend(matches or [text])
    return expanded


_CLAIM_INPUT_SCHEMA = None
_EVIDENCE_ALIASES = {
    "extract": "extract_or_location",
    "quote": "extract_or_location",
    "text": "extract_or_location",
    "excerpt": "extract_or_location",
    "location": "extract_or_location",
    "source": "source_id",
    "sid": "source_id",
    "id": "source_id",
}
_SOURCE_EVIDENCE_ALIASES = ("evidence", "sources", "extracts")


def _claim_input_schema():
    global _CLAIM_INPUT_SCHEMA
    if _CLAIM_INPUT_SCHEMA is None:
        _CLAIM_INPUT_SCHEMA = json.loads(
            (ROOT / "references" / "claim-input.schema.json").read_text(
                encoding="utf-8"
            )
        )
    return _CLAIM_INPUT_SCHEMA


def _canon_prefixed_id(prefix, value):
    text = str(value).strip()
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix) :].strip()
    if text.isdigit():
        return f"{prefix}{int(text)}"
    return str(value).strip()


def _claim_id_number(value):
    text = str(value).strip()
    if text.lower().startswith("c"):
        text = text[1:].strip()
    return int(text) if text.isdigit() else None


def _next_free_claim_id(ledger, seen, batch_ids):
    numbers = []
    for value in list(seen) + list(batch_ids):
        number = _claim_id_number(value)
        if number is not None:
            numbers.append(number)
    for claim in ledger.get("claims", []):
        number = _claim_id_number(claim.get("claim_id"))
        if number is not None:
            numbers.append(number)
    return f"C{max(numbers, default=0) + 1}"


def _normalize_evidence_record(record):
    if not isinstance(record, dict):
        return record
    known = set(
        _claim_input_schema()["properties"]["source_evidence"]["items"]["properties"]
    )
    out = {}
    for key, value in record.items():
        dest = _EVIDENCE_ALIASES.get(key, key)
        if dest in known and dest not in out:
            out[dest] = value
    if "source_id" in out:
        out["source_id"] = _canon_prefixed_id("S", out["source_id"])
    return out


def _normalize_claim_input(item, ledger, seen, batch_ids):
    assigned = False
    item = dict(item)
    consumed = []
    if "source_evidence" not in item:
        for alias in _SOURCE_EVIDENCE_ALIASES:
            if alias in item:
                value = item[alias]
                item["source_evidence"] = [value] if isinstance(value, dict) else value
                consumed.append(alias)
                break
    evidence = item.get("source_evidence")
    if isinstance(evidence, dict):
        item["source_evidence"] = [_normalize_evidence_record(evidence)]
    elif isinstance(evidence, list):
        item["source_evidence"] = [_normalize_evidence_record(row) for row in evidence]
    known = set(_claim_input_schema()["properties"])
    unknown = [key for key in item if key not in known and key not in consumed]
    item = {key: value for key, value in item.items() if key in known}
    raw_id = item.get("claim_id")
    if raw_id in (None, ""):
        item["claim_id"] = _next_free_claim_id(ledger, seen, batch_ids)
        assigned = True
    else:
        item["claim_id"] = _canon_prefixed_id("C", raw_id)
    return item, assigned, unknown


def _unwrap_claim_items(payload):
    if (
        isinstance(payload, dict)
        and set(payload.keys()) == {"claims"}
        and isinstance(payload.get("claims"), list)
    ):
        return list(payload["claims"])
    if isinstance(payload, list):
        return list(payload)
    return [payload]


def cmd_claim_add(args):
    ws, state, ledger = _open(args)
    items = []
    sources = {}
    for path in expand_file_globs([str(_input_path(args, item)) for item in args.files]):
        payload = _read_json(path)
        batch = _unwrap_claim_items(payload)
        for item in batch:
            if isinstance(item, dict) and item.get("claim_id"):
                sources[_canon_prefixed_id("C", item["claim_id"])] = path
        items.extend(batch)
    lines = []
    accepted = 0
    failures = []
    seen = set()
    batch_ids = [
        _canon_prefixed_id("C", item.get("claim_id"))
        for item in items
        if isinstance(item, dict) and item.get("claim_id") not in (None, "")
    ]
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            lines.append(f"item {index} is not an object; skipped")
            continue
        item, assigned, unknown = _normalize_claim_input(
            raw, ledger, seen, batch_ids
        )
        if assigned:
            batch_ids.append(item["claim_id"])
        claim_id = item.get("claim_id") or "<no claim_id>"
        extras = []
        if unknown:
            extras.append(
                finding(
                    "ledger/claim-input",
                    f"{claim_id}: unknown fields ignored: {', '.join(unknown)}",
                    severity="warn",
                    ids=[claim_id],
                )
            )
        omitted = []
        if "kind" not in item:
            omitted.append(
                f"kind not given (recorded as {validate_ledger.CLAIM_DEFAULTS['kind']})"
            )
        if "importance" not in item:
            omitted.append(
                f"importance not given (recorded as "
                f"{validate_ledger.CLAIM_DEFAULTS['importance']})"
            )
        if omitted:
            extras.append(
                finding(
                    "ledger/claim-input",
                    f"{claim_id}: {'; '.join(omitted)}",
                    severity="warn",
                    ids=[claim_id],
                )
            )
        findings = adopt(
            extras
            + _batch_findings(ws, ledger, item, seen)
            + [
                item_finding
                for item_finding in validate_ledger.claim_findings(
                    item, ledger, cache_dir=ws.sources
                )
                if not is_finding(item_finding)
                or item_finding.family in CLAIM_ADD_FAMILIES
            ],
            # R20/K5: the file a rejected claim came from is known right here;
            # `state` only learns it after the claim is accepted, so a failing
            # claim used to be told to edit `claims/*.json`.
            claim_files=sources,
        )
        # R13: warn-tier findings are advice; only hard ones refuse the upsert.
        hard = hard_findings(findings)
        warns = [item for item in findings if item.severity == "warn"]
        if hard:
            mismatches = [
                item_finding
                for item_finding in hard
                if item_finding.family == "fidelity/mismatch"
            ]
            for mismatch in mismatches:
                lines.extend(
                    _claim_add_mismatch_lines(ws, item, claim_id, mismatch)
                )
            for item_finding in hard:
                if item_finding.family == "fidelity/mismatch":
                    continue
                message = str(item_finding.message)
                if " Missing: " in message:
                    message = message.split(" Missing: ", 1)[0]
                if item_finding.fix and "Fix:" not in message:
                    message = f"{message} — Fix: {item_finding.fix}"
                lines.append(
                    f"{claim_id} FAIL [{item_finding.family}] {message}"
                )
            failures.append(claim_id)
            continue
        claim = expand_claim_input(ws, item, ledger)
        claims = ledger.setdefault("claims", [])
        replaced = False
        for index, existing in enumerate(claims):
            if existing.get("claim_id") == claim["claim_id"]:
                claim["report_excerpts"] = existing.get("report_excerpts", [])
                claims[index] = claim
                replaced = True
                break
        if not replaced:
            claims.append(claim)
        if isinstance(item.get("report_paragraph"), int):
            state.setdefault("bindings", {})[claim["claim_id"]] = item["report_paragraph"]
            record_binding_hashes(
                state, ws.report_text(), {claim["claim_id"]: item["report_paragraph"]}
            )
        record_probe_contexts(ws, claim)
        # K5: the remedy for this claim has to name the file it came from.
        if claim["claim_id"] in sources:
            state.setdefault("claim_files", {})[claim["claim_id"]] = sources[
                claim["claim_id"]
            ]
        seen.add(claim["claim_id"])
        accepted += 1
        verb = "replaced" if replaced else "added"
        if assigned:
            lines.append(f"{claim['claim_id']} {verb} (assigned id)")
        else:
            lines.append(
                f"{claim['claim_id']} {verb} ({len(claim['source_ids'])} sources)"
            )
        lines.extend(_warn_lines(claim_id, warns))
    ws.save_ledger(ledger)
    state["counters"]["claims"] = len(ledger["claims"])
    ws.save_state(state)
    if failures:
        tail = f"{len(failures)} failed: {' '.join(failures)}"
        if any("extract_or_location:" in line for line in lines):
            tail += (
                " — paste each extract_or_location line above into a new "
                "claims file and alx claim add it"
            )
    else:
        tail = "0 failed"
    lines.insert(0, f"{len(items)} submitted, {accepted} accepted, {tail}")
    # Field test 3: the whole diagnosis survives a `| tail -15` of the output.
    transcript = ws.alx / "last-claim-add.txt"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lines.append("full output: .alx/last-claim-add.txt")
    _emit(
        ws,
        state,
        "claim add",
        f"{accepted} accepted",
        lines,
    )
    return 1 if failures else 0


def _claim_paragraph(state, claim):
    return state.get("bindings", {}).get(claim.get("claim_id"))


def record_binding_hashes(state, text, mapping):
    """K3: remember WHICH paragraph a claim was bound to: index plus exact text.

    Masked prose is not an identity — two body paragraphs can carry the same
    sentence under different citations — so the body index identifies the span
    and the hash of its exact text verifies it.
    """
    blocks = {number: block for number, _s, _e, block in body_paragraphs(text)}
    hashes = state.setdefault("binding_hashes", {})
    for claim_id, number in mapping.items():
        block = blocks.get(number)
        if block:
            hashes[claim_id] = {
                "paragraph": number,
                "sha256": _sha256_text(block),
            }
    return hashes


def cmd_claim_bind(args):
    ws, state, ledger = _open(args)
    ids = {claim.get("claim_id") for claim in ledger.get("claims", [])}
    bindings = {}
    for token in args.claims:
        # Both forms: `C1 --paragraph 3`, and any number of `C1:3 C4:15` pairs.
        claim_id, separator, number = str(token).partition(":")
        number = number if separator else args.paragraph
        try:
            paragraph = int(number)
        except (TypeError, ValueError):
            print(
                f"{token}: write `C<n>:<paragraph>` or pass --paragraph.",
                file=sys.stderr,
            )
            return 1
        if claim_id not in ids:
            print(f"{claim_id} is not in the ledger.", file=sys.stderr)
            return 1
        bindings[claim_id] = paragraph
    state.setdefault("bindings", {}).update(bindings)
    record_binding_hashes(state, ws.report_text(), bindings)
    ws.save_state(state)
    _emit(
        ws,
        state,
        "claim bind",
        ", ".join(f"{claim} -> paragraph {number}" for claim, number in bindings.items()),
        [f"{claim} is bound to paragraph {number}." for claim, number in bindings.items()],
    )
    return 0


def _drop_plan(ws, state, ledger, claim_id):
    text = ws.report_text()
    mapping, _mapping_findings = paragraph_mapping(ws, state, ledger, text)
    paragraph = mapping.get(claim_id)
    co_mapped = [
        other
        for other, number in mapping.items()
        if number == paragraph and other != claim_id and paragraph is not None
    ]
    dropped = [claim_id, *co_mapped]
    dependents = [
        claim.get("claim_id")
        for claim in ledger.get("claims", [])
        if claim.get("claim_id") not in dropped
        and set(claim.get("supports", [])) & set(dropped)
    ]
    return paragraph, co_mapped, dependents


def _paragraph_to_delete(state, text, claim_id, paragraph):
    """K3: the bound body index names the span; the recorded hash verifies it.

    `body_paragraphs` numbers the body only, so the index can never reach the
    standfirst, and it stays unique where the prose does not.
    """
    blocks = body_paragraphs(text)
    recorded = state.get("binding_hashes", {}).get(claim_id)
    recorded = recorded if isinstance(recorded, dict) else {}
    number = recorded.get("paragraph", paragraph)
    entry = next((item for item in blocks if item[0] == number), None)
    digest = recorded.get("sha256")
    if entry is None or not digest or _sha256_text(entry[3]) == digest:
        return entry
    # The hash moved: the paragraph was edited, or an untracked edit renumbered
    # the body. An exact-text match is still an identity; the index is not.
    return next(
        (item for item in blocks if _sha256_text(item[3]) == digest), entry
    )


def _renumber_bindings(state, deleted):
    """Every binding after the deleted paragraph moves up by one."""
    bindings = state.get("bindings", {})
    for other, number in list(bindings.items()):
        if isinstance(number, int) and number > deleted:
            bindings[other] = number - 1
    for recorded in state.get("binding_hashes", {}).values():
        if isinstance(recorded, dict) and recorded.get("paragraph", 0) > deleted:
            recorded["paragraph"] -= 1


def apply_drop(ws, state, ledger, claim_id, reason):
    """The §6.8 mechanical scope drop; returns the lines it would print."""
    paragraph, co_mapped, dependents = _drop_plan(ws, state, ledger, claim_id)
    lines = [
        f"{claim_id} maps to paragraph {paragraph if paragraph else '<unmapped>'}."
    ]
    if co_mapped:
        lines.append(f"Also dropped (same paragraph): {', '.join(co_mapped)}")
    if dependents:
        lines.append(
            "WARN [ledger/excluded-supports] claims that support a dropped claim: "
            + ", ".join(dependents)
        )
    dropped = [claim_id, *co_mapped]
    text = ws.report_text()
    target = _paragraph_to_delete(state, text, claim_id, paragraph)
    if target is not None:
        number, start, end, block = target
        # K3: the exact span is the deletion's identity; its masked prose is
        # what the review-freshness rule compares and what leftover prose
        # recognises, so the copies that legitimately survive it are counted.
        state.setdefault("mechanical_deletions", []).append(_sha256_text(block))
        text = re.sub(r"\n{3,}", "\n\n", text[:start] + text[end:])
        prose = _sha256_text(masked_prose(block))
        state.setdefault("mechanical_deletion_prose", {})[prose] = sum(
            1
            for _n, _s, _e, survivor in body_paragraphs(text)
            if _sha256_text(masked_prose(survivor)) == prose
        )
        ws.report.write_text(text, encoding="utf-8")
        _renumber_bindings(state, number)
        lines.append(f"Deleted paragraph {number} of report.md.")
    stamp = _now().isoformat()
    remaining = []
    ledger.setdefault("excluded_claims", [])
    for claim in ledger.get("claims", []):
        if claim.get("claim_id") in dropped:
            excluded = dict(claim)
            excluded["reason"] = reason
            excluded["dropped_at"] = stamp
            ledger["excluded_claims"].append(excluded)
        else:
            remaining.append(claim)
    ledger["claims"] = remaining
    for item in ledger.get("coverage", []):
        if not isinstance(item, dict):
            continue
        for key in ("claim_ids", "claims"):
            value = item.get(key)
            if isinstance(value, list):
                item[key] = [v for v in value if v not in dropped]
    ledger["synthesis"] = strip_synthesis(ledger.get("synthesis", {}), dropped)
    drops = state.setdefault("mechanical_drops", [])
    for value in dropped:
        state.get("bindings", {}).pop(value, None)
        state.get("binding_hashes", {}).pop(value, None)
        if value not in drops:
            drops.append(value)
    ws.save_ledger(ledger)
    ws.save_state(state)
    _regenerate_sources(ws, _bound_ledger(state, ledger), state.get("lang", "en"))
    lines.append(f"Excluded: {', '.join(dropped)}")
    return lines


def cmd_claim_drop(args):
    ws, state, ledger = _open(args)
    claim_id = args.claim_id
    if claim_id not in {claim.get("claim_id") for claim in ledger.get("claims", [])}:
        print(f"{claim_id} is not in the ledger.", file=sys.stderr)
        return 1
    if not args.apply:
        paragraph, co_mapped, dependents = _drop_plan(ws, state, ledger, claim_id)
        lines = [
            f"{claim_id} maps to paragraph {paragraph if paragraph else '<unmapped>'}."
        ]
        if co_mapped:
            lines.append(f"Also dropped (same paragraph): {', '.join(co_mapped)}")
        if dependents:
            lines.append(
                "WARN [ledger/excluded-supports] claims that support a dropped claim: "
                + ", ".join(dependents)
            )
        lines.append(f"Apply with `{remedy('claim-drop', claim_id=claim_id)}`.")
        _emit(ws, state, "claim drop", f"{claim_id} plan", lines)
        return 0
    lines = apply_drop(
        ws,
        state,
        ledger,
        claim_id,
        args.reason or "hard finding; scope dropped.",
    )
    _emit(ws, state, "claim drop", f"{claim_id} excluded", lines)
    return 0


# --------------------------------------------------------------------------
# ledger merge
# --------------------------------------------------------------------------


#: Spec §6.5: `ledger merge` deep-merges only these keys.
MERGEABLE_LEDGER_KEYS = frozenset(
    {"brief", "people", "coverage", "synthesis", "unresolved_questions"}
)


def _deep_merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def cmd_ledger_merge(args):
    ws, state, ledger = _open(args)
    try:
        patch = _read_json(_input_path(args, args.patch))
    except json.JSONDecodeError as exc:
        print(
            f"{args.patch} is not valid JSON: {exc.msg} "
            f"at line {exc.lineno} column {exc.colno}",
            file=sys.stderr,
        )
        return 1
    blocked = [key for key in ("sources", "claims") if key in patch]
    # Spec §6.5: only these keys merge; anything else is ignored with a WARN.
    merged = [
        key
        for key in patch
        if key in MERGEABLE_LEDGER_KEYS and key not in ("sources", "claims")
    ]
    ignored = [
        key
        for key in patch
        if key not in MERGEABLE_LEDGER_KEYS or key in ("sources", "claims")
    ]
    for key in merged:
        value = patch[key]
        if isinstance(value, dict):
            _deep_merge(ledger.setdefault(key, {}), value)
        else:
            ledger[key] = value
    ws.save_ledger(ledger)
    lines = [f"merged: {', '.join(merged)}"]
    for finding in validate_ledger.notes_shape_findings(ledger):
        lines.append(f"WARN {finding.message}")
    if blocked:
        lines.append(
            f"ignored keys: {', '.join(blocked)} "
            "(sources only via fetch; claims only via claim add)",
        )
        ignored = [key for key in ignored if key not in blocked]
    if ignored:
        lines.append(
            f"WARN: ignored key(s) not merged by `ledger merge`: {', '.join(ignored)} "
            f"(mergeable: {', '.join(sorted(MERGEABLE_LEDGER_KEYS))}).",
        )
    # Field test 4: a patch citing claims that were never added has to say so
    # in its first line; the per-reference WARNs scroll away.
    claims = ledger.get("claims")
    claims = claims if isinstance(claims, list) else []
    known = {
        claim.get("claim_id")
        for claim in claims
        if isinstance(claim, dict)
    }
    coverage = ledger.get("coverage")
    coverage = coverage if isinstance(coverage, list) else []
    referenced = []
    for item in coverage:
        if not isinstance(item, dict):
            continue
        referenced.extend(validate_ledger.coverage_claim_ids(item))
    synthesis = ledger.get("synthesis")
    if isinstance(synthesis, dict):
        central = synthesis.get("central_judgment_claim_ids")
        if isinstance(central, list):
            referenced.extend(central)
    missing = list(dict.fromkeys(item for item in referenced if item not in known))
    if missing:
        shown = " ".join(missing[:8])
        if len(missing) > 8:
            shown += f" +{len(missing) - 8} more"
        lines.insert(
            0,
            f"{len(missing)} claim ids not in the ledger ({shown}); "
            "run alx claim add first",
        )
    _emit(ws, state, "ledger merge", ", ".join(patch), lines)
    return 0


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


def cmd_snapshot(args):
    ws, state, ledger = _open(args)
    if args.restore:
        latest = ws.latest_snapshot()
        if latest is None:
            print("No snapshot to restore; run `alx snapshot` first.", file=sys.stderr)
            return 0
        ws.report.write_text(_snapshot_text(ws, state), encoding="utf-8")
        _emit(
            ws,
            state,
            "snapshot",
            f"restored {latest.name}",
            [f"report.md restored from {latest.name}."],
        )
        return 0
    base = ws.dir / "report.pre-rewild.md"
    # C5: a second snapshot is the next humanization round, not a refusal.
    iteration = f".iter{len(ws.snapshots())}" if base.exists() else ""
    target = ws.dir / f"report.pre-rewild{iteration}.md"
    _bind_markers(ws, state, ledger, ws.report_text())
    shutil.copyfile(ws.report, target)
    state["humanization"] = "snapshot"
    ws.save_state(state)
    _emit(ws, state, "snapshot", target.name, [f"Snapshot written: {target.name}"])
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def _snapshot_text(ws, state):
    """J6: the snapshot minus the paragraphs `claim drop --apply` deleted.

    A quotation that lived in a mechanically deleted paragraph is an allowed
    loss, and a restore must never resurrect a dropped Class-F paragraph —
    otherwise `quotation-lost` and `claim drop` chase each other.
    """
    snapshot = ws.latest_snapshot()
    if snapshot is None:
        return None
    text = snapshot.read_text(encoding="utf-8")
    deleted = set(state.get("mechanical_deletions", []))
    if not deleted:
        return text
    for _number, start, end, block in reversed(body_paragraphs(text)):
        if _sha256_text(block) in deleted:
            text = text[:start] + text[end:]
    return re.sub(r"\n{3,}", "\n\n", text)


def _effective_snapshot(ws, state):
    """J6: the snapshot the tiers compare against, minus the dropped paragraphs."""
    snapshot = ws.latest_snapshot()
    if snapshot is None:
        return None
    text = _snapshot_text(ws, state)
    if text == snapshot.read_text(encoding="utf-8"):
        return snapshot
    path = ws.alx / "snapshot.effective.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _integrity_findings(ws, state, ledger):
    """Section (a): `validate_report.integrity_findings` plus the UTF-8 guard."""
    raw = ws.report.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [finding("integrity/encoding", f"report.md is not UTF-8: {exc}.")]
    return [
        _date_line_finding(item, ws, state, ledger)
        for item in validate_report.integrity_findings(
            text,
            ledger,
            snapshot_text=_snapshot_text(ws, state),
            lang=state.get("lang", "en"),
        )
    ]


def _date_line_finding(item, ws, state, ledger):
    """`check --fix` may only be advertised where it repairs (spec §6.7).

    It normalizes the date line's whitespace; a date line in the wrong place or
    in the wrong form is a formatting defect `--fix` cannot repair, so spec
    §6.10 makes it Class A and the only honest remedy is editing `report.md`.
    """
    if not is_finding(item) or item.family != "integrity/date-line":
        return item
    if _date_line_repairable(ws, state, ledger):
        return Finding(**{**vars(item), "fix": remedy("check-fix"), "remove": ""})
    return Finding(
        **{**vars(item), "klass": "A", "fix": remedy("edit-prose"), "remove": ""}
    )


def _date_line_repairable(ws, state, ledger):
    """True when the immediate blockquote holds the date bar its whitespace."""
    try:
        expected = report_contract.localized_date(
            state.get("lang", "en"), date.fromisoformat(ledger.get("report_date", ""))
        )
    except (TypeError, ValueError):
        return False
    folded = re.sub(r"\s+", "", expected)
    return any(
        re.sub(r"\s+", "", line) == folded
        for line in _metadata_lines(ws.report_text())
    )


def _metadata_lines(text):
    lines = []
    found_h1 = False
    collecting = False
    for line in text.splitlines():
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
    return lines


def _ledger_findings(ws, ledger):
    """Section (b): T2's grouped rules plus the §6.7(b) cache binding."""
    findings = list(
        validate_ledger.collect_findings(
            ledger,
            schema_path=validate_ledger.DEFAULT_SCHEMA,
            cache_dir=ws.sources,
        )
    )
    key_source_ids = set()
    central = set(ledger.get("synthesis", {}).get("central_judgment_claim_ids", []))
    for claim in ledger.get("claims", []):
        if claim.get("importance") == "key" or claim.get("claim_id") in central:
            key_source_ids.update(claim.get("source_ids", []))
    for source in ledger.get("sources", []):
        source_id = source.get("source_id", "")
        entry = cached(ws, source_id)
        if entry is None:
            findings.append(
                finding(
                    "fidelity/cache-missing",
                    f"{source_id} has no `sources/{source_id}.txt` + meta pair.",
                    ids=[source_id],
                )
            )
            continue
        text, meta = entry
        citing = [
            claim.get("claim_id")
            for claim in ledger.get("claims", [])
            if source_id in (claim.get("source_ids") or []) and claim.get("claim_id")
        ]
        if normalize_url(source.get("url", "")) not in cache_urls(meta):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache url {meta.get('url')} != ledger url "
                    f"{source.get('url')}.",
                    ids=[source_id, *citing],
                )
            )
        elif not cache_matches(text, meta):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache text sha256 does not match its meta record.",
                    ids=[source_id, *citing],
                )
            )
        if source.get("provenance") == "unverified" and source_id in key_source_ids:
            findings.append(
                finding(
                    "ledger/provenance",
                    f"{source_id} carries a key or central claim while provenance is "
                    "`unverified` (treated as interested).",
                    # R27: the default classification is a prompt, not a refusal.
                    severity="warn",
                    ids=[source_id],
                )
            )
    return findings


#: An inline claim citation: `[C17]`, `[C3, C4]`, `[C3、C4]`, `【C3】`.
_CLAIM_MARKER_RE = re.compile(
    r"[\[【]\s*(C[0-9]+(?:\s*[,、，]\s*C[0-9]+)*)\s*[\]】]"
)


def _marker_bindings(text):
    """{claim_id: paragraph} for the inline claim markers; first occurrence wins."""
    bindings = {}
    for number, _start, _end, block in body_paragraphs(text):
        for match in _CLAIM_MARKER_RE.finditer(block):
            for claim_id in re.findall(r"C[0-9]+", match.group(1)):
                bindings.setdefault(claim_id, number)
    return bindings


def _convert_claim_markers(ws, ledger, text):
    """Rewrite `[C17]` into the markdown link of the claim's first source."""
    sources = {
        source.get("source_id"): source for source in ledger.get("sources", [])
    }
    links = {}
    for claim in ledger.get("claims", []):
        for source_id in claim.get("source_ids") or []:
            source = sources.get(source_id) or {}
            if source.get("url"):
                links[claim.get("claim_id")] = f"[{source_id}]({source['url']})"
                break

    def replace(match):
        claim_ids = re.findall(r"C[0-9]+", match.group(1))
        if not any(claim_id in links for claim_id in claim_ids):
            return match.group(0)
        # An id with no ledger claim stays a visible `[C22]` for the author.
        rendered = []
        for claim_id in claim_ids:
            link = links.get(claim_id, f"[{claim_id}]")
            if link not in rendered:
                rendered.append(link)
        return " ".join(rendered)

    converted = _CLAIM_MARKER_RE.sub(replace, text)
    if converted != text:
        ws.report.write_text(converted, encoding="utf-8")
    return converted


def _rewrite_same_page_links(ws, ledger, text):
    """R36.1: rewrite report links that differ only by www. or public suffix."""
    allowed = validate_report._ledger_url_set(ledger)
    pending = []
    for url, start, end in validate_report._markdown_url_entries(text):
        hit = validate_report.same_page_ledger_source(url, ledger)
        if not hit:
            continue
        new, source_id = hit
        if validate_report.normalize_url(url) == validate_report.normalize_url(new):
            continue
        if validate_report.normalize_url(url) in allowed:
            continue
        pending.append((start, end, url, new, source_id))
    lines = []
    for start, end, url, new, source_id in reversed(pending):
        text = text[:start] + new + text[end:]
        lines.append(f"link rewritten: {url} → {new} ({source_id})")
    lines.reverse()
    if pending:
        ws.report.write_text(text, encoding="utf-8")
    return text, lines


def _bind_markers(ws, state, ledger, text):
    """Record the marker bindings, then turn the markers into source links.

    The binding is recorded before the marker becomes a link, so it survives
    the rewrite; an explicit `claim bind` still wins. `snapshot` runs this too,
    so the pre-Rewild copy never carries a marker the report has since lost.
    """
    bindings = state.setdefault("bindings", {})
    known = {claim.get("claim_id") for claim in ledger.get("claims", [])}
    for claim_id, number in _marker_bindings(text).items():
        if claim_id in known:
            bindings.setdefault(claim_id, number)
    return _convert_claim_markers(ws, ledger, text)


def paragraph_mapping(ws, state, ledger, text):
    """({claim_id: paragraph}, {claim_id: candidates}) — spec §6.7c."""
    paragraphs = body_paragraphs(text)
    markers = _marker_bindings(text)
    urls_by_paragraph = {
        number: {normalize_url(url) for _label, url in markdown_links(block)}
        for number, _start, _end, block in paragraphs
    }
    mapping = {}
    unbound = {}
    for claim in ledger.get("claims", []):
        if not claim.get("include_in_report", True):
            continue
        claim_id = claim.get("claim_id", "")
        explicit = _claim_paragraph(state, claim)
        if explicit:
            try:
                number = int(explicit)
            except (TypeError, ValueError):
                number = None
            if number is not None and 1 <= number <= len(paragraphs):
                mapping[claim_id] = number
                continue
        if claim_id in markers:
            mapping[claim_id] = markers[claim_id]
            continue
        claim_urls = set()
        for source in ledger.get("sources", []):
            if source.get("source_id") in claim.get("source_ids", []):
                claim_urls.add(normalize_url(source.get("url", "")))
                claim_urls.update(
                    normalize_url(alias) for alias in source.get("aliases", [])
                )
        candidates = [
            number for number, urls in urls_by_paragraph.items() if urls & claim_urls
        ]
        if len(candidates) == 1:
            mapping[claim_id] = candidates[0]
        else:
            unbound[claim_id] = candidates
    return mapping, unbound


def _bound_ledger(state, ledger):
    """T4 reads `report_paragraph` off the claim; ruling R4 keeps it in state."""
    bindings = state.get("bindings", {})
    if not bindings:
        return ledger
    shadow = dict(ledger)
    shadow["claims"] = [
        dict(claim, report_paragraph=bindings[claim["claim_id"]])
        if claim.get("claim_id") in bindings
        else claim
        for claim in ledger.get("claims", [])
    ]
    return shadow


def _cited_sources(ledger, text):
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    by_url = {}
    for source in ledger.get("sources", []):
        by_url[normalize_url(source.get("url", ""))] = source
        for alias in source.get("aliases", []):
            by_url[normalize_url(alias)] = source
    ordered = []
    for _label, url in markdown_links(body):
        source = by_url.get(normalize_url(url))
        if source is not None and source not in ordered:
            ordered.append(source)
    # A bound claim cites its own sources even when the body carries no link.
    by_id = {
        source.get("source_id"): source for source in ledger.get("sources", [])
    }
    bound = [
        claim
        for claim in ledger.get("claims", [])
        if claim.get("include_in_report") is True
        and (claim.get("report_paragraph") is not None or claim.get("report_excerpts"))
    ]
    for claim in sorted(bound, key=lambda claim: claim.get("report_paragraph") or 0):
        for source_id in claim.get("source_ids") or []:
            source = by_id.get(source_id)
            if source is not None and source not in ordered:
                ordered.append(source)
    return ordered


#: The Sources heading `check --fix` writes when the report has none.
SOURCES_HEADINGS = {
    "en": "## Sources",
    "zh-CN": "## 资料来源",
    "zh-HK": "## 資料來源",
}


def _regenerate_sources(ws, ledger, lang="en"):
    text = ws.report_text()
    offset = sources_heading_offset(text)
    listing = "\n".join(
        f"- [{source.get('title', source.get('url'))}]({source.get('url')})"
        for source in _cited_sources(ledger, text)
    )
    if offset is None:
        heading = SOURCES_HEADINGS.get(lang, SOURCES_HEADINGS["en"])
        ws.report.write_text(
            text.rstrip("\n") + "\n\n" + heading + "\n\n" + listing + "\n",
            encoding="utf-8",
        )
        return True
    heading_end = text.index("\n", offset) if "\n" in text[offset:] else len(text)
    heading = text[offset:heading_end]
    ws.report.write_text(
        text[:offset] + heading + "\n\n" + listing + "\n", encoding="utf-8"
    )
    return True


def _excerpt_prose(text):
    return re.sub(r"\s+", " ", validate_report._report_prose(str(text), [])).strip()


def _excerpts_located(claim, prose):
    """True when every recorded excerpt is still in the bound paragraph."""
    excerpts = claim.get("report_excerpts") or []
    return bool(excerpts) and all(
        _excerpt_prose(excerpt) in prose for excerpt in excerpts
    )


def _subject_paragraph(claim, paragraphs):
    """The first body paragraph that states the claim's subject term (R9)."""
    terms = sorted(
        re.findall(r"[\w一-鿿]{4,}", str(claim.get("claim", ""))),
        key=len,
        reverse=True,
    )[:3]
    for number in sorted(paragraphs):
        prose = masked_prose(paragraphs[number])
        if any(term in prose for term in terms):
            return number
    return None


def _claim_paragraph_number(claim, paragraphs, mapping):
    """Where the claim is stated: its binding, its excerpt, else its subject."""
    number = mapping.get(claim.get("claim_id"))
    if number:
        return number
    for candidate, block in sorted(paragraphs.items()):
        if _excerpts_located(claim, _excerpt_prose(block)):
            return candidate
    return _subject_paragraph(claim, paragraphs)


def _excerpt_remedy(claim, claim_id, candidates, paragraphs, mapping):
    """`binding/excerpt-missing`: write it, bind it, or cite the claim."""
    if mapping.get(claim_id):
        return remedy("check-fix")
    if candidates:
        return remedy("claim-bind", claim_id=claim_id, paragraph=candidates[0])
    return add_link(_claim_paragraph_number(claim, paragraphs, mapping), claim_id)


def _binding_remedy(item, unbound):
    """J3: print the candidates `alx`'s own numbering found, never a bare `N`.

    One line binds every unbound claim at once, so a report with five of them
    costs one command instead of five.
    """
    if not is_finding(item) or item.family != "binding/claim-paragraph":
        return item
    claim_id = _pick_id(item, "C")
    pairs = [
        f"{other}:{candidates[0]}"
        for other, candidates in sorted(unbound.items())
        if candidates
    ]
    if not claim_id or not unbound.get(claim_id):
        return item
    return Finding(
        **{
            **vars(item),
            "ids": list(item.ids or []) or [claim_id],
            "fix": f"alx claim bind {' '.join(pairs)}",
            "remove": remedy("claim-drop", claim_id=claim_id),
        }
    )


def _binding_findings(ws, state, ledger, *, fix=False, rewrite_out=None):
    """Section (c): T4's binding rules, excerpt binding and leftover prose."""
    text = ws.report_text()
    mapping, unbound = paragraph_mapping(ws, state, ledger, text)
    paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
    if fix:
        text = _bind_markers(ws, state, ledger, text)
        text, rewrites = _rewrite_same_page_links(ws, ledger, text)
        if rewrite_out is not None:
            rewrite_out.extend(rewrites)
        paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
        for claim in ledger.get("claims", []):
            number = mapping.get(claim.get("claim_id"))
            block = paragraphs.get(number)
            if not block:
                continue
            prose = _excerpt_prose(block)
            # The excerpt is re-derived whenever the bound paragraph no longer
            # contains it, so a prose edit (humanization) does not leave every
            # claim "cannot be located".
            if not _excerpts_located(claim, prose):
                claim["report_excerpts"] = [prose[:EXCERPT_CHARS]]
        ws.save_ledger(ledger)
        _regenerate_sources(
            ws, _bound_ledger(state, ledger), state.get("lang", "en")
        )
        text = ws.report_text()
        mapping, unbound = paragraph_mapping(ws, state, ledger, text)
    record_binding_hashes(state, text, mapping)
    ws.save_state(state)
    findings = [
        _binding_remedy(item, unbound)
        for item in validate_report.binding_findings(
            text, _bound_ledger(state, ledger)
        )
    ]
    # Ruling R3: the schema no longer demands report_excerpts; `check`(c) does.
    for claim in ledger.get("claims", []):
        if claim.get("include_in_report") is not True:
            continue
        if claim.get("report_excerpts"):
            continue
        claim_id = claim.get("claim_id", "")
        candidates = unbound.get(claim_id)
        findings.append(
            finding(
                "binding/excerpt-missing",
                f"{claim_id} is included in the report with no report_excerpts; "
                "bind it to a paragraph, then `alx check --fix` writes the excerpt.",
                ids=[claim_id],
                # A bound claim's excerpt is written by `--fix`; an unbound one
                # with candidates needs the binding; with no candidate at all
                # the claim is cited nowhere, so R9 says where the link goes
                # (addendum 7).
                fix=_excerpt_remedy(claim, claim_id, candidates, paragraphs, mapping),
                remove=remedy("claim-drop", claim_id=claim_id),
            )
        )
    deleted = set(state.get("mechanical_deletions", []))
    survivors = state.get("mechanical_deletion_prose", {})
    seen = {}
    for number, _start, _end, block in body_paragraphs(text):
        prose = _sha256_text(masked_prose(block))
        seen[prose] = seen.get(prose, 0) + 1
        # K3: the deleted span itself, or one copy more of its prose than the
        # drop left behind. The twin that survived the drop is not leftover.
        if _sha256_text(block) in deleted or seen[prose] > survivors.get(
            prose, seen[prose]
        ):
            findings.append(
                finding(
                    "binding/leftover-prose",
                    f"paragraph {number} was dropped with its claim but is still in "
                    "report.md.",
                )
            )
    return findings, _paragraph_table(mapping, unbound)


def _paragraph_table(mapping, unbound):
    """Spec §6.7(c): every include_in_report claim, bound or not."""
    table = dict(mapping)
    for claim_id, candidates in unbound.items():
        table[claim_id] = (
            f"unbound (candidates: {', '.join(str(n) for n in candidates)})"
            if candidates
            else "unbound (no candidate)"
        )
    return table


def _rewild_findings(ws, state):
    """Section (e): the offline rewild tiers."""
    snapshot = _effective_snapshot(ws, state)
    if snapshot is None:
        return []
    run_check = getattr(rewild_gate, "run_check", None)
    if run_check is None:
        return [
            finding(
                "rewild/checker",
                "rewild evaluator unavailable: `rewild_gate.run_check` is missing, "
                "so section (e) did not run.",
            )
        ]
    note = ws.reviews / "rewild.json"
    findings = list(
        run_check(
            ws.report,
            snapshot,
            lang=state.get("lang", "en"),
            review_note_path=note if note.exists() else None,
            timeout=_checker_timeout(),
        )
    )
    _note_checker_timeout(item.message for item in findings)
    findings = [
        item
        for item in findings
        if "skipped" not in str(getattr(item, "message", ""))
    ]
    if note.exists() and _is_blank_review_note(_read_json(note), "rewild"):
        message = _blank_review_message(ws, "rewild")
        findings = [
            item
            for item in findings
            if getattr(item, "family", "") != "review/rewild"
        ]
        findings.append(finding("review/rewild", message, severity="warn"))
    return findings


def _note_field_path(entry):
    return str(entry).split(":", 1)[0].split()[0]


def _uniq_note_paths(missing):
    seen = set()
    unique = []
    for entry in missing:
        path = _note_field_path(entry)
        if path in seen:
            continue
        seen.add(path)
        unique.append(entry)
    return unique


def _plain_excerpt(text):
    """Inline markup and line wrapping removed, so a verbatim quote matches."""
    return re.sub(r"\s+", " ", re.sub(r"[*_`\[\]]", "", str(text))).strip()


_SECTION_REVIEW_TEXT_KEYS = (
    "purpose",
    "new_value",
    "evidence_or_reasoning",
    "limitation_or_tradeoff",
    "contribution_to_governing_question",
)


def _review_judgment_fields(kind):
    return (
        "fidelity_checks, findings"
        if kind == "rewild"
        else "scores, checks, section_reviews, completion_note"
    )


def _blank_review_message(ws, kind):
    path = (ws.reviews / f"{kind}.json").resolve()
    fields = _review_judgment_fields(kind)
    return (
        f"nothing filled yet — edit {path} ({fields}) and run "
        f"alx review finish {kind} again"
    )


def _review_issue_block_lines(ws, state):
    """R39.1: unfinished or blank review; one BLOCKED line per kind."""
    lines = []
    reviews = state.get("reviews") or {}
    for kind in REVIEW_KINDS:
        record = reviews.get(kind) or {}
        path = ws.reviews / f"{kind}.json"
        note = {}
        if path.exists():
            try:
                loaded = _read_json(path)
            except (OSError, json.JSONDecodeError):
                loaded = {}
            if isinstance(loaded, dict):
                note = loaded
        finished = bool(record.get("finished"))
        if finished and not _is_blank_review_note(note, kind):
            continue
        reason = "not finished" if not finished else "empty"
        fields = _review_judgment_fields(kind)
        lines.append(
            f"BLOCKED review/{kind}: reviews/{kind}.json is {reason} — "
            f"edit {path.resolve()} ({fields}), then alx review finish {kind}, "
            f"then alx issue"
        )
    return lines


def _is_blank_review_note(note, kind):
    if not isinstance(note, dict):
        return True
    if kind == "rewild":
        checks = note.get("fidelity_checks")
        checks = checks if isinstance(checks, dict) else {}
        return not any(value is True for value in checks.values())
    scores = note.get("scores")
    scores = scores if isinstance(scores, dict) else {}
    for entry in scores.values():
        entry = entry if isinstance(entry, dict) else {}
        if isinstance(entry.get("score"), int):
            return False
    checks = note.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    if any(value is True for value in checks.values()):
        return False
    if str(note.get("completion_note") or "").strip():
        return False
    for section in note.get("section_reviews") or []:
        if not isinstance(section, dict):
            continue
        for key in _SECTION_REVIEW_TEXT_KEYS:
            if str(section.get(key) or "").strip():
                return False
    return True


def _is_review_quality_line(message):
    text = str(message)
    if " scored " in text and "(< 4)" in text:
        return True
    if text.startswith("checks false:"):
        return True
    if text in {"section_reviews empty", "completion_note empty"}:
        return True
    return text.startswith("Section review") or text.startswith(
        "Duplicate section review"
    )


def _note_completeness(ws, state, ledger, kind):
    """Quality lines of one review note; metadata is never demanded here."""
    path = ws.reviews / f"{kind}.json"
    if not path.exists():
        return [f"reviews/{kind}.json is missing"]
    note = _read_json(path)
    if not isinstance(note, dict):
        return [f"reviews/{kind}.json is missing"]
    if _is_blank_review_note(note, kind):
        return [_blank_review_message(ws, kind)]
    missing = []
    if kind == "rewild":
        checks = note.get("fidelity_checks")
        checks = checks if isinstance(checks, dict) else {}
        false = [
            name
            for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
            if checks.get(name) is not True
        ]
        if false:
            missing.append("fidelity_checks false: " + ", ".join(false))
        for index, item in enumerate(note.get("findings") or [], start=1):
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            disposition = item.get("disposition")
            if category not in {"style", "region", "fidelity"}:
                category = "style"
            if disposition not in {"resolved", "rejected"}:
                disposition = "rejected"
            if category in {"region", "fidelity"} and disposition != "resolved":
                missing.append(
                    f"findings[{index}] region/fidelity not resolved"
                )
        return _uniq_note_paths(missing)
    scores = note.get("scores")
    scores = scores if isinstance(scores, dict) else {}
    for name in CONTENT_SCORE_KEYS:
        entry = scores.get(name)
        entry = entry if isinstance(entry, dict) else {}
        score = entry.get("score")
        if not isinstance(score, int) or score < 4:
            shown = score if isinstance(score, int) else "none"
            missing.append(
                f"{name} scored {shown} (< 4): revise, then alx review finish content"
            )
    checks = note.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    false = [name for name in CONTENT_CHECK_KEYS if checks.get(name) is not True]
    if false:
        missing.append("checks false: " + ", ".join(false))
    if not note.get("section_reviews"):
        missing.append("section_reviews empty")
    if not note.get("completion_note"):
        missing.append("completion_note empty")
    for index, item in enumerate(note.get("findings") or [], start=1):
        if not isinstance(item, dict):
            continue
        if item.get("severity") == "critical" and item.get("disposition") != "fixed":
            missing.append(
                f"findings[{index}].disposition (a critical finding must be fixed)"
            )
        if item.get("severity") == "major" and item.get("disposition") == "rejected":
            missing.append(f"findings[{index}] major finding rejected")
        excerpt = item.get("report_disclosure_excerpt")
        if excerpt and _plain_excerpt(excerpt) not in _plain_excerpt(ws.report_text()):
            missing.append(
                f"findings[{index}].report_disclosure_excerpt (not in report.md)"
            )
    for entry in note.get("claim_support") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("disposition") in {"", None, "supported"}:
            continue
        if not str(entry.get("note") or "").strip():
            missing.append(
                f"claim_support[{entry.get('claim_id') or '?'}].note "
                f"(why the claim is {entry.get('disposition')})"
            )
    return _uniq_note_paths(missing)


def _paragraph_set(text, state):
    limit = sources_heading_offset(text)
    body = text[:limit] if limit is not None else text
    prefix = tuple(VERIFICATION_NOTE_PREFIX.values())
    blocks = []
    for _start, _end, block in _blocks(body):
        prose = masked_prose(block)
        if prose.startswith(prefix):
            continue
        blocks.append(prose)
    return blocks


def _without_ids(values, dropped):
    return [value for value in values or [] if value not in dropped]


SYNTHESIS_BUCKETS = ("adversarial_tests", "implications", "decisions_or_takeaways")
SYNTHESIS_ID_KEYS = ("claim_ids", "rationale_claim_ids")


def strip_synthesis(synthesis, dropped):
    """Spec §6.4: a drop removes synthesis references, entries included."""
    synthesis = dict(synthesis)
    for key in ("central_judgment_claim_ids", "counterevidence_claim_ids"):
        synthesis[key] = _without_ids(synthesis.get(key), dropped)
    for bucket in SYNTHESIS_BUCKETS:
        kept = []
        for entry in synthesis.get(bucket, []):
            if isinstance(entry, dict):
                entry = dict(entry)
                emptied = False
                for key in SYNTHESIS_ID_KEYS:
                    if key in entry:
                        entry[key] = _without_ids(entry[key], dropped)
                        emptied = emptied or not entry[key]
                if emptied:
                    continue
            kept.append(entry)
        synthesis[bucket] = kept
    return synthesis


def _mechanical_ledger(ledger, state):
    """The ledger reduced to what a review must see again (spec §6.8)."""
    dropped = set(state.get("mechanical_drops", []))
    stripped = {
        key: value
        for key, value in ledger.items()
        if key not in {"claims", "sources", "excluded_claims", "coverage", "synthesis"}
    }
    stripped["claims"] = [
        {
            key: value
            for key, value in claim.items()
            if key not in {"report_excerpts", "verified_at"}
        }
        for claim in ledger.get("claims", [])
        if claim.get("claim_id") not in dropped
    ]
    stripped["sources"] = [
        {
            key: value
            for key, value in source.items()
            if key not in {"accessed", "aliases"}
        }
        for source in ledger.get("sources", [])
    ]
    stripped["coverage"] = []
    for item in ledger.get("coverage", []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        for key in ("claim_ids", "claims"):
            if key in row:
                row[key] = _without_ids(row.get(key), dropped)
        stripped["coverage"].append(row)
    stripped["synthesis"] = strip_synthesis(ledger.get("synthesis", {}), dropped)
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True)


def _review_family(kind, suffix):
    """One name set: `rewild_gate` owns `review/rewild`; `alx` owns content."""
    return "review/rewild" if kind == "rewild" else f"review/{kind}-{suffix}"


def freshness_findings(ws, state, ledger, kind):
    """Spec §6.8: current inputs must equal the reviewed copy up to mechanics."""
    record = state.get("reviews", {}).get(kind, {})
    if not record.get("finished"):
        fix = (
            f"alx review finish {kind}"
            if record.get("iteration")
            else f"alx review start {kind}"
        )
        return [
            finding(
                _review_family(kind, "missing"),
                f"the {kind} review is missing.",
                fix=fix,
            )
        ]
    reviewed = ws.review_dir(kind, record["iteration"])
    current = _paragraph_set(ws.report_text(), state)
    previous = _paragraph_set(
        (reviewed / "report.md").read_text(encoding="utf-8"), state
    )
    allowed = set(state.get("mechanical_deletion_prose", []))
    changed = [block for block in current if block not in previous]
    removed = [
        block
        for block in previous
        if block not in current and _sha256_text(block) not in allowed
    ]
    ledger_changed = False
    if kind == "content":
        reviewed_ledger = _read_json(reviewed / "ledger.json")
        ledger_changed = _mechanical_ledger(
            reviewed_ledger, state
        ) != _mechanical_ledger(ledger, state)
    if changed or removed or ledger_changed:
        n = len(changed) + len(removed)
        return [
            finding(
                _review_family(kind, "stale"),
                f"{n} paragraph(s) changed since the {kind} review — re-read them "
                f"if the change was substantive; alx review finish {kind} re-stamps.",
                fix=f"re-read the changed paragraphs, then alx review finish {kind}",
            )
        ]
    return []


_CANNOT_LOCATE = re.compile(r"Claim (C\d+) cannot be located in the report")
_NO_NEARBY_CITATION = re.compile(r"Claim (C\d+) has no nearby citation")


def _content_binding_remedies(items, ws, state, ledger):
    """A binding defect is repaired by binding, never by a new review round.

    `content_gate` reports both of these as `content/check`, whose generic
    remedy is `alx review start content --iter`; that re-review fixes nothing
    here. Ruling R9: inserting the link leaves the visible text unchanged, so
    it is a mechanical delta and the finished review stays fresh.
    """
    text = ws.report_text()
    paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
    mapping, _unbound = paragraph_mapping(ws, state, ledger, text)
    claims = {claim.get("claim_id"): claim for claim in ledger.get("claims", [])}
    repaired = []
    for item in items:
        match = _CANNOT_LOCATE.search(str(item.message)) or _NO_NEARBY_CITATION.search(
            str(item.message)
        )
        if match is None:
            repaired.append(item)
            continue
        claim_id = match.group(1)
        number = _claim_paragraph_number(
            claims.get(claim_id, {"claim_id": claim_id}), paragraphs, mapping
        )
        family = item.family
        if _CANNOT_LOCATE.search(str(item.message)):
            # `--fix` re-derives report_excerpts from the bound paragraph. That
            # is the §6.7 mechanical excerpt write, so ruling R10 lets the
            # finding advertise `--fix` — under the family that owns the repair.
            family = "binding/excerpt-missing"
            fix = (
                remedy("check-fix")
                if mapping.get(claim_id) or not number
                else remedy("claim-bind", claim_id=claim_id, paragraph=number)
            )
        else:
            fix = add_link(number, claim_id)
        repaired.append(
            Finding(
                family=family,
                severity=item.severity,
                klass=getattr(item, "klass", "F"),
                ids=list(item.ids or []) or [claim_id],
                message=item.message,
                fix=fix,
                remove=remedy("claim-drop", claim_id=claim_id),
            )
        )
    return repaired


def _content_check(ws):
    """J9: the review half of `content_gate` only.

    Its ledger half re-runs `validate_references`, which section (b) already
    reported; printed twice, the second copy carries `alx review start content
    --iter`, a remedy that repairs no ledger defect. `include_ledger_checks=False`
    drops those re-emissions and keeps the per-claim binding checks (spec §7.4).
    """
    note = ws.reviews / "content.json"
    return content_gate.run_check(
        ws.report, ws.ledger_path, note, include_ledger_checks=False
    )


def _fill_absent_review_paths(note, ws, state):
    """check/issue: fill only absent path/lang/profile; never hashes/status."""
    if not isinstance(note, dict):
        return note
    lang = state.get("lang", "en")
    if not note.get("report_path"):
        note["report_path"] = str(ws.report)
    if not note.get("ledger_path"):
        note["ledger_path"] = str(ws.ledger_path)
    if not note.get("report_lang"):
        note["report_lang"] = lang
    if not note.get("profile"):
        note["profile"] = rewild_gate.PROFILES.get(lang, ("rewild",))[0]
    return note


def _stamp_existing_review_notes(ws, state):
    for kind in REVIEW_KINDS:
        path = ws.reviews / f"{kind}.json"
        if not path.exists():
            continue
        note = _read_json(path)
        if not isinstance(note, dict):
            continue
        _fill_absent_review_paths(note, ws, state)
        _write_json(path, note)


def _review_findings(ws, state, ledger):
    """Section (f): both notes' gate checks plus §6.8 freshness."""
    _stamp_existing_review_notes(ws, state)
    findings = []
    content_path = ws.reviews / "content.json"
    if content_path.exists():
        gate = _content_check(ws)
        note = _read_json(content_path)
        if _is_blank_review_note(note, "content"):
            gate = [
                item
                for item in gate
                if not (
                    getattr(item, "family", "") in {"content/score", "content/check"}
                    and _is_review_quality_line(getattr(item, "message", ""))
                )
            ]
            gate.append(
                finding(
                    "content/check",
                    _blank_review_message(ws, "content"),
                    severity="warn",
                )
            )
        findings.extend(_content_binding_remedies(gate, ws, state, ledger))
    for kind in REVIEW_KINDS:
        note_missing = _note_completeness(ws, state, ledger, kind)
        record = state.get("reviews", {}).get(kind, {})
        family = "review/rewild" if kind == "rewild" else "review/content"
        if record.get("finished") and note_missing:
            for line in note_missing:
                findings.append(finding(family, line, severity="warn"))
            if note_missing[0].startswith("nothing filled yet"):
                continue
        findings.extend(freshness_findings(ws, state, ledger, kind))
    return findings


def mechanical_fixes(ws, state, ledger):
    """`check --fix`: derivations and refreshes only, never claim text or prose."""
    for source in ledger.get("sources", []):
        entry = cached(ws, source.get("source_id", ""))
        if entry is None:
            continue
        meta = entry[1]
        source["accessed"] = (meta.get("fetched_at") or "")[:10] or source.get(
            "accessed"
        )
        domain = _registrable_domain(source.get("url", "")) or ""
        if domain and not source.get("family_justification"):
            source["source_family"] = domain
    meta_by_source = {
        source.get("source_id"): (cached(ws, source.get("source_id", "")) or (None, {}))[1]
        for source in ledger.get("sources", [])
    }
    for claim in ledger.get("claims", []):
        derived = []
        for record in claim.get("source_evidence", []):
            source_id = record.get("source_id")
            if source_id and source_id not in derived:
                derived.append(source_id)
        if derived:
            claim["source_ids"] = derived
        claim["person_ids"] = validate_ledger.derive_person_ids(
            claim, ledger.get("people")
        )
        stamps = sorted(
            (
                meta_by_source.get(source_id, {}).get("fetched_at", "")[:10]
                for source_id in claim.get("source_ids", [])
            ),
            reverse=True,
        )
        if stamps and stamps[0]:
            claim["verified_at"] = stamps[0]
    _fix_date_line(ws, state, ledger)
    ws.save_ledger(ledger)


def _fix_date_line(ws, state, ledger):
    """Spec §6.7 `--fix`: date-line whitespace, never the date itself."""
    try:
        expected = report_contract.localized_date(
            state.get("lang", "en"), date.fromisoformat(ledger.get("report_date", ""))
        )
    except (TypeError, ValueError):
        return
    text = ws.report_text()
    if expected in _metadata_lines(text):
        return
    folded = re.sub(r"\s+", "", expected)
    replaced = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith(">")
            and re.sub(r"\s+", "", stripped.lstrip(">")) == folded
        ):
            replaced.append(f"> {expected}")
        else:
            replaced.append(line)
    updated = "\n".join(replaced) + ("\n" if text.endswith("\n") else "")
    if updated != text:
        ws.report.write_text(updated, encoding="utf-8")


def run_check(ws, state, ledger, *, fix=False, mapping_out=None, rewrite_out=None):
    """Sections (a)-(f) of spec §6.7; every evaluator runs offline, every time."""
    if fix:
        mechanical_fixes(ws, state, ledger)
    findings = []
    findings.extend(_integrity_findings(ws, state, ledger))
    if any(
        getattr(item, "family", "") == "integrity/encoding" for item in findings
    ):
        return adopt(
            findings, paragraphs=0, claim_files=state.get("claim_files", {})
        )
    findings.extend(_ledger_findings(ws, ledger))
    findings = [
        item
        for item in findings
        if getattr(item, "family", "") != "fidelity/context-changed"
    ]
    binding, mapping = _binding_findings(
        ws, state, ledger, fix=fix, rewrite_out=rewrite_out
    )
    if mapping_out is not None:
        mapping_out.update(mapping)
    findings.extend(binding)
    findings.extend(_rewild_findings(ws, state))
    findings.extend(_review_findings(ws, state, ledger))
    return adopt(
        findings,
        paragraphs=len(body_paragraphs(ws.report_text())),
        claim_files=state.get("claim_files", {}),
    )


def _record_last_check(state, findings):
    """What `alx status` reports; J7: `issue` refreshes it after its remedies."""
    state["last_check"] = {
        "at": _now().isoformat(),
        "hard": len(hard_findings(findings)),
        "families": sorted({item.family for item in findings}),
    }


def _claim_order(claim_id):
    digits = re.sub(r"\D", "", str(claim_id))
    return (int(digits) if digits else 0, str(claim_id))


def _next_step(hard):
    """C6: the two ways forward after a check; neither of them is a refusal."""
    if hard:
        return (
            f"fix HARD then `{remedy('check')}`, or `{remedy('issue')}` "
            "(it drops what is still hard)"
        )
    return f"`{remedy('issue')}`"


def _status_line(state, findings):
    next_step = _next_step(hard_findings(findings))
    return (
        f"=== STATUS: check #{state['counters']['check']}. Next: {next_step}. ==="
    )


def _length_line(ws, state):
    """Section (a): the same count, unit and band every length rule uses (R12)."""
    lang = state.get("lang", "en")
    count, unit = report_blocks.report_length(ws.report_text(), lang)
    floor, ceiling, _unit = report_contract.report_length_policy(lang)
    return f"length {count} {unit}; floor {floor}, ceiling {ceiling}"


def _cited_source_ids(ledger):
    cited = set()
    for claim in ledger.get("claims") or []:
        cited.update(claim.get("source_ids") or [])
        for evidence in claim.get("source_evidence") or []:
            if evidence.get("source_id"):
                cited.add(evidence["source_id"])
    return cited


def _source_id_sort_key(source_id):
    return int(source_id[1:]) if source_id[1:].isdigit() else source_id


def _uncited_sources_line(ws, ledger):
    cited = _cited_source_ids(ledger)
    uncited = [
        sid
        for sid in (source.get("source_id") for source in ledger.get("sources") or [])
        if isinstance(sid, str) and sid not in cited
    ]
    if not uncited:
        return None
    sizes = {}
    for source_id in uncited:
        entry = cached(ws, source_id)
        sizes[source_id] = -1 if entry is None else len(entry[0])
    # smallest first: an empty shell is what this line exists to expose
    uncited.sort(key=lambda sid: (sizes[sid], _source_id_sort_key(sid)))
    parts = [
        f"{sid} (no cache)" if sizes[sid] < 0 else f"{sid} ({sizes[sid]} chars)"
        for sid in uncited
    ]
    return f"uncited sources ({len(uncited)}): " + " ".join(parts)


def cmd_check(args):
    ws, state, ledger = _open(args)
    state["counters"]["check"] = state["counters"].get("check", 0) + 1
    mapping = {}
    rewrites = []
    findings = run_check(
        ws, state, ledger, fix=args.fix, mapping_out=mapping, rewrite_out=rewrites
    )
    ledger = ws.load_ledger()
    rows = sorted(mapping.items(), key=lambda row: _claim_order(row[0]))
    lines = list(rewrites) + [_length_line(ws, state)]
    uncited = _uncited_sources_line(ws, ledger)
    if uncited:
        lines.append(uncited)
    lines.append(
        f"claim->paragraph ({len(rows)} claims):" if rows else "claim->paragraph: none"
    )
    # R29: the whole `check` output has to stay readable in one screen, so the
    # mapping folds instead of spending one line per claim.
    pairs = [f"{claim_id}={paragraph}" for claim_id, paragraph in rows]
    lines += [
        "  " + " ".join(pairs[start : start + 8]) for start in range(0, len(pairs), 8)
    ]
    lines += [
        render_grouped(
            _check_display_findings(ws, state, findings), verbose=args.verbose
        ),
        _status_line(state, findings),
    ]
    _record_last_check(state, findings)
    ws.save_state(state)
    _emit(
        ws,
        state,
        "check",
        f"{len(hard_findings(findings))} hard",
        lines,
    )
    return 0


# --------------------------------------------------------------------------
# review lifecycle
# --------------------------------------------------------------------------


#: Spec §6.8: `review start` prints what to fill, so a model never has to read
#: `scripts/` or a schema to learn the note format. One row per JSON path:
#: allowed values, then the one-line meaning.
CONTENT_NOTE_GUIDE = (
    (
        "scores.<key>.score",
        "integer 1-5; 4 or more passes",
        "one key each: " + ", ".join(CONTENT_SCORE_KEYS),
    ),
    ("scores.<key>.rationale", "text", "why that score"),
    (
        "checks.<key>",
        "true | false; all must be true",
        "one key each: " + ", ".join(CONTENT_CHECK_KEYS),
    ),
    (
        "section_reviews[]",
        "one object per H2 section, at least one",
        "keys: section_heading, purpose, new_value, evidence_or_reasoning, "
        "limitation_or_tradeoff, contribution_to_governing_question, "
        'disposition="keep"',
    ),
    (
        "findings[]",
        "may stay empty",
        "keys: finding_id F<n>, severity critical|major|minor, category "
        "scope|evidence|reasoning|counterevidence|depth|decision_value|"
        "forecast|structure|writing, location, finding, disposition "
        "fixed|accepted_limitation|rejected, rationale, "
        "report_disclosure_excerpt (report text verbatim, or null)",
    ),
    (
        "evidence_limitations[]",
        "texts; may stay empty",
        "what the evidence cannot settle",
    ),
    (
        "visual_assets[]",
        "may stay empty",
        "keys: path, sha256, usage body|cover|body_and_cover, "
        "visible_text_and_claims_review, "
        'disposition="approved"',
    ),
    ("completion_note", "text", "what you checked and what stands"),
    (
        "claim_support[]",
        "may stay empty",
        "one entry only for a claim you qualified or removed; every other "
        "retained claim counts as supported. keys: claim_id, paragraph "
        "(integer >= 1), disposition qualified|removed, note (1+ chars)",
    ),
)


REVIEW_SET_EXAMPLE = {
    "content": "scores.question_answered.score=5 "
    "'scores.question_answered.rationale=each question has its own section'",
    "rewild": "fidelity_checks.causality=true 'findings=[]'",
}


def _rewild_note_guide():
    return (
        (
            "fidelity_checks.<key>",
            "true | false; all must be true",
            "one key each: "
            + ", ".join(sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)),
        ),
        (
            "findings[]",
            "may stay empty",
            "keys: category style|region|fidelity, finding, disposition "
            "resolved|rejected, reason",
        ),
    )


def _note_instructions(kind):
    """The printed field list `review start` owes the reviewer (item 4)."""
    guide = CONTENT_NOTE_GUIDE if kind == "content" else _rewild_note_guide()
    lines = [
        f"Edit reviews/{kind}.json in place: fill the fields below, leave the rest as written.",
        f"Or: alx review set {kind} {REVIEW_SET_EXAMPLE[kind]} "
        "(one PATH=VALUE per field; no shell heredocs)",
    ]
    lines.extend(f"  {path}: {values} — {meaning}" for path, values, meaning in guide)
    lines.append(
        f"Then `alx review finish {kind}`; it names the JSON path of whatever "
        "is still missing."
    )
    return lines


def _stamp_review_metadata(note, ws, state, kind, *, completed=False):
    """Fill workspace metadata; never a reason to refuse the note."""
    if not isinstance(note, dict):
        return note
    lang = state.get("lang", "en")
    snapshot = ws.latest_snapshot()
    note["schema_version"] = 1 if kind == "rewild" else 2
    if completed:
        note["status"] = "completed"
    note["report_path"] = str(ws.report)
    note["ledger_path"] = str(ws.ledger_path)
    note["report_sha256"] = file_sha256(ws.report)
    note["ledger_sha256"] = file_sha256(ws.ledger_path)
    note["source_sha256"] = file_sha256(snapshot) if snapshot is not None else ""
    note["report_lang"] = lang
    note["profile"] = rewild_gate.PROFILES.get(lang, ("rewild",))[0]
    note["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if not note.get("reviewer_mode"):
        note["reviewer_mode"] = "fresh_eyes"
    return note


def _note_skeleton(ws, state, kind, ledger):
    note = _stamp_review_metadata({}, ws, state, kind)
    note["status"] = "draft"
    if kind == "rewild":
        note["fidelity_checks"] = {
            name: False for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
        }
        note["findings"] = []
        return note
    note.update(
        {
            "scores": {
                name: {"score": None, "rationale": ""} for name in CONTENT_SCORE_KEYS
            },
            "checks": {name: False for name in CONTENT_CHECK_KEYS},
            "section_reviews": [
                {
                    "section_heading": heading,
                    "purpose": "",
                    "new_value": "",
                    "evidence_or_reasoning": "",
                    "limitation_or_tradeoff": "",
                    "contribution_to_governing_question": "",
                    "disposition": "keep",
                }
                for heading, _offset in validate_report._h2_sections(ws.report_text())
            ],
            "visual_assets": [],
            "findings": [],
            "evidence_limitations": [],
            "completion_note": "",
            "claim_support": [],
        }
    )
    return note


def cmd_review_start(args):
    ws, state, ledger = _open(args)
    kind = args.kind
    note_path = ws.reviews / f"{kind}.json"
    if note_path.exists() and not args.iter:
        try:
            existing = _read_json(note_path)
        except (OSError, json.JSONDecodeError):
            existing = {}
        if not _is_blank_review_note(existing, kind):
            _emit(
                ws,
                state,
                f"review start {kind}",
                "already has content",
                [
                    f"reviews/{kind}.json already has content — alx review finish "
                    f"{kind} attests it; --iter starts a new blind read and moves "
                    f"it to reviews/{kind}.iter<N>.json"
                ],
            )
            return 0
    if args.iter and note_path.exists():
        n = 1
        while (ws.reviews / f"{kind}.iter{n}.json").exists():
            n += 1
        shutil.move(str(note_path), str(ws.reviews / f"{kind}.iter{n}.json"))
    record = state["reviews"].setdefault(kind, {"iteration": 0, "finished": False})
    iteration = record["iteration"] + 1 if (args.iter or not record["iteration"]) else record["iteration"]
    target = ws.review_dir(kind, iteration)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws.report, target / "report.md")
    if kind == "content":
        shutil.copyfile(ws.ledger_path, target / "ledger.json")
    lines = []
    if args.iter and record["iteration"]:
        previous = ws.review_dir(kind, record["iteration"]) / "report.md"
        diff = [
            block
            for block in _paragraph_set(ws.report_text(), state)
            if block not in _paragraph_set(previous.read_text(encoding="utf-8"), state)
        ]
        lines.append(f"{len(diff)} paragraph(s) changed since iteration {record['iteration']}:")
        lines.extend(f"  - {block[:80]}" for block in diff[:5])
    record.update(
        {
            "iteration": iteration,
            "finished": False,
            "report_sha256": file_sha256(ws.report),
            "ledger_sha256": file_sha256(ws.ledger_path),
        }
    )
    ws.reviews.mkdir(parents=True, exist_ok=True)
    _write_json(ws.reviews / f"{kind}.json", _note_skeleton(ws, state, kind, ledger))
    ws.save_state(state)
    protocol = (
        "references/rewild-gate.md blind-review protocol"
        if kind == "rewild"
        else "references/content-quality.md §13 review protocol"
    )
    lines.append(f"Report copy for the blind read: {target}")
    lines.extend(_note_instructions(kind))
    lines.append(f"Judge the report by {protocol}.")
    lines.insert(
        0,
        f"Note to fill: {(ws.reviews / f'{kind}.json').resolve()} (edit in place)",
    )
    _emit(ws, state, f"review start {kind}", f"iteration {iteration}", lines)
    return 0


def cmd_review_finish(args):
    ws, state, ledger = _open(args)
    kind = args.kind
    record = state["reviews"].get(kind, {})
    if not record.get("iteration"):
        print(f"Run `alx review start {kind}` first.", file=sys.stderr)
        return 1
    path = ws.reviews / f"{kind}.json"
    if path.exists():
        note = _read_json(path)
        if not isinstance(note, dict):
            note = {}
        _stamp_review_metadata(note, ws, state, kind, completed=True)
        for section in note.get("section_reviews") or []:
            if isinstance(section, dict) and not section.get("disposition"):
                section["disposition"] = "keep"
        _write_json(path, note)
    target = ws.review_dir(kind, record["iteration"])
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws.report, target / "report.md")
    if kind == "content":
        shutil.copyfile(ws.ledger_path, target / "ledger.json")
    record["report_sha256"] = file_sha256(ws.report)
    record["ledger_sha256"] = file_sha256(ws.ledger_path)
    missing = _note_completeness(ws, state, ledger, kind)
    if missing:
        for field in missing:
            print(f"WARN review/{kind}: {field}")
    record["finished"] = True
    ws.save_state(state)
    _emit(
        ws,
        state,
        f"review finish {kind}",
        f"iteration {record['iteration']}",
        [f"{kind} review {record['iteration']} finished."],
    )
    return 0


_PATH_SEGMENT = re.compile(r"\.?([^[.\]]+)(?:\[(\d+)\])?")


def _assignment_tokens(path):
    tokens = []
    pos = 0
    while pos < len(path):
        match = _PATH_SEGMENT.match(path, pos)
        if match is None or match.start() != pos:
            raise KeyError(path)
        tokens.append(match.group(1))
        if match.group(2) is not None:
            tokens.append(int(match.group(2)))
        pos = match.end()
    if not tokens:
        raise KeyError(path)
    return tokens


def _set_note_path(note, path, value):
    tokens = _assignment_tokens(path)
    cur = note
    for i, token in enumerate(tokens[:-1]):
        nxt = tokens[i + 1]
        if isinstance(token, int):
            if not isinstance(cur, list) or token >= len(cur):
                raise KeyError(path)
            cur = cur[token]
            continue
        if token not in cur:
            cur[token] = [] if isinstance(nxt, int) else {}
        cur = cur[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last >= len(cur):
            raise KeyError(path)
        cur[last] = value
        return
    cur[last] = value


def _assignment_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_review_set(args):
    ws, state, _ledger = _open(args)
    kind = args.kind
    path = ws.reviews / f"{kind}.json"
    if not path.is_file():
        print(f"Run alx review start {kind} first.", file=sys.stderr)
        return 1
    note = _read_json(path)
    for raw in args.assignments:
        field, sep, value = raw.partition("=")
        if not sep:
            print(f"review set {kind}: expected PATH=VALUE, got {raw!r}", file=sys.stderr)
            return 1
        try:
            _set_note_path(note, field, _assignment_value(value))
        except (KeyError, TypeError):
            print(f"review set {kind}: no such path {field}", file=sys.stderr)
            return 1
    _write_json(path, note)
    n = len(args.assignments)
    _emit(
        ws,
        state,
        f"review set {kind}",
        f"{n} fields",
        [f"set {n} field(s) in reviews/{kind}.json"],
        worklog=False,
    )
    return 0


# --------------------------------------------------------------------------
# issue
# --------------------------------------------------------------------------


def _strip_verification_note(ws):
    text = ws.report_text()
    prefixes = tuple(VERIFICATION_NOTE_PREFIX.values())
    cleaned = []
    for _start, _end, block in _blocks(text):
        if block.strip().startswith(prefixes):
            cleaned.append(block)
    for block in cleaned:
        text = text.replace(block + "\n\n", "")
        text = text.replace(block + "\n", "")
        text = text.replace(block, "")
    if cleaned:
        ws.report.write_text(text, encoding="utf-8")


def _auto_remedies(ws, state, ledger, findings, lines):
    restore = [
        item
        for item in class_f_findings(findings)
        if item.family
        in {
            "integrity/quotation-lost",
            "integrity/control-chars",
            "integrity/replacement-char",
            "integrity/encoding",
            # The producer of a lost quotation is `rewild_gate`, which names the
            # family `fidelity/quotation-lost`; both must auto-restore.
            "fidelity/quotation-lost",
            # R30: a figure the humanize pass invented is the same class of
            # damage as a lost quotation; the snapshot is the only true text.
            "fidelity/rewild",
        }
    ]
    if restore and ws.latest_snapshot() is not None:
        try:
            ws.report.write_text(_snapshot_text(ws, state), encoding="utf-8")
            lines.append("auto-remedy: report.md restored from the latest snapshot.")
        except (UnicodeDecodeError, OSError):
            lines.append("auto-remedy: snapshot restore failed.")
    # The Remove remedy of `binding/link-not-in-ledger`: the anchor text stays,
    # the URL goes, so a link to an unfetched source never withholds delivery.
    urls = []
    for item in class_f_findings(findings):
        if item.family != "binding/link-not-in-ledger":
            continue
        match = _URL_IN_MESSAGE.search(item.message)
        if match and match.group(0) not in urls:
            urls.append(match.group(0))
    if urls:
        text = ws.report_text()
        for url in urls:
            text = re.sub(r"\[([^\]]*)\]\(\s*" + re.escape(url) + r"\s*\)", r"\1", text)
        ws.report.write_text(text, encoding="utf-8")
        lines.extend(f"link removed: {url}" for url in urls)
    leftovers = [
        item
        for item in class_f_findings(findings)
        if item.family == "binding/leftover-prose"
    ]
    if leftovers:
        text = ws.report_text()
        numbered = {
            number: (start, end, block)
            for number, start, end, block in body_paragraphs(text)
        }
        targets = []
        for item in leftovers:
            match = re.search(r"paragraph (\d+)", item.message)
            if match:
                targets.append(int(match.group(1)))
        for number in sorted(set(targets), reverse=True):
            if number not in numbered:
                text = ws.report_text()
                numbered = {
                    n: (s, e, b) for n, s, e, b in body_paragraphs(text)
                }
            if number not in numbered:
                continue
            start, end, block = numbered[number]
            state.setdefault("mechanical_deletions", []).append(_sha256_text(block))
            text = re.sub(r"\n{3,}", "\n\n", text[:start] + text[end:])
            prose = _sha256_text(masked_prose(block))
            state.setdefault("mechanical_deletion_prose", {})[prose] = sum(
                1
                for _n, _s, _e, survivor in body_paragraphs(text)
                if _sha256_text(masked_prose(survivor)) == prose
            )
            ws.report.write_text(text, encoding="utf-8")
            _renumber_bindings(state, number)
            lines.append(f"leftover prose deleted: paragraph {number}")
            numbered = {n: (s, e, b) for n, s, e, b in body_paragraphs(text)}
        ws.save_state(state)
    # C1: one line per removal, naming the family that asked for it.
    families = {}
    for item in class_f_findings(findings):
        for value in item.ids:
            if re.fullmatch(r"C\d+", str(value)):
                families.setdefault(str(value), item.family)
    claims = {claim.get("claim_id"): claim for claim in ledger.get("claims", [])}
    dropped = []
    for claim_id, family in families.items():
        if claim_id not in claims:
            continue
        text = str(claims[claim_id].get("claim", ""))[:100]
        apply_drop(ws, state, ledger, claim_id, "Class-F finding at issue.")
        lines.append(f"dropped {claim_id} ({family}): {text}")
        dropped.append(claim_id)
    if dropped:
        stamp = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        with ws.worklog.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} issue auto-drop {', '.join(dropped)}\n")
    return ws.load_state(), ws.load_ledger()


def _drop_hard(ws, state, ledger, findings, lines):
    """C1: apply every Remove remedy until nothing hard is left to remove."""
    dropped = False
    while class_f_findings(findings):
        before = len(ledger.get("claims", []))
        state, ledger = _auto_remedies(
            ws, state, ledger, class_f_findings(findings), lines
        )
        dropped = True
        findings = run_check(ws, state, ledger, fix=False)
        if len(ledger.get("claims", [])) == before:
            break
    return state, ledger, findings, dropped


def _online_findings(result):
    """Spec §6.9.2: the live statuses T1 reports, as classifiable findings.

    `check_source_fidelity` records unreachable/undecodable/mismatch on the
    check, not as a finding, so `alx` derives them here: a live MISMATCH is
    Class F, and every unverified sampled check is a Class-A availability
    finding. The quorum sentence is appended only when the sample is past
    the policy quorum.
    """
    result = result or {}
    findings = as_findings(result.get("findings"))
    checks = [item for item in result.get("checks") or [] if isinstance(item, dict)]
    unverified = [
        item for item in checks if item.get("status") in UNVERIFIED_STATUSES
    ]
    beyond_quorum = bool(checks) and len(unverified) / len(checks) > UNVERIFIED_QUORUM
    for check in checks:
        status = check.get("status")
        ids = [
            str(value)
            for value in (check.get("claim_id"), check.get("source_id"))
            if value
        ]
        detail = str(check.get("detail") or status)
        if status == "mismatch":
            findings.append(finding("fidelity/mismatch", detail, ids=ids))
        elif status in UNVERIFIED_STATUSES:
            message = detail
            if beyond_quorum:
                message = (
                    f"{detail} Unverified sources are past the "
                    f"{int(UNVERIFIED_QUORUM * 100)}% quorum."
                )
            findings.append(finding(f"fidelity/{status}", message, ids=ids))
    return findings


def _online_phase(ws, state, ledger, args, lines, delivery_notes):
    """Live fidelity only when `issue --live` is passed."""
    if not getattr(args, "live", False):
        return [], True
    receipt_path = ws.receipts / "source-fidelity.json"
    # J1: only a receipt this pass wrote may be hashed into `issue.json`, and
    # this pass is now about to write one.
    receipt_path.unlink(missing_ok=True)
    cap = ONLINE_CAP_MINUTES
    timeout = min(FETCH_TIMEOUT_SECONDS, cap * 60)
    try:
        result = source_fidelity.check_source_fidelity(
            ledger,
            sample_size=args.sample_size,
            online=True,
            timeout=timeout,
            cache_dir=ws.sources,
        )
    except Exception as exc:  # availability failures are Class A
        delivery_notes.append(f"online source fidelity failed: {exc}")
        return [], False
    _write_json(ws.alx / "fidelity-result.json", result or {})
    refreshed = list((result or {}).get("refreshed_source_ids", []))
    findings = _online_findings(result)
    if refreshed:
        for claim in ledger.get("claims", []):
            if set(claim.get("source_ids", [])) & set(refreshed):
                findings.extend(claim_probe_findings(ws, ledger, claim))
    disclosure = list((result or {}).get("disclosure_required", []))
    if disclosure:
        delivery_notes.append(
            "central-judgment evidence not re-read live: " + ", ".join(disclosure)
        )
    lines.append(
        f"source fidelity: {(result or {}).get('status', 'unknown')}, "
        f"{len(refreshed)} source(s) refreshed."
    )
    adopted = adopt(findings, online=True)
    blocking = class_f_findings(adopted)
    if not blocking:
        # The receipt is written from this same pass; there is no second fetch.
        try:
            source_fidelity.issue_source_fidelity_receipt(
                ws.ledger_path,
                receipt_path,
                sample_size=args.sample_size,
                timeout=timeout,
                cache_dir=ws.sources,
                force=True,
                result=result,
            )
        except Exception as exc:  # a refused receipt is Class A
            delivery_notes.append(f"source-fidelity receipt not issued: {exc}")
    unverified = [item for item in adopted if item.klass == "A"]
    if unverified:
        # The detail is printed; the delivery note itself is prose that goes
        # into the report's Verification note, so it carries no ids or figures.
        lines.append(render_grouped(unverified))
        delivery_notes.extend(
            f"{family}: a sampled source was not re-read live; the recorded "
            "cache stands as its evidence"
            for family in sorted({item.family for item in unverified})
        )
    return blocking, True


def _verify_receipts_in_process(ws, state, receipts, delivery_notes):
    """Spec §6.9.4: validate_report `--fast --final-once`; never a second fetch."""
    if not {"rewild", "content"} <= set(receipts):
        return
    fidelity_receipt = ws.receipts / "source-fidelity.json"
    if not fidelity_receipt.exists() or _source_fidelity_receipt_stale(
        fidelity_receipt, ws.ledger_path, ws.report
    ):
        # K4 / R35.13: `--fast` requires a current receipt; stale = absent.
        return
    argv = [
        str(ws.report),
        "--ledger",
        str(ws.ledger_path),
        "--rewild-receipt",
        str(receipts["rewild"]),
        "--content-receipt",
        str(receipts["content"]),
        "--source-fidelity-receipt",
        str(ws.receipts / "source-fidelity.json"),
        "--expected-lang",
        state.get("lang", "en"),
        "--min-sections",
        "3",
        "--fast",
    ]
    result_path = ws.alx / "fidelity-result.json"
    if result_path.exists():
        argv.extend(["--final-once", str(result_path)])
    captured = io.StringIO()
    with redirect_stdout(captured), redirect_stderr(captured):
        validate_report.main(argv)
    errors = [
        line.removeprefix("[FAIL] ")
        for line in captured.getvalue().splitlines()
        if line.startswith("[FAIL] ")
    ]
    if errors:
        delivery_notes.append(
            "validate_report --fast --final-once failed: " + " | ".join(errors[:3])
        )


def _source_fidelity_receipt_stale(path, ledger_path, report_path=None):
    """True when the file exists but ledger/report hashes no longer match."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("ledger_sha256") != file_sha256(ledger_path):
        return True
    recorded_report = payload.get("report_sha256")
    return bool(
        recorded_report
        and report_path is not None
        and recorded_report != file_sha256(report_path)
    )


def _receipt_phase(ws, state, ledger, lines, delivery_notes):
    """Step 4 receipts; the rule tiers were already classified by `check`."""
    # Ruling R11: the gate compares against the EFFECTIVE snapshot (the
    # snapshot minus the paragraphs `claim drop --apply` deleted), exactly as
    # check does. Those deletions are mechanical per spec 6.8, so a quotation
    # that only lived in a dropped paragraph is not a lost quotation.
    original = ws.latest_snapshot()
    snapshot = _effective_snapshot(ws, state)
    receipts = {}
    for kind in REVIEW_KINDS:
        note_path = ws.reviews / f"{kind}.json"
        if not note_path.exists():
            continue
        note = _read_json(note_path)
        if not isinstance(note, dict):
            continue
        _fill_absent_review_paths(note, ws, state)
        _write_json(note_path, note)
    blocking = []
    rewild_receipt = ws.receipts / "rewild.json"
    # R28: a gate returns its warnings next to its errors; only the hard tier
    # withholds a receipt.
    errors = gate_severity.hard_errors(rewild_gate.run_gate(
        ws.report,
        snapshot,
        report_lang=state.get("lang", "en"),
        review_note_path=ws.reviews / "rewild.json",
        receipt_path=rewild_receipt,
        force=True,
        timeout=_checker_timeout(),
        snapshot_sha256=file_sha256(original) if original is not None else None,
    ))
    _note_checker_timeout(errors)
    if errors:
        blocking.extend(_refused_receipt(_rewild_findings(ws, state)))
        delivery_notes.append(f"rewild receipt not issued: {errors[0]}")
    else:
        receipts["rewild"] = rewild_receipt
    content_receipt = ws.receipts / "content.json"
    fidelity_receipt = ws.receipts / "source-fidelity.json"
    fidelity_stale = _source_fidelity_receipt_stale(
        fidelity_receipt, ws.ledger_path, ws.report
    )
    if fidelity_stale:
        lines.append(STALE_FIDELITY_WARN)
    errors = gate_severity.hard_errors(content_gate.run_content_gate(
        ws.report,
        ws.ledger_path,
        ws.reviews / "content.json",
        content_receipt,
        source_fidelity_receipt_path=fidelity_receipt,
        force=True,
    ))
    if errors:
        blocking.extend(_refused_receipt(_content_check(ws)))
        delivery_notes.append(f"content receipt not issued: {errors[0]}")
    else:
        receipts["content"] = content_receipt
        if not fidelity_receipt.exists():
            delivery_notes.append(
                "source fidelity: offline — extracts were verified verbatim "
                "at claim add; alx issue --live re-reads a sample of cited pages"
            )
    _verify_receipts_in_process(ws, state, receipts, delivery_notes)
    lines.append(f"receipts written: {', '.join(sorted(receipts)) or 'none'}")
    return receipts, blocking


def _refused_receipt(findings):
    """J5: a refused gate keeps its producer's class, never `tooling/receipt`."""
    return class_f_findings(adopt(as_findings(findings)))


def cmd_issue(args):
    ws, state, ledger = _open(args)
    lines = []
    delivery_notes = []
    review_blocks = _review_issue_block_lines(ws, state)
    if review_blocks:
        state["last_issue"] = {"blocked": len(review_blocks)}
        ws.save_state(state)
        lines.append(BLOCKED_HEADER)
        lines.extend(review_blocks)
        _emit(ws, state, "issue", f"blocked {len(review_blocks)}", lines)
        return 1
    findings = run_check(ws, state, ledger, fix=False)
    state, ledger, findings, _dropped = _drop_hard(
        ws, state, ledger, findings, lines
    )
    # J7: `alx status` must report what `issue` just saw, remedies included.
    _record_last_check(state, findings)
    ws.save_state(state)
    refusals = _collect_refusals(ws, state, ledger, findings)
    if refusals:
        state["last_issue"] = {"blocked": len(refusals)}
        ws.save_state(state)
        lines.append(_render_blocked(refusals))
        _emit(ws, state, "issue", f"blocked {len(refusals)}", lines)
        return 1
    state["last_issue"] = {"blocked": 0}
    ws.save_state(state)
    reminders = [item for item in findings if item.family in REMINDER_FAMILIES]
    if reminders:
        lines.append(REMINDER_HEADER)
        lines.append(_render_reminders(reminders))
    online_findings, _ok = _online_phase(
        ws, state, ledger, args, lines, delivery_notes
    )
    if online_findings:
        # Spec §6.9.1 + J5: the drops change the report and the ledger, so the
        # whole offline check runs again over what is actually delivered.
        state, ledger = _auto_remedies(ws, state, ledger, online_findings, lines)
        findings = run_check(ws, state, ledger, fix=False)
        state, ledger, findings, _again = _drop_hard(
            ws, state, ledger, findings, lines
        )
        _record_last_check(state, findings)
        ws.save_state(state)
        # J1: the receipt is owed by the ledger that is actually delivered, so
        # the live pass runs once more over the ledger minus the dropped claims.
        _online_phase(ws, state, ledger, args, lines, delivery_notes)
    still_hard = class_f_findings(findings)
    if still_hard:
        # C1: nothing refuses, so what could not be removed is still printed.
        lines.append(render_grouped(still_hard))
    _strip_verification_note(ws)
    receipts, gate_blocking = _receipt_phase(ws, state, ledger, lines, delivery_notes)
    if gate_blocking:
        # C1: a refused gate is printed and noted; it no longer withholds the
        # receipts.
        lines.append(render_grouped(gate_blocking))
    # R28: every warning is recorded and none of them withholds the delivery.
    warning_notes = [
        f"{item.family}: {item.message}"
        for item in findings
        if item.severity == "warn"
    ]
    if delivery_notes or warning_notes:
        _write_json(
            ws.receipts / "delivery-notes.json",
            {
                "written_at": _now().isoformat(),
                "notes": delivery_notes + warning_notes,
            },
        )
    for note in delivery_notes:
        lines.append(f"note: {note}")
    receipt = {
        "schema_version": 1,
        "issued_at": _now().isoformat(),
        "report_sha256": file_sha256(ws.report),
        "ledger_sha256": file_sha256(ws.ledger_path),
        "receipts": {
            name: file_sha256(path) for name, path in sorted(receipts.items())
        },
        "notes": {
            kind: file_sha256(ws.reviews / f"{kind}.json")
            for kind in REVIEW_KINDS
            if (ws.reviews / f"{kind}.json").exists()
        },
        "checkers": {
            "alx": "09-14-01",
            "rewild_gate": getattr(rewild_gate, "SCHEMA_VERSION", 1),
        },
        "delivery_notes": delivery_notes,
    }
    fidelity_receipt = ws.receipts / "source-fidelity.json"
    if fidelity_receipt.exists() and not _source_fidelity_receipt_stale(
        fidelity_receipt, ws.ledger_path, ws.report
    ):
        receipt["receipts"]["source-fidelity"] = file_sha256(fidelity_receipt)
    _write_json(ws.receipts / "issue.json", receipt)
    state["counters"]["issue"] = state["counters"].get("issue", 0) + 1
    ws.save_state(state)
    lines.append(f"receipts/issue.json written; next: `{remedy('render')}`.")
    _emit(ws, state, "issue", "issued", lines)
    return 0


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def _record_render_note(ws, note):
    """D4b: a degraded render is recorded where every other Class A note is."""
    path = ws.receipts / "delivery-notes.json"
    payload = _read_json(path) if path.exists() else {}
    notes = list(payload.get("notes", [])) if isinstance(payload, dict) else []
    notes.append(note)
    _write_json(path, {"written_at": _now().isoformat(), "notes": notes})


def _contact_sheet_status(result):
    """F1: render_pages returns (backend, failures); mocks may return a list."""
    if isinstance(result, tuple) and len(result) == 2:
        selected, failures = result
        return selected, list(failures or [])
    return None, []


def _pdfkit_failure_reason(failures):
    for item in failures:
        if item.startswith("pdfkit:"):
            return item.split(":", 1)[1].strip()
    return ""


def _note_pdfkit_contact_fallback(ws, lines, template, selected, failures):
    """F1: PDFKit failure stays visible when a later backend wrote the sheet."""
    reason = _pdfkit_failure_reason(failures)
    if not reason or not selected or selected == "pdfkit":
        return
    note = (
        f"{template} contact sheet: PDFKit failed ({reason}); "
        f"rendered with {selected}"
    )
    _record_render_note(ws, note)
    lines.append(
        render_grouped(
            [finding("tooling/render", f"{note}.", fix=remedy("render"))]
        )
    )


def cmd_render(args):
    ws, state, ledger = _open(args)
    receipt_path = ws.receipts / "issue.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else {}
    if receipt.get("report_sha256") != file_sha256(ws.report) or receipt.get(
        "ledger_sha256"
    ) != file_sha256(ws.ledger_path):
        # C2: a missing or stale receipt is the issue step `render` runs itself.
        issue_code = cmd_issue(
            argparse.Namespace(
                dir=args.dir, deliver=False, sample_size=8, offline=False, live=False
            )
        )
        if issue_code:
            return issue_code
        ws, state, ledger = _open(args)
    from scripts import md_to_pdf, render_pdf_pages  # heavy import, render only

    subject = f"{ledger.get('subject', '')} {ledger.get('research_question', '')}"
    templates = (
        [args.template]
        if args.template
        else ["executive", md_to_pdf.select_adaptive_companion(subject)]
    )
    lines = []
    fidelity_path = ws.receipts / "source-fidelity.json"
    fidelity_stale = _source_fidelity_receipt_stale(
        fidelity_path, ws.ledger_path, ws.report
    )
    if fidelity_stale:
        lines.append(STALE_FIDELITY_WARN)
    written = 0
    usable = 0
    for template in templates:
        output = ws.dir / f"report-{template}.pdf"
        kwargs = {
            "template": template,
            "lang": state.get("lang", "en"),
            "ledger": str(ws.ledger_path),
            "force": True,
        }
        for name, path in (
            ("rewild_receipt", ws.receipts / "rewild.json"),
            ("content_receipt", ws.receipts / "content.json"),
            ("source_fidelity_receipt", fidelity_path),
        ):
            if path.exists() and not (
                name == "source_fidelity_receipt" and fidelity_stale
            ):
                kwargs[name] = str(path)
        kwargs["issue_receipt"] = str(receipt_path)
        try:
            md_to_pdf.render_pdf(str(ws.report), str(output), **kwargs)
        except Exception as exc:
            # R28: `render` produces what it can; a gate receipt `issue` could
            # not write is a recorded warning, not a refusal.
            note = f"{template} not rendered: {exc}"
            _record_render_note(ws, note)
            lines.append(
                render_grouped(
                    [finding("tooling/render", f"{note}.", fix=note)]
                )
            )
            continue
        written += 1
        pages = ws.dir / f"pages-{template}"
        lines.append(f"{template}: {output}")
        # README: "after generation, the PDF is reopened to check text, links,
        # fonts, pagination, and overflow" — the July flow ran
        # `validate_report --pdf` right after md_to_pdf; render does it here.
        try:
            pdf_errors = validate_report.validate_pdf(
                output,
                min_pages=0,
                min_text_chars=5000,
                min_links=1,
                expected_lang=state.get("lang", "en"),
            )
        except Exception as exc:
            pdf_errors = [f"PDF check did not run: {exc}"]
        for error in pdf_errors:
            lines.append(f"{template} PDF check: {error}")
        if not pdf_errors:
            lines.append(f"{template} PDF check: passed (text, links, fonts, pages, overflow)")
        chars = getattr(pdf_errors, "text_chars", 0)
        if chars < 500:
            lines.append(
                f"{template} PDF: extractable text {chars} characters "
                "(blocked below 500)."
            )
        else:
            usable += 1
        # `alx` owns the contact-sheet directory: a second `render` refills it
        # instead of refusing because it is not empty.
        shutil.rmtree(pages, ignore_errors=True)
        try:
            # Darwin Preview path requests PDFKit first (AUTO_FALLBACK[0]).
            # Off darwin the call stays the default auto chain, no extra print.
            if sys.platform == "darwin":
                result = render_pdf_pages.render_pages(
                    str(output), str(pages), backend="auto"
                )
            else:
                result = render_pdf_pages.render_pages(str(output), str(pages))
        except Exception as exc:  # D4b: every rasterizer backend failed
            # Spec §6.10/§6.11: a rasterizer failure is Class A. The PDF is
            # already written, so the contact sheet is the only loss and the
            # next template still renders.
            note = f"{template} contact sheet not rendered: {exc}"
            _record_render_note(ws, note)
            lines.append(
                render_grouped(
                    [finding("tooling/render", f"{note}.", fix=remedy("render"))]
                )
            )
            continue
        if sys.platform == "darwin":
            selected, failures = _contact_sheet_status(result)
            _note_pdfkit_contact_fallback(ws, lines, template, selected, failures)
        lines.append(f"{template} contact sheet: {pages}")
    if not written or not usable:
        lines.append(BLOCKED_HEADER)
        if not written:
            lines.append("no PDF file produced by any template.")
        else:
            lines.append(
                "produced PDF extractable text is under 500 characters."
            )
        _emit(ws, state, "render", "blocked", lines)
        return 1
    _emit(ws, state, "render", f"{len(templates)} PDFs", lines)
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def cmd_status(args):
    ws, state, ledger = _open(args)
    last = state.get("last_check") or {}
    reviews = state.get("reviews", {})
    lines = [
        f"sources {len(ledger.get('sources', []))}",
        f"claims {len(ledger.get('claims', []))}",
        f"snapshot {'yes' if ws.latest_snapshot() else 'no'}",
        "reviews "
        + ", ".join(
            f"{kind}={'finished' if reviews.get(kind, {}).get('finished') else 'pending'}"
            for kind in REVIEW_KINDS
        ),
        f"receipts {'issued' if (ws.receipts / 'issue.json').exists() else 'none'}",
        f"PDFs {len(list(ws.dir.glob('report-*.pdf')))}",
        "last check "
        + (
            f"#{state['counters'].get('check', 0)} with {last.get('hard', 0)} hard "
            if last
            else "not run"
        ),
        f"Next: {_next_command(ws, state, ledger)}",
    ]
    _emit(ws, state, "status", "phase checklist", lines)
    return 0


def _next_command(ws, state, ledger):
    blocked = (state.get("last_issue") or {}).get("blocked") or 0
    if blocked:
        return f"`alx issue` (blocked: {blocked} items)"
    if not ledger.get("sources"):
        return "`alx fetch <url>`"
    if not ledger.get("claims"):
        return "`alx claim add claims/batch.json`"
    last = state.get("last_check")
    if not last:
        return f"`{remedy('check-fix')}`"
    if last.get("hard"):
        # C6: the snapshot and both reviews are optional, so the only ways
        # forward are a fix or the issue that drops what is still hard.
        return _next_step(True)
    if not (ws.receipts / "issue.json").exists():
        return f"`{remedy('issue')}`"
    receipt = _read_json(ws.receipts / "issue.json")
    fresh = receipt.get("report_sha256") == file_sha256(
        ws.report
    ) and receipt.get("ledger_sha256") == file_sha256(ws.ledger_path)
    pdfs = list(ws.dir.glob("report-*.pdf"))
    if pdfs and fresh:
        names = [path.name for path in pdfs]
        prefer = ("report-executive.pdf", "report-atlas.pdf")
        ordered = [name for name in prefer if name in names]
        ordered.extend(sorted(name for name in names if name not in ordered))
        return f"deliver {', '.join(ordered)} and report.md"
    if not fresh:
        return f"`{remedy('check-fix')}` / `{remedy('issue')}`"
    return f"`{remedy('render')}`"


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="alx", description="Alexandria research workspace commands"
    )
    parser.add_argument(
        "--dir", default=".", help="report workspace directory (default: .)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create the workspace")
    init.add_argument("directory")
    init.add_argument("--lang", choices=LANGUAGES, required=True)
    init.add_argument("--subject", required=True, help="file holding the subject")
    # Default None so `cmd_init` can say whether the archetype was inferred.
    init.add_argument(
        "--archetype",
        choices=ARCHETYPES,
        default=None,
        help="optional; stored, never required",
    )
    init.add_argument("--reader", help="file holding the intended reader")
    init.add_argument("--budget-minutes", type=int, default=30)
    init.add_argument("--force", action="store_true")
    init.set_defaults(
        handler=cmd_init,
        file_args=(("--subject", "subject"), ("--reader", "reader")),
    )

    fetch = subparsers.add_parser("fetch", help="fetch sources into the cache")
    fetch.add_argument("urls", nargs="*")
    fetch.add_argument("--id", dest="id", help="ledger source id to refresh")
    fetch.add_argument(
        "--refresh",
        action="store_true",
        help="accepted with --id; --id already refreshes the cache",
    )
    fetch.add_argument(
        "--provenance", help="optional; stored, not used for the report"
    )
    fetch.add_argument("--type", help="optional; stored, not used for the report")
    fetch.add_argument(
        "--role", action="append", help="optional; stored, not used for the report"
    )
    fetch.add_argument(
        "--accountability",
        choices=ACCOUNTABILITY_BASES,
        help="optional; stored, not used for the report",
    )
    fetch.set_defaults(handler=cmd_fetch)

    source = subparsers.add_parser("source", help="source classification")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_set = source_sub.add_parser("set")
    source_set.add_argument("source_id")
    source_set.add_argument("--provenance")
    source_set.add_argument("--type")
    source_set.add_argument("--role", action="append")
    source_set.add_argument("--accountability", choices=ACCOUNTABILITY_BASES)
    source_set.add_argument("--published")
    source_set.add_argument("--undated-reason", dest="undated_reason")
    source_set.add_argument("--family-justification", dest="family_justification")
    source_set.add_argument("--accountability-note", dest="accountability_note")
    source_set.add_argument("--url", dest="url")
    source_set.set_defaults(
        handler=cmd_source_set,
        file_args=(
            ("--undated-reason", "undated_reason"),
            ("--family-justification", "family_justification"),
            ("--accountability-note", "accountability_note"),
        ),
    )

    find = subparsers.add_parser("find", help="verbatim windows from the cache")
    find.add_argument("sources", help="one id, a comma list, or `all`")
    find.add_argument("keywords", nargs="+")
    find.add_argument("--context", type=int, default=160)
    find.add_argument("--max", type=int, default=3)
    find.set_defaults(handler=cmd_find)

    claim = subparsers.add_parser("claim", help="claim lifecycle")
    claim_sub = claim.add_subparsers(dest="claim_command", required=True)
    claim_add = claim_sub.add_parser("add")
    claim_add.add_argument("files", nargs="+")
    claim_add.set_defaults(handler=cmd_claim_add, file_args=(("FILE", "files"),))
    claim_drop = claim_sub.add_parser("drop")
    claim_drop.add_argument("claim_id")
    claim_drop.add_argument("--apply", action="store_true")
    claim_drop.add_argument("--reason")
    claim_drop.set_defaults(handler=cmd_claim_drop)
    claim_bind = claim_sub.add_parser("bind")
    claim_bind.add_argument("claims", nargs="+", metavar="C<n>[:<paragraph>]")
    claim_bind.add_argument("--paragraph", type=int)
    claim_bind.set_defaults(handler=cmd_claim_bind)

    ledger = subparsers.add_parser("ledger", help="ledger edits")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_merge = ledger_sub.add_parser("merge")
    ledger_merge.add_argument("patch")
    ledger_merge.set_defaults(handler=cmd_ledger_merge, file_args=(("PATCH", "patch"),))

    snapshot = subparsers.add_parser("snapshot", help="pre-humanization snapshot")
    snapshot.add_argument("--restore", action="store_true")
    snapshot.set_defaults(handler=cmd_snapshot)

    check = subparsers.add_parser("check", help="every offline evaluator, grouped")
    check.add_argument("--fix", action="store_true")
    check.add_argument(
        "--verbose",
        action="store_true",
        help="print every WARN item instead of one line per family",
    )
    check.set_defaults(handler=cmd_check)

    review = subparsers.add_parser("review", help="review lifecycle")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_start = review_sub.add_parser("start")
    review_start.add_argument("kind", choices=REVIEW_KINDS)
    review_start.add_argument("--iter", action="store_true")
    review_start.set_defaults(handler=cmd_review_start)
    review_finish = review_sub.add_parser("finish")
    review_finish.add_argument("kind", choices=REVIEW_KINDS)
    review_finish.set_defaults(handler=cmd_review_finish)
    review_set = review_sub.add_parser("set")
    review_set.add_argument("kind", choices=REVIEW_KINDS)
    review_set.add_argument("assignments", nargs="+")
    review_set.set_defaults(handler=cmd_review_set)

    issue = subparsers.add_parser("issue", help="receipts, once, at the end")
    issue.add_argument(
        "--live",
        action="store_true",
        help="re-read a sample of the cited pages",
    )
    issue.add_argument(
        "--offline",
        action="store_true",
        help="accepted, ignored",
    )
    issue.add_argument("--sample-size", type=int, default=8)
    issue.set_defaults(handler=cmd_issue)

    render = subparsers.add_parser("render", help="PDFs from a passed issue")
    render.add_argument("--template")
    render.set_defaults(handler=cmd_render)

    status = subparsers.add_parser("status", help="elapsed, phase, next command")
    status.set_defaults(handler=cmd_status)
    return parser


def missing_file_arguments(args):
    """J1: every FILE-typed argument is a path, checked before any handler runs.

    D10 routes free text through files, so prose passed inline must fail with
    one line and exit 2, never with a `FileNotFoundError` from deep in a
    command. `file_args` on each subparser names the flags that take a path.
    """
    missing = []
    cwd = Path.cwd()
    for flag, dest in getattr(args, "file_args", ()):
        value = getattr(args, dest, None)
        # K5: a FILE argument may arrive as an unexpanded glob (spec D14
        # prints one); it is a path when it names at least one file.
        for path in expand_file_globs(value if isinstance(value, list) else [value]):
            if path and not _input_path(args, path).is_file():
                # C3: both locations tried, so the model can see which one to
                # write the file to.
                missing.append(
                    f"{flag}: no file at {Path(path).resolve()} nor at "
                    f"{(Path(args.dir) / path).resolve()} (cwd {cwd})"
                )
    return missing


def main(argv=None):
    argv = sys.argv[1:] if argv is None else [str(item) for item in argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    code = relocate(argv)
    if code is not None:
        return code
    missing = missing_file_arguments(args)
    for message in missing:
        print(message, file=sys.stderr)
    if missing:
        return 2
    try:
        return args.handler(args)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
