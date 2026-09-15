#!/usr/bin/env python3
"""Alexandria's single entry point: one CLI over the research gates.

`alx` is thin orchestration over the existing modules used as libraries
(spec 09-14-01 §5). Free text enters only through files; every command
appends one worklog line and prints the elapsed/remaining footer last.
"""

import argparse
import functools
import glob
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
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
LIVING_STATUSES = ("living", "recently_deceased", "deceased", "unknown")
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
    "claim-bind": "alx claim bind {claim_id} --paragraph {paragraph}",
    "ledger-merge": "alx ledger merge {file}",
    "source-set": "alx source set {source_id} --provenance primary_independent",
    "source-family-justification": (
        "alx source set {source_id} --family-justification family-justification.txt"
    ),
    "find": "alx find {source_id} {keyword}",
    "snapshot-restore": "alx snapshot --restore",
    "review-start": "alx review start {kind}",
    "review-iter": "alx review start {kind} --iter",
    "review-restore": "alx review restore {kind}",
    "check": "alx check",
    "check-fix": "alx check --fix",
    "issue": "alx issue",
    "issue-deliver": "alx issue --deliver",
    "render": "alx render",
    "set-field": "set field {field} in {file}",
    # Addendum 6: a claim field re-enters the ledger only through `claim add`.
    "set-field-claim": "set field {field} in {file}, then alx claim add {file}",
    # J4: a refresh alone leaves the recorded probe contexts behind; only
    # `claim add` re-binds them, so the remedy is the two-step sequence.
    "refresh-rebind": "alx fetch --id {source_id} --refresh, then alx claim add {file}",
    "extend-quote": "extend the quote in {file}",
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
    re.compile(r"^alx fetch --id S\d+ --refresh, then alx claim add \S+$"),
    # A month-day extract cannot be found under the claim's full date: the
    # repair is a second extract stating the year, or the source's own wording.
    re.compile(
        r"^add a second extract from S\d+ that states the year "
        r"\(alx find S\d+ [^()]+\), or reword the claim to the source's "
        r"form \(.+\)$"
    ),
    re.compile(r"^extend the quote in \S+$"),
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
#: unusable beyond the policy quorum, which `--deliver` may waive (spec §6.10).
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
FETCH_TIMEOUT_SECONDS = 10
REWILD_CHECKER_TIMEOUT_SECONDS = 120
RESERVE_MINUTES = 8
FETCH_STOP_MINUTES = 20
DEGRADE_MINUTES = 15
ONLINE_CAP_MINUTES = 4
EXCERPT_CHARS = 60
MIN_EXTRACT_CHARS = 20
MAX_WINDOW_CHARS = 300
MAX_FINDING_CHARS = 800

