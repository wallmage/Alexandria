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


def as_text(f):
    """Legacy string form: ``[FAIL] ...`` or ``WARNING: ...``."""
    if not isinstance(f, Finding):
        return str(f)
    if f.severity == "warn":
        return f"{WARNING_PREFIX}{f.message}"
    return f"[FAIL] {f.message}"


def group(findings):
    grouped = OrderedDict()
    for finding in findings:
        if not isinstance(finding, Finding):
            continue
        grouped.setdefault(finding.family, []).append(finding)
    return grouped


def render_grouped(findings, *, per_family=5):
    records = [item for item in findings if isinstance(item, Finding)]
    hard = [item for item in records if item.severity == "hard"]
    warn = [item for item in records if item.severity == "warn"]
    lines = [f"=== HARD {len(hard)} (blocks issue) ==="]

    def emit(items):
        for family, members in group(items).items():
            lines.append(f"[{family}] {len(members)}")
            shown = members[:per_family]
            for item in shown:
                prefix = f"{', '.join(item.ids)}: " if item.ids else ""
                tail = item.message.rstrip(".")
                if item.fix:
                    tail += f". Fix: {item.fix}."
                if item.remove:
                    tail += f" Remove: `{item.remove}`."
                if not tail.endswith("."):
                    tail += "."
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
    if isinstance(finding, Finding):
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
        text = as_text(error) if isinstance(error, Finding) else f"[FAIL] {error}"
        print(transform(text, sys.stderr), file=sys.stderr)
    for finding in warning_findings(findings):
        text = as_text(finding) if isinstance(finding, Finding) else str(finding)
        print(transform(text, sys.stderr), file=sys.stderr)
    if errors:
        return 1
    print(transform(ok_message, sys.stdout))
    return 0
