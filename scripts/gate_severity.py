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

WARNING_PREFIX = "WARNING: "


def warning(message):
    """Mark one finding as a non-blocking warning."""
    text = str(message)
    return text if is_warning(text) else f"{WARNING_PREFIX}{text}"


def is_warning(finding):
    """Return whether one finding belongs to the non-blocking tier."""
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
        print(transform(f"[FAIL] {error}", sys.stderr), file=sys.stderr)
    for finding in warning_findings(findings):
        print(transform(str(finding), sys.stderr), file=sys.stderr)
    if errors:
        return 1
    print(transform(ok_message, sys.stdout))
    return 0