DEGRADE_INSTRUCTION = (
    "remaining <= 15 min: stop fixing, run `alx issue --deliver`, then `alx render`."
)


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
        "review/content-stale",
        "fidelity/unreachable",
        "fidelity/undecodable",
    }
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
        # The Remove remedy is what `issue --deliver` applies; without it one
        # foreign link blocked `issue` and `issue --deliver` alike, forever.
        return remedy("fetch-url", url=url), remedy("remove-link", url=url)
    if family in {"binding/claim-paragraph", "binding/paragraph"}:
        candidate = re.search(r"candidates: (\d+)", item.message)
        paragraph = int(candidate.group(1)) if candidate else 1
        return (
            remedy("claim-bind", claim_id=claim_id or "C1", paragraph=paragraph),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
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
        return _quote_or_find(item, source_id, claim_id)
    if family == "ledger/extract-length":
        return (
            remedy("extend-quote", file="claims/*.json"),
            remedy("claim-drop", claim_id=claim_id) if claim_id else "",
        )
    if family in ONLINE_CLASS_A_FAMILIES or family.startswith("tooling/"):
        return remedy("issue-deliver"), _drop_or_refresh(item)
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
        return (remedy("fetch-url", url=https) if https else ""), ""
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
        return remedy("review-iter", kind="content"), remedy(
            "review-restore", kind="content"
        )
    if family.startswith("review/rewild"):
        return remedy("review-iter", kind="rewild"), remedy(
            "review-start", kind="rewild"
        )
    if family in {"rewild/ai-vocabulary", "rewild/style", "rewild/length"}:
        return remedy("edit-prose"), ""
    if family.startswith("rewild/"):
        return remedy("issue-deliver"), ""
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
    {"ledger/https", "ledger/host-conflict", "fidelity/context-changed"}
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
        return set_field(match.group(1), _named_file(item))
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
    """Print the producer's remedies when it has them, `alx`'s own when not."""
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
        fix = _with_claim_file(_completed_remedy(item.fix, item), item, claim_files)
        fix = fix if valid_remedy(fix) else ""
        remove = _completed_remedy(getattr(item, "remove", ""), item)
        remove = remove if valid_remedy(remove) else ""
        if klass == "A":
            # Addendum: nothing to drop; `alx issue --deliver` waives it.
            remove = ""
        # Ruling R10: a dishonest `Fix:` sends the whole line back to `_remedies`
        # rather than leaving the finding with a `Remove:` and no repair.
        rejected = bool(fix) and not honest_fix(item.family, fix)
        fix = "" if rejected else fix
        if rejected or (not fix and not remove) or item.family in REMEDY_OVERRIDES:
            fix, remove = _remedies(
                item, paragraphs=paragraphs, claim_files=claim_files
            )
            # R20: `alx`'s own remedy names the real claim input too; only the
            # producer's remedy passed through _with_claim_file before.
            fix = _with_claim_file(fix, item, claim_files)
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
    remaining = int((deadline - now).total_seconds() // 60)
    return elapsed, remaining


#: Field test 4: at this many elapsed minutes with nothing accepted the run is
#: past rescue by more research; the footer says so once per command.
BEHIND_SCHEDULE_MINUTES = 12
_BEHIND_SCHEDULE_PRINTED = False


def _behind_schedule_line(state, elapsed):
    """The escalation line, or None while the run is still on schedule."""
    global _BEHIND_SCHEDULE_PRINTED
    if _BEHIND_SCHEDULE_PRINTED or elapsed <= BEHIND_SCHEDULE_MINUTES:
        return None
    if state.get("counters", {}).get("claims"):
        return None
    _BEHIND_SCHEDULE_PRINTED = True
    return (
        f"BEHIND SCHEDULE: no claim accepted after {elapsed} min — add the "
        "claims that validate now (alx claim add --dry-run shows which), drop "
        "the rest, and start drafting report.md; remaining ≤ 15 min "
        "→ alx issue --deliver"
    )


def _emit(ws, state, command, summary, lines, *, worklog=True):
    """Print the command output, append the worklog line, print the footer."""
    for line in lines:
        print(line)
    elapsed, remaining = _minutes(state)
    stamp = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    if worklog:
        with ws.worklog.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {command} {summary}\n")
    escalation = _behind_schedule_line(state, elapsed)
    if escalation:
        print(escalation)
    if remaining <= DEGRADE_MINUTES:
        print(DEGRADE_INSTRUCTION)
    print(f"elapsed {max(elapsed, 0)} min, remaining {max(remaining, 0)} min")


#: D7: a stalled rewild checker costs its 120 s once per command, not once per
#: invocation. `issue --deliver` runs the checker up to four times (check,
#: post-remedy check, gate, refused-gate findings); after the first timeout the
#: rest of the command skips the subprocess and reuses that one Class A note.
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
    global _CHECKER_TIMED_OUT, _BEHIND_SCHEDULE_PRINTED
    _CHECKER_TIMED_OUT = False
    _BEHIND_SCHEDULE_PRINTED = False
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


def _deadline_epoch(state):
    """T1 compares `deadline` against `time.time()`, so hand it a POSIX stamp."""
    return datetime.fromisoformat(state["deadline"]).timestamp()


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
                "living_status": args.subject_status,
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
        print(
            f"{ws.ledger_path} exists; `alx init` refuses to overwrite it. "
            "Use --force to reset the workspace.",
            file=sys.stderr,
        )
        return 1
    if args.archetype == "person" and not args.subject_status:
        print(
            "--subject-status {living,recently_deceased,deceased,unknown} is "
            "required for the person archetype.",
            file=sys.stderr,
        )
        return 1
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
            "`alx init … --archetype <name>"
            + (
                " --subject-status <living|deceased|…>`"
                if args.archetype == "person"
                else "`"
            ),
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
        deadline=_deadline_epoch(state),
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
        deadline=_deadline_epoch(state),
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
    ok = True
    if args.id:
        if not args.refresh:
            print("`alx fetch --id S<n>` requires --refresh.", file=sys.stderr)
            return 1
        ok = _refresh_one(ws, state, ledger, args, args.id, lines)
    else:
        if not args.urls:
            print("`alx fetch` needs one or more URLs.", file=sys.stderr)
            return 1
        for url in args.urls:
            _elapsed, remaining = _minutes(state)
            if remaining < FETCH_STOP_MINUTES:
                lines.append(
                    f"remaining {remaining} min: fetch batch stopped; draft with "
                    "the sources already in the ledger."
                )
                break
            ok = _fetch_one(ws, state, ledger, args, url, lines) and ok
    ws.save_ledger(ledger)
    state["counters"]["fetch"] = state["counters"].get("fetch", 0) + 1
    ws.save_state(state)
    _emit(ws, state, "fetch", f"{len(ledger['sources'])} sources", lines)
    return 0 if ok else 1


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


@functools.lru_cache(maxsize=1)
def _script_character_maps():
    """Single-character Simplified→Traditional and Traditional→Simplified maps."""
    s2t = {}
    t2s = {}
    for line in validate_report.S2T_CHARACTER_MAP.read_text(
        encoding="utf-8"
    ).splitlines():
        if not line or line.startswith("#"):
            continue
        source, targets = line.split("\t", 1)
        targets = targets.split()
        if not targets:
            continue
        s2t[source] = targets[0]
        for target in targets:
            t2s.setdefault(target, source)
    return s2t, t2s


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


def cmd_show(args):
    ws, state, _ledger = _open(args)
    entry = cached(ws, args.source_id)
    if entry is None:
        print(f"{args.source_id} has no cache; run `alx fetch`.", file=sys.stderr)
        return 1
    text = entry[0]
    end = args.end if args.end is not None else min(len(text), args.start + 1000)
    lines = [
        f"{args.source_id} chars {args.start}-{min(end, len(text))} of {len(text)}",
        text[args.start : end],
    ]
    _emit(ws, state, "show", f"{args.source_id} window", lines)
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


def cmd_claim_add(args):
    ws, state, ledger = _open(args)
    items = []
    sources = {}
    for path in expand_file_globs([str(_input_path(args, item)) for item in args.files]):
        payload = _read_json(path)
        batch = payload if isinstance(payload, list) else [payload]
        for item in batch:
            if isinstance(item, dict) and item.get("claim_id"):
                sources[item["claim_id"]] = path
        items.extend(batch)
    dry_run = getattr(args, "dry_run", False)
    lines = []
    accepted = 0
    failures = []
    seen = set()
    for item in items:
        claim_id = item.get("claim_id") or "<no claim_id>"
        findings = adopt(
            _batch_findings(ws, ledger, item, seen)
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
        for item_finding in hard:
            lines.append(
                f"{claim_id} {'WARN' if item_finding.severity == 'warn' else 'FAIL'}"
                f" [{item_finding.family}] {item_finding.message}"
                f" — fix: {item_finding.fix}"
            )
        if hard:
            lines.extend(_warn_lines(claim_id, warns))
            failures.append(f"{claim_id}({len(hard)})")
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
        if not dry_run:
            record_probe_contexts(ws, claim)
        # K5: the remedy for this claim has to name the file it came from.
        if claim["claim_id"] in sources:
            state.setdefault("claim_files", {})[claim["claim_id"]] = sources[
                claim["claim_id"]
            ]
        seen.add(claim["claim_id"])
        accepted += 1
        verb = "replaced" if replaced else "added"
        if dry_run:
            verb = f"would be {verb}"
        lines.append(
            f"{claim['claim_id']} {verb} ({len(claim['source_ids'])} sources)"
        )
        lines.extend(_warn_lines(claim_id, warns))
    if not dry_run:
        ws.save_ledger(ledger)
        state["counters"]["claims"] = len(ledger["claims"])
        ws.save_state(state)
    tail = f"{len(failures)} failed"
    if failures:
        tail += ": " + " ".join(failures)
    if dry_run:
        # Field test 4: a rehearsal must not read as a committed run.
        lines.insert(
            0,
            f"DRY RUN, nothing written: {len(items)} submitted, "
            f"{accepted} would be accepted, {tail}",
        )
        lines.append(f"next: alx claim add {args.files[0]}")
    else:
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
        worklog=not dry_run,
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
            "HARD until re-pointed — claims that support a dropped claim: "
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
        item["claim_ids"] = [
            value for value in item.get("claim_ids", []) if value not in dropped
        ]
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
                "HARD until re-pointed — claims that support a dropped claim: "
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
        args.reason or "Class-F finding; scope dropped.",
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
    forbidden = [key for key in ("claims", "sources") if key in patch]
    if forbidden:
        print(
            "sources only via fetch/source set; claims only via claim add "
            f"(patch carried: {', '.join(forbidden)}).",
            file=sys.stderr,
        )
        return 1
    # Spec §6.5: only these keys merge; anything else is ignored with a WARN.
    merged = [key for key in patch if key in MERGEABLE_LEDGER_KEYS]
    ignored = [key for key in patch if key not in MERGEABLE_LEDGER_KEYS]
    for key in merged:
        value = patch[key]
        if isinstance(value, dict):
            _deep_merge(ledger.setdefault(key, {}), value)
        else:
            ledger[key] = value
    ws.save_ledger(ledger)
    findings = adopt(_ledger_findings(ws, ledger))
    lines = [render_grouped(findings)] if findings else ["Ledger merged; no findings."]
    if ignored:
        lines.insert(
            0,
            f"WARN: ignored key(s) not merged by `ledger merge`: {', '.join(ignored)} "
            f"(mergeable: {', '.join(sorted(MERGEABLE_LEDGER_KEYS))}).",
        )
    # Field test 4: a patch citing claims that were never added has to say so
    # in its first line; the per-reference WARNs scroll away.
    known = {claim.get("claim_id") for claim in ledger.get("claims", [])}
    referenced = [
        claim_id
        for item in ledger.get("coverage", [])
        if isinstance(item, dict)
        for claim_id in item.get("claim_ids", []) or []
    ] + list(ledger.get("synthesis", {}).get("central_judgment_claim_ids", []) or [])
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
    return 1 if hard_findings(findings) else 0


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


def cmd_snapshot(args):
    ws, state, ledger = _open(args)
    if args.restore:
        latest = ws.latest_snapshot()
        if latest is None:
            print("No snapshot to restore; run `alx snapshot` first.", file=sys.stderr)
            return 1
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
        if normalize_url(source.get("url", "")) not in cache_urls(meta):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache url {meta.get('url')} != ledger url "
                    f"{source.get('url')}.",
                    ids=[source_id],
                )
            )
        elif not cache_matches(text, meta):
            findings.append(
                finding(
                    "fidelity/cache-detached",
                    f"{source_id} cache text sha256 does not match its meta record.",
                    ids=[source_id],
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
            mapping[claim_id] = explicit
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


def _excerpts_located(claim, prose):
    """True when every recorded excerpt is still in the bound paragraph."""
    excerpts = claim.get("report_excerpts") or []
    return bool(excerpts) and all(
        re.sub(r"\s+", " ", str(excerpt)).strip() in prose for excerpt in excerpts
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
        if _excerpts_located(claim, re.sub(r"\s+", " ", masked_prose(block))):
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


def _binding_findings(ws, state, ledger, *, fix=False):
    """Section (c): T4's binding rules, excerpt binding and leftover prose."""
    text = ws.report_text()
    mapping, unbound = paragraph_mapping(ws, state, ledger, text)
    paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
    if fix:
        text = _bind_markers(ws, state, ledger, text)
        paragraphs = {number: block for number, _s, _e, block in body_paragraphs(text)}
        for claim in ledger.get("claims", []):
            number = mapping.get(claim.get("claim_id"))
            block = paragraphs.get(number)
            if not block:
                continue
            prose = re.sub(r"\s+", " ", masked_prose(block))
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


def _fidelity_findings(ws, ledger):
    """Section (d): T1's offline full-coverage probe over the cache."""
    result = source_fidelity.check_source_fidelity(
        ledger,
        sample_size=0,
        online=False,
        cache_dir=ws.sources,
    )
    return as_findings(result.get("findings"))


def _rewild_findings(ws, state):
    """Section (e): the offline rewild tiers.

    `review_note_path` stays `None`: the note's hashes are stamped by `issue`
    (step 4), so before then they never match the working report. The note's
    freshness is judged by alx's own mechanical-delta rule in section (f).
    """
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
    findings = list(
        run_check(
            ws.report,
            snapshot,
            lang=state.get("lang", "en"),
            review_note_path=None,
            timeout=_checker_timeout(),
        )
    )
    _note_checker_timeout(item.message for item in findings)
    return findings


#: J3: each note's schema, whose string minimums are the CJK floor; the full
#: non-CJK floor is enforced here and by `content_gate` (spec §7.1 halving).
REVIEW_SCHEMAS = {
    "rewild": ROOT / "references" / "rewild-review.schema.json",
    "content": ROOT / "references" / "content-review.schema.json",
}


def _prose_floor_missing(note, kind):
    return [
        f"{error} ({kind}-review schema)"
        for error in validate_ledger.prose_floor_errors(
            note, _read_json(REVIEW_SCHEMAS[kind])
        )
    ]


def _plain_excerpt(text):
    """Inline markup and line wrapping removed, so a verbatim quote matches."""
    return re.sub(r"\s+", " ", re.sub(r"[*_`\[\]]", "", str(text))).strip()


def _note_completeness(ws, state, ledger, kind):
    """Offline completeness of one review note (spec §6.7f)."""
    path = ws.reviews / f"{kind}.json"
    if not path.exists():
        return [f"reviews/{kind}.json is missing"]
    note = _read_json(path)
    missing = []
    # Item 4: every entry is the exact JSON path of the field to fill.
    if kind == "rewild":
        checks = note.get("fidelity_checks") or {}
        missing.extend(
            f"fidelity_checks.{name} (must be true)"
            for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
            if checks.get(name) is not True
        )
        for index, item in enumerate(note.get("findings") or [], start=1):
            if item.get("disposition") not in {"resolved", "rejected"}:
                missing.append(
                    f"findings[{index}].disposition (resolved | rejected)"
                )
            elif item.get("category") in {"region", "fidelity"} and (
                item.get("disposition") != "resolved"
            ):
                missing.append(
                    f"findings[{index}].disposition (must be resolved for "
                    f"category {item.get('category')})"
                )
        missing.extend(_prose_floor_missing(note, kind))
        return missing
    scores = note.get("scores") or {}
    for name in CONTENT_SCORE_KEYS:
        entry = scores.get(name) or {}
        if not isinstance(entry.get("score"), int):
            missing.append(f"scores.{name}.score (integer 1-5)")
        elif entry["score"] < 4:
            missing.append(f"scores.{name}.score (is {entry['score']}, below 4)")
        if not str(entry.get("rationale") or "").strip():
            missing.append(f"scores.{name}.rationale (20+ chars, CJK 10+)")
    checks = note.get("checks") or {}
    missing.extend(
        f"checks.{name} (must be true)"
        for name in CONTENT_CHECK_KEYS
        if checks.get(name) is not True
    )
    if not note.get("section_reviews"):
        missing.append("section_reviews (at least one section)")
    if not note.get("completion_note"):
        missing.append("completion_note")
    for index, item in enumerate(note.get("findings") or [], start=1):
        if item.get("severity") == "critical" and item.get("disposition") != "fixed":
            missing.append(
                f"findings[{index}].disposition (a critical finding must be fixed)"
            )
        excerpt = item.get("report_disclosure_excerpt")
        # The report emphasizes and wraps its prose, so the excerpt is compared
        # without inline markup and with folded whitespace.
        if excerpt and _plain_excerpt(excerpt) not in _plain_excerpt(ws.report_text()):
            missing.append(
                f"findings[{index}].report_disclosure_excerpt (not in report.md)"
            )
    # A retained claim with no entry is supported by default; only a claim the
    # reviewer qualified or removed owes an entry, so the missing-key list is
    # the fixed form and never one line per claim.
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
    # The note must also satisfy the schema `content_gate` enforces, or
    # `finish` would exit 0 on a note the gate then rejects. Both lists are
    # returned together, so `finish` names every missing field in one round.
    missing.extend(
        f"{error} (content-review schema)"
        for error in validate_ledger.validate_schema(
            note, _read_json(content_gate.CONTENT_REVIEW_SCHEMA)
        )
    )
    missing.extend(_prose_floor_missing(note, kind))
    return missing


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
    stripped["coverage"] = [
        dict(item, claim_ids=_without_ids(item.get("claim_ids"), dropped))
        for item in ledger.get("coverage", [])
    ]
    stripped["synthesis"] = strip_synthesis(ledger.get("synthesis", {}), dropped)
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True)


def _review_family(kind, suffix):
    """One name set: `rewild_gate` owns `review/rewild`; `alx` owns content."""
    return "review/rewild" if kind == "rewild" else f"review/{kind}-{suffix}"


def freshness_findings(ws, state, ledger, kind):
    """Spec §6.8: current inputs must equal the reviewed copy up to mechanics."""
    record = state.get("reviews", {}).get(kind, {})
    if not record.get("finished"):
        # R29: reviews are optional, so their absence is silent. A note that
        # exists but no longer matches the report is still reported below.
        return []
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
    findings = []
    if changed or removed:
        findings.append(
            finding(
                _review_family(kind, "stale"),
                f"re-review required: {len(changed)} paragraph(s) added or changed and "
                f"{len(removed)} removed since the {kind} review.",
            )
        )
    if kind == "content":
        reviewed_ledger = _read_json(reviewed / "ledger.json")
        if _mechanical_ledger(reviewed_ledger, state) != _mechanical_ledger(
            ledger, state
        ):
            findings.append(
                finding(
                    _review_family(kind, "stale"),
                    "re-review required: the ledger changed beyond accessed/"
                    "verified_at/report_excerpts since the content review.",
                )
            )
    return findings


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


def _review_findings(ws, state, ledger):
    """Section (f): both notes' gate checks plus §6.8 freshness."""
    findings = []
    if (ws.reviews / "content.json").exists():
        findings.extend(
            _content_binding_remedies(
                _content_check(ws), ws, state, ledger
            )
        )
    for kind in REVIEW_KINDS:
        note_missing = _note_completeness(ws, state, ledger, kind)
        record = state.get("reviews", {}).get(kind, {})
        if record.get("finished") and note_missing:
            findings.append(
                finding(
                    _review_family(kind, "stale"),
                    f"reviews/{kind}.json is incomplete: "
                    f"{'; '.join(note_missing)}.",
                )
            )
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


def run_check(ws, state, ledger, *, fix=False, mapping_out=None):
    """Sections (a)-(f) of spec §6.7; every evaluator runs offline, every time."""
    if fix:
        mechanical_fixes(ws, state, ledger)
    findings = []
    findings.extend(_integrity_findings(ws, state, ledger))
    findings.extend(_ledger_findings(ws, ledger))
    binding, mapping = _binding_findings(ws, state, ledger, fix=fix)
    if mapping_out is not None:
        mapping_out.update(mapping)
    findings.extend(binding)
    findings.extend(_fidelity_findings(ws, ledger))
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
        "class_f": len(class_f_findings(findings)),
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


def _status_line(state, findings, remaining):
    elapsed, _remaining = _minutes(state)
    next_step = _next_step(hard_findings(findings))
    tail = (
        f" At remaining <= 15 min run `{remedy('issue')}` then "
        f"`{remedy('render')}`."
    )
    return (
        f"=== STATUS: check #{state['counters']['check']}, elapsed {elapsed} min, "
        f"remaining {max(remaining, 0)} min. Next: {next_step}.{tail} ==="
    )


def _length_line(ws, state):
    """Section (a): the same count, unit and band every length rule uses (R12)."""
    lang = state.get("lang", "en")
    count, unit = report_blocks.report_length(ws.report_text(), lang)
    floor, ceiling, _unit = report_contract.report_length_policy(lang)
    return f"length {count} {unit}; floor {floor}, ceiling {ceiling}"


def cmd_check(args):
    ws, state, ledger = _open(args)
    state["counters"]["check"] = state["counters"].get("check", 0) + 1
    mapping = {}
    findings = run_check(ws, state, ledger, fix=args.fix, mapping_out=mapping)
    ledger = ws.load_ledger()
    _elapsed, remaining = _minutes(state)
    rows = sorted(mapping.items(), key=lambda row: _claim_order(row[0]))
    lines = [_length_line(ws, state)]
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
        render_grouped(findings, verbose=args.verbose),
        _status_line(state, findings, remaining),
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
    return 1 if hard_findings(findings) else 0


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
    ("scores.<key>.rationale", "text, 20+ chars (CJK 10+)", "why that score"),
    (
        "checks.<key>",
        "true | false; all must be true",
        "one key each: " + ", ".join(CONTENT_CHECK_KEYS),
    ),
    (
        "section_reviews[]",
        "one object per H2 section, at least one",
        'keys: section_heading, purpose, new_value, evidence_or_reasoning, '
        "limitation_or_tradeoff, contribution_to_governing_question "
        '(10+ CJK / 20+ other chars each), disposition="keep"',
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
        'visible_text_and_claims_review (10+ CJK / 20+ other chars), '
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
            "resolved|rejected (region and fidelity must be resolved), "
            "reason (10+ chars)",
        ),
    )


def _note_instructions(kind):
    """The printed field list `review start` owes the reviewer (item 4)."""
    guide = CONTENT_NOTE_GUIDE if kind == "content" else _rewild_note_guide()
    lines = [f"Fill reviews/{kind}.json — every field below, nothing else:"]
    lines.extend(f"  {path}: {values} — {meaning}" for path, values, meaning in guide)
    lines.append(
        f"Then `alx review finish {kind}`; it names the JSON path of whatever "
        "is still missing."
    )
    return lines


def _note_skeleton(ws, state, kind, ledger):
    lang = state.get("lang", "en")
    if kind == "rewild":
        snapshot = ws.latest_snapshot()
        return {
            "schema_version": 1,
            "status": "draft",
            "report_sha256": file_sha256(ws.report),
            "source_sha256": file_sha256(snapshot) if snapshot else "",
            "report_lang": lang,
            "profile": rewild_gate.PROFILES[lang][0],
            "fidelity_checks": {
                name: False for name in sorted(rewild_gate.REQUIRED_FIDELITY_CHECKS)
            },
            "findings": [],
        }
    return {
        "schema_version": 2,
        "status": "draft",
        "report_path": str(ws.report),
        "report_sha256": file_sha256(ws.report),
        "ledger_path": str(ws.ledger_path),
        "ledger_sha256": file_sha256(ws.ledger_path),
        "report_lang": lang,
        "reviewed_at": date.today().isoformat(),
        "reviewer_mode": "fresh_eyes",
        # The skeleton is the whole form: every score and check key is here, so
        # `review finish` can only ever name keys the reviewer left unfilled.
        "scores": {
            name: {"score": None, "rationale": ""} for name in CONTENT_SCORE_KEYS
        },
        "checks": {name: False for name in CONTENT_CHECK_KEYS},
        "section_reviews": [],
        "visual_assets": [],
        "findings": [],
        "evidence_limitations": [],
        "completion_note": "",
        # Empty by default: a retained claim needs an entry only when the
        # reviewer qualifies or removes it.
        "claim_support": [],
    }


def cmd_review_start(args):
    ws, state, ledger = _open(args)
    kind = args.kind
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
    lines.append(f"Review copy: {target}")
    lines.extend(_note_instructions(kind))
    lines.append(f"Judge the report by {protocol}.")
    _emit(ws, state, f"review start {kind}", f"iteration {iteration}", lines)
    return 0


def cmd_review_finish(args):
    ws, state, ledger = _open(args)
    kind = args.kind
    record = state["reviews"].get(kind, {})
    if not record.get("iteration"):
        print(f"Run `alx review start {kind}` first.", file=sys.stderr)
        return 1
    # `status` and a section's `disposition` are `finish`'s own fields, not the
    # reviewer's: they are written before the note is judged complete.
    path = ws.reviews / f"{kind}.json"
    if path.exists():
        note = _read_json(path)
        note["status"] = "completed"
        for section in note.get("section_reviews") or []:
            if isinstance(section, dict) and not section.get("disposition"):
                section["disposition"] = "keep"
        _write_json(path, note)
    missing = _note_completeness(ws, state, ledger, kind)
    note = _read_json(path)
    if note.get("report_sha256") != record.get("report_sha256"):
        missing.append("report_sha256 no longer matches the reviewed copy")
    if missing:
        print(
            f"reviews/{kind}.json is incomplete: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
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


def cmd_review_restore(args):
    ws, state, _ledger = _open(args)
    kind = args.kind
    record = state["reviews"].get(kind, {})
    if not record.get("finished"):
        print(f"No finished {kind} review to restore.", file=sys.stderr)
        return 1
    reviewed = ws.review_dir(kind, record["iteration"])
    shutil.copyfile(reviewed / "report.md", ws.report)
    if kind == "content":
        shutil.copyfile(reviewed / "ledger.json", ws.ledger_path)
    _emit(
        ws,
        state,
        f"review restore {kind}",
        f"iteration {record['iteration']}",
        [f"report.md restored from the {kind} review copy."],
    )
    return 0


# --------------------------------------------------------------------------
# issue
# --------------------------------------------------------------------------


def _verification_note(lang, notes):
    prefix = VERIFICATION_NOTE_PREFIX[lang]
    joiner = "; " if lang == "en" else "；"
    return f"{prefix} {joiner.join(notes)}"


def _insert_verification_note(ws, lang, notes):
    text = ws.report_text()
    prefixes = tuple(VERIFICATION_NOTE_PREFIX.values())
    cleaned = []
    for _start, _end, block in _blocks(text):
        if block.strip().startswith(prefixes):
            cleaned.append(block)
    for block in cleaned:
        text = text.replace(block + "\n\n", "")
    offset = sources_heading_offset(text)
    note = _verification_note(lang, notes)
    if offset is None:
        text = text.rstrip("\n") + "\n\n" + note + "\n"
    else:
        text = text[:offset] + note + "\n\n" + text[offset:]
    ws.report.write_text(text, encoding="utf-8")
    return note


def _auto_remedies(ws, state, ledger, findings, lines):
    """Spec §6.9.1: `--deliver` drops scope, it never waives Class F."""
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
        }
    ]
    if restore and ws.latest_snapshot() is not None:
        ws.report.write_text(_snapshot_text(ws, state), encoding="utf-8")
        lines.append("auto-remedy: report.md restored from the latest snapshot.")
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
    Class F, and unverified sources are the Class-A availability finding once
    they pass the policy quorum.
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
        elif status in UNVERIFIED_STATUSES and beyond_quorum:
            findings.append(
                finding(
                    f"fidelity/{status}",
                    f"{detail} Unverified sources are past the "
                    f"{int(UNVERIFIED_QUORUM * 100)}% quorum.",
                    ids=ids,
                )
            )
    return findings


def _online_phase(ws, state, ledger, args, lines, delivery_notes, disclosures):
    """Step 2: deadline-bound live fidelity, then re-probe refreshed sources."""
    receipt_path = ws.receipts / "source-fidelity.json"
    _elapsed, remaining = _minutes(state)
    if remaining < RESERVE_MINUTES:
        # K1: the skip writes nothing, so it may not destroy the receipt an
        # earlier pass wrote; that receipt is what the content gate reads.
        kept = "; the receipt from an earlier pass stands" if receipt_path.exists() else ""
        delivery_notes.append(
            f"live source re-check skipped ({max(remaining, 0)} min left; every "
            "extract was already verified offline against the cached pages by "
            f"alx check){kept}"
        )
        return [], True
    # J1: only a receipt this pass wrote may be hashed into `issue.json`, and
    # this pass is now about to write one.
    receipt_path.unlink(missing_ok=True)
    cap = min(ONLINE_CAP_MINUTES, max(remaining - RESERVE_MINUTES, 1))
    timeout = min(FETCH_TIMEOUT_SECONDS, cap * 60)
    try:
        result = source_fidelity.check_source_fidelity(
            ledger,
            sample_size=args.sample_size,
            online=True,
            timeout=timeout,
            cache_dir=ws.sources,
            deadline=_deadline_epoch(state),
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
        disclosures.append(
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
                deadline=_deadline_epoch(state),
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
    if not (ws.receipts / "source-fidelity.json").exists():
        # K4: `--fast` requires that receipt; its absence is already a note.
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
        if freshness_findings(ws, state, ledger, kind):
            # Spec §6.8: `issue` stamps the current hashes only when the
            # freshness rule passes; a stale note must fail its gate instead.
            continue
        note = _read_json(note_path)
        note["report_sha256"] = file_sha256(ws.report)
        if kind == "rewild" and snapshot is not None:
            note["source_sha256"] = file_sha256(snapshot)
        if kind == "content":
            note["ledger_sha256"] = file_sha256(ws.ledger_path)
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
            # K4: no receipt at all is a recorded gap, not a refused gate.
            delivery_notes.append(
                "content receipt issued without a source-fidelity receipt: "
                "live fidelity never ran"
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
    disclosures = []
    if ws.latest_snapshot() is None:
        shutil.copyfile(ws.report, ws.dir / "report.pre-rewild.md")
        state["humanization"] = "none"
        ws.save_state(state)
        disclosures.append("humanization: none (issue created the snapshot)")
    findings = run_check(ws, state, ledger, fix=False)
    state, ledger, findings, dropped_for_delivery = _drop_hard(
        ws, state, ledger, findings, lines
    )
    # J7: `alx status` must report what `issue` just saw, remedies included.
    _record_last_check(state, findings)
    ws.save_state(state)
    online_findings, _ok = _online_phase(
        ws, state, ledger, args, lines, delivery_notes, disclosures
    )
    if online_findings:
        # Spec §6.9.1 + J5: the drops change the report and the ledger, so the
        # whole offline check runs again over what is actually delivered.
        state, ledger = _auto_remedies(ws, state, ledger, online_findings, lines)
        dropped_for_delivery = True
        findings = run_check(ws, state, ledger, fix=False)
        state, ledger, findings, _again = _drop_hard(
            ws, state, ledger, findings, lines
        )
        _record_last_check(state, findings)
        ws.save_state(state)
        # J1: the receipt is owed by the ledger that is actually delivered, so
        # the live pass runs once more over the ledger minus the dropped claims.
        _online_phase(ws, state, ledger, args, lines, delivery_notes, disclosures)
    still_hard = class_f_findings(findings)
    if still_hard:
        # C1: nothing refuses, so what could not be removed is still printed.
        lines.append(render_grouped(still_hard))
    note_items = delivery_notes + disclosures
    if note_items:
        note = _insert_verification_note(ws, state.get("lang", "en"), note_items)
        lines.append(f"verification note: {note[:60]}")
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
    if (ws.receipts / "source-fidelity.json").exists():
        receipt["receipts"]["source-fidelity"] = file_sha256(
            ws.receipts / "source-fidelity.json"
        )
    _write_json(ws.receipts / "issue.json", receipt)
    state["counters"]["issue"] = state["counters"].get("issue", 0) + 1
    ws.save_state(state)
    if args.deliver and not dropped_for_delivery:
        # R28: with no hard finding to remove, `--deliver` is an alias of
        # `issue`; the warnings it used to waive are notes now.
        lines.append("warnings recorded in delivery notes")
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


def cmd_render(args):
    ws, state, ledger = _open(args)
    receipt_path = ws.receipts / "issue.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else {}
    if receipt.get("report_sha256") != file_sha256(ws.report) or receipt.get(
        "ledger_sha256"
    ) != file_sha256(ws.ledger_path):
        # C2: a missing or stale receipt is the issue step `render` runs itself.
        cmd_issue(argparse.Namespace(dir=args.dir, deliver=False, sample_size=8))
        ws, state, ledger = _open(args)
    from scripts import md_to_pdf, render_pdf_pages  # heavy import, render only

    subject = f"{ledger.get('subject', '')} {ledger.get('research_question', '')}"
    templates = (
        [args.template]
        if args.template
        else ["executive", md_to_pdf.select_adaptive_companion(subject)]
    )
    lines = []
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
            ("source_fidelity_receipt", ws.receipts / "source-fidelity.json"),
        ):
            if path.exists():
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
                    [finding("tooling/render", f"{note}.", fix=remedy("issue"))]
                )
            )
            continue
        pages = ws.dir / f"pages-{template}"
        lines.append(f"{template}: {output}")
        # `alx` owns the contact-sheet directory: a second `render` refills it
        # instead of refusing because it is not empty.
        shutil.rmtree(pages, ignore_errors=True)
        try:
            render_pdf_pages.render_pages(str(output), str(pages))
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
        lines.append(f"{template} contact sheet: {pages}")
    _emit(ws, state, "render", f"{len(templates)} PDFs", lines)
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def cmd_status(args):
    managed = "managed" if runtime_packages_present() else "host — relocation failed"
    print(f"runtime: {sys.executable} ({managed})")
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
            f"({last.get('class_f', 0)} Class F)"
            if last
            else "not run"
        ),
        f"Next: {_next_command(ws, state, ledger)}",
    ]
    _emit(ws, state, "status", "phase checklist", lines)
    return 0


