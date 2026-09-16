"""Shared hard-error and warning tiers for Alexandria's delivery gates.

Every gate helper keeps returning plain strings, so existing callers are
unchanged. A warning is one of those strings carrying ``WARNING_PREFIX``:

* hard errors are fabrication, unsupported quantities, citations and URLs,
  source fidelity, person safety, and schema validity. They block delivery.
* warnings are style, prose phrasing, and formatting judgments that can be
  overcautious. They are printed, they do not block delivery.

Callers that decide whether delivery may proceed filter with
:func:`hard_errors`; command-line entry points print both tiers through
:func:`emit_findings` and exit on the hard tier alone.
"""

import sys
from collections import OrderedDict
from dataclasses import dataclass

WARNING_PREFIX = "WARNING: "


@dataclass
class Finding:
    family: str
    severity: str
    klass: str
    ids: list
    message: str
    fix: str
    remove: str = ""


def is_finding(item):
    """Duck-type test for a finding record.

    ``gate_severity`` is imported both as a top-level module and as
    ``scripts.gate_severity``, so two distinct ``Finding`` classes exist at
    runtime and ``isinstance`` would silently drop every finding produced by a
    module that imported the other copy.
    """
    return all(
        hasattr(item, name)
        for name in ("family", "severity", "klass", "ids", "message", "fix")
    )


def as_text(f):
    """Legacy string form: ``[FAIL] ...`` or ``WARNING: ...``."""
    if not is_finding(f):
        return str(f)
    if f.severity == "warn":
        return f"{WARNING_PREFIX}{f.message}"
    return f"[FAIL] {f.message}"


def group(findings):
    grouped = OrderedDict()
    for finding in findings:
        if not is_finding(finding):
            continue
        grouped.setdefault(finding.family, []).append(finding)
    return grouped


#: R28: "Class A" is gone — a warning is printed with its fix and blocks
#: nothing, so only the HARD tier carries a label, and only ever `F`.
CLASS_LABELS = {"F": " (F)"}


#: R29: the WARN tier is advice, so it prints one line per distinct
#: message (first occurrence's fix), at most 5 per family; `--verbose`
#: expands the tier.
WARN_MESSAGE_CHARS = 160
WARN_FULL_FAMILIES = frozenset(
    {
        "fidelity/semantic",
        "rewild/region",
        "rewild/ai-vocabulary",
        "rewild/length",
    }
)
SCHEMA_FAMILIES = frozenset({"ledger/schema", "ledger/claim-input"})


def render_grouped(findings, *, per_family=5, with_class=False, verbose=False):
    records = [item for item in findings if is_finding(item)]
    hard = [item for item in records if item.severity == "hard"]
    warn = [item for item in records if item.severity == "warn"]
    lines = [f"=== HARD {len(hard)} (fix, or alx issue drops them) ==="]

    def label(members):
        if not with_class or not any(item.klass == "F" for item in members):
            return ""
        return CLASS_LABELS["F"]

    def emit_compact(items):
        schema = [item for item in items if item.family in SCHEMA_FAMILIES]
        full = [item for item in items if item.family in WARN_FULL_FAMILIES]
        compact = [
            item
            for item in items
            if item.family not in WARN_FULL_FAMILIES
            and item.family not in SCHEMA_FAMILIES
        ]
        if schema:
            emit(schema)
        if full:
            emit(full)
        for family, members in group(compact).items():
            by_text = OrderedDict()
            for item in members:
                key = " ".join(str(item.message).split())
                by_text.setdefault(key, []).append(item)
            shown = list(by_text.items())[:per_family]
            extra = len(members) - sum(len(copies) for _text, copies in shown)
            for _text, copies in shown:
                first = copies[0]
                # One line per distinct text; a multi-line message still folds.
                message = " ".join(str(first.message).split())
                if len(message) > WARN_MESSAGE_CHARS:
                    message = message[:WARN_MESSAGE_CHARS].rstrip() + "…"
                line = f"[{family}] {len(copies)} — {message}"
                if first.fix:
                    line += f" — Fix: {first.fix}"
                lines.append(line)
            if extra > 0:
                lines.append(f"[{family}] +{extra} more (--verbose)")

    def emit(items):
        for family, members in group(items).items():
            lines.append(f"[{family}] {len(members)}{label(members)}")
            # Item 7: every schema line is distinct and names its own field, so
            # `ledger/schema` is never capped; the other families still are.
            cap = (
                len(members)
                if family in SCHEMA_FAMILIES or family in WARN_FULL_FAMILIES
                else per_family
            )
            shown = members[:cap]
            for item in shown:
                prefix = f"{', '.join(item.ids)}: " if item.ids else ""
                tail = item.message.rstrip(".") + "."
                if item.fix:
                    tail += f" Fix: {item.fix}."
                if getattr(item, "remove", ""):
                    tail += f" Remove: `{item.remove}`."
                lines.append(f"  {prefix}{tail}")
            extra = len(members) - cap
            if extra > 0:
                lines.append(f"  +{extra} more")

    emit(hard)
    lines.append(f"=== WARN {len(warn)} ===")
    if verbose:
        emit(warn)
    else:
        emit_compact(warn)
    return "\n".join(lines)


def warning(message):
    """Mark one finding as a non-blocking warning."""
    text = str(message)
    return text if is_warning(text) else f"{WARNING_PREFIX}{text}"


def is_warning(finding):
    """Return whether one finding belongs to the non-blocking tier."""
    if is_finding(finding):
        return finding.severity == "warn"
    return str(finding).startswith(WARNING_PREFIX)


def hard_errors(findings):
    """Return only the findings that must block delivery."""
    return [finding for finding in findings if not is_warning(finding)]


def warning_findings(findings):
    """Return only the non-blocking findings, marker included."""
    return [finding for finding in findings if is_warning(finding)]


def emit_findings(findings, *, ok_message, transform=None):
    """Print both tiers and return the process exit code."""
    transform = transform or (lambda text, stream: text)
    errors = hard_errors(findings)
    for error in errors:
        text = as_text(error) if is_finding(error) else f"[FAIL] {error}"
        print(transform(text, sys.stderr), file=sys.stderr)
    for finding in warning_findings(findings):
        print(transform(as_text(finding), sys.stderr), file=sys.stderr)
    if errors:
        return 1
    print(transform(ok_message, sys.stdout))
    return 0
