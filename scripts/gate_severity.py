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


def render_grouped(findings, *, per_family=5, with_class=False):
    records = [item for item in findings if is_finding(item)]
    hard = [item for item in records if item.severity == "hard"]
    warn = [item for item in records if item.severity == "warn"]
    lines = [f"=== HARD {len(hard)} (blocks issue) ==="]

    def label(members):
        if not with_class or not any(item.klass == "F" for item in members):
            return ""
        return CLASS_LABELS["F"]

    def emit(items):
        for family, members in group(items).items():
            lines.append(f"[{family}] {len(members)}{label(members)}")
            shown = members[:per_family]
            for item in shown:
                prefix = f"{', '.join(item.ids)}: " if item.ids else ""
                tail = item.message.rstrip(".") + "."
                if item.fix:
                    tail += f" Fix: {item.fix}."
                if getattr(item, "remove", ""):
                    tail += f" Remove: `{item.remove}`."
                lines.append(f"  {prefix}{tail}")
            extra = len(members) - per_family
            if extra > 0:
                lines.append(f"  +{extra} more")

    emit(hard)
    lines.append(f"=== WARN {len(warn)} ===")
    emit(warn)
    lines.append(f"=== STATUS: {len(hard)} hard, {len(warn)} warn ===")
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