def _next_command(ws, state, ledger):
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
    init.add_argument("--archetype", choices=ARCHETYPES, default=None)
    init.add_argument("--subject-status", choices=LIVING_STATUSES)
    init.add_argument("--reader", help="file holding the intended reader")
    init.add_argument("--budget-minutes", type=int, default=60)
    init.add_argument("--force", action="store_true")
    init.set_defaults(
        handler=cmd_init,
        file_args=(("--subject", "subject"), ("--reader", "reader")),
    )

    fetch = subparsers.add_parser("fetch", help="fetch sources into the cache")
    fetch.add_argument("urls", nargs="*")
    fetch.add_argument("--id", dest="id", help="ledger source id to refresh")
    fetch.add_argument("--refresh", action="store_true")
    fetch.add_argument("--provenance")
    fetch.add_argument("--type")
    fetch.add_argument("--role", action="append")
    fetch.add_argument("--accountability", choices=ACCOUNTABILITY_BASES)
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

    show = subparsers.add_parser("show", help="a cache window")
    show.add_argument("source_id")
    show.add_argument("--start", type=int, default=0)
    show.add_argument("--end", type=int)
    show.set_defaults(handler=cmd_show)

    claim = subparsers.add_parser("claim", help="claim lifecycle")
    claim_sub = claim.add_subparsers(dest="claim_command", required=True)
    claim_add = claim_sub.add_parser("add")
    claim_add.add_argument("--dry-run", dest="dry_run", action="store_true")
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
    snapshot.add_argument("--iter", action="store_true")
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
    review_restore = review_sub.add_parser("restore")
    review_restore.add_argument("kind", choices=REVIEW_KINDS)
    review_restore.set_defaults(handler=cmd_review_restore)

    issue = subparsers.add_parser("issue", help="receipts, once, at the end")
    issue.add_argument("--deliver", action="store_true")
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
