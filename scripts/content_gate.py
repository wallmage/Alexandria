#!/usr/bin/env python3
"""Validate Alexandria's final content review and issue a bound receipt."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    from .validate_ledger import validate_references, validate_schema
    from .validate_report import validate_report_against_ledger
except ImportError:
    from validate_ledger import validate_references, validate_schema
    from validate_report import validate_report_against_ledger


ROOT = Path(__file__).resolve().parents[1]
CONTENT_REVIEW_SCHEMA = ROOT / "references" / "content-review.schema.json"
EVIDENCE_LEDGER_SCHEMA = ROOT / "references" / "evidence-ledger.schema.json"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), []
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{label} could not be read: {exc}"]


def _schema_errors(data, schema_path, label):
    schema, errors = _read_json(schema_path, f"{label} schema")
    if errors:
        return errors
    return [
        f"{label} {error}"
        for error in validate_schema(data, schema)
    ]


def _normalized(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def _write_receipt(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(handle.name).replace(path)
    except Exception:
        Path(handle.name).unlink(missing_ok=True)
        raise


def run_content_gate(report_path, ledger_path, review_note_path, receipt_path):
    """Return errors; on success write a receipt bound to every input."""
    report_path = Path(report_path).resolve()
    ledger_path = Path(ledger_path).resolve()
    review_note_path = Path(review_note_path).resolve()
    receipt_path = Path(receipt_path).resolve()

    errors = []
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Final report could not be read: {exc}"]
    ledger, ledger_errors = _read_json(ledger_path, "Evidence ledger")
    review, review_errors = _read_json(review_note_path, "Content review")
    errors.extend(ledger_errors)
    errors.extend(review_errors)
    if ledger is None or review is None:
        return errors

    errors.extend(
        _schema_errors(ledger, EVIDENCE_LEDGER_SCHEMA, "Evidence ledger:")
    )
    errors.extend(validate_references(ledger))
    errors.extend(
        _schema_errors(review, CONTENT_REVIEW_SCHEMA, "Content review:")
    )
    errors.extend(validate_report_against_ledger(report_text, ledger))
    ledger_language = (
        ledger.get("brief", {}).get("report_language")
        if isinstance(ledger.get("brief"), dict)
        else None
    )
    if review.get("report_lang") != ledger_language:
        errors.append(
            "Content review language does not match the evidence ledger."
        )

    report_hash = file_sha256(report_path)
    ledger_hash = file_sha256(ledger_path)
    if review.get("report_path") != str(report_path):
        errors.append("Content review belongs to a different final report.")
    if review.get("report_sha256") != report_hash:
        errors.append("Content review does not match the final report.")
    if review.get("ledger_path") != str(ledger_path):
        errors.append("Content review belongs to a different evidence ledger.")
    if review.get("ledger_sha256") != ledger_hash:
        errors.append("Content review does not match the evidence ledger.")

    report_normalized = _normalized(report_text)
    findings = review.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("finding_id", "<unknown>")
            severity = finding.get("severity")
            disposition = finding.get("disposition")
            if severity == "critical" and disposition != "fixed":
                errors.append(f"Critical finding {finding_id} must be fixed.")
            if severity == "major" and disposition == "rejected":
                errors.append(
                    f"Major finding {finding_id} cannot be rejected at final review."
                )
            if severity == "major" and disposition == "accepted_limitation":
                disclosure = _normalized(
                    finding.get("report_disclosure_excerpt") or ""
                )
                if len(disclosure) < 40 or disclosure not in report_normalized:
                    errors.append(
                        f"{finding_id} disclosure cannot be located in the final report."
                    )

    if errors:
        return errors

    scores = review["scores"]
    receipt = {
        "schema_version": 1,
        "status": "passed",
        "report_lang": review["report_lang"],
        "report_path": str(report_path),
        "report_sha256": report_hash,
        "ledger_path": str(ledger_path),
        "ledger_sha256": ledger_hash,
        "review_note_path": str(review_note_path),
        "review_note_sha256": file_sha256(review_note_path),
        "content_review_schema_path": str(CONTENT_REVIEW_SCHEMA.resolve()),
        "content_review_schema_sha256": file_sha256(CONTENT_REVIEW_SCHEMA),
        "evidence_ledger_schema_path": str(EVIDENCE_LEDGER_SCHEMA.resolve()),
        "evidence_ledger_schema_sha256": file_sha256(EVIDENCE_LEDGER_SCHEMA),
        "minimum_score": min(item["score"] for item in scores.values()),
    }
    _write_receipt(receipt_path, receipt)
    return []


def validate_content_receipt(
    report_path,
    ledger_path,
    receipt,
    *,
    expected_lang=None,
):
    """Verify and deterministically replay a content-gate receipt."""
    report_path = Path(report_path).resolve()
    ledger_path = Path(ledger_path).resolve()
    if not isinstance(receipt, dict):
        return ["Content receipt root must be an object."]

    errors = []
    if receipt.get("schema_version") != 1:
        errors.append("Content receipt has an unsupported schema version.")
    if receipt.get("status") != "passed":
        errors.append("Content receipt does not record a passing gate.")
    if expected_lang and receipt.get("report_lang") != expected_lang:
        errors.append("Content receipt language does not match the expected report language.")
    if receipt.get("report_path") != str(report_path):
        errors.append("Content receipt belongs to a different report.")
    if receipt.get("ledger_path") != str(ledger_path):
        errors.append("Content receipt belongs to a different ledger.")

    for path, key, label in (
        (report_path, "report_sha256", "current report"),
        (ledger_path, "ledger_sha256", "current ledger"),
    ):
        try:
            digest = file_sha256(path)
        except OSError as exc:
            errors.append(f"Content receipt {label} could not be verified: {exc}")
            continue
        if receipt.get(key) != digest:
            errors.append(f"Content receipt does not match the {label}.")

    for path_key, hash_key, expected_path, label in (
        (
            "content_review_schema_path",
            "content_review_schema_sha256",
            CONTENT_REVIEW_SCHEMA.resolve(),
            "content-review schema",
        ),
        (
            "evidence_ledger_schema_path",
            "evidence_ledger_schema_sha256",
            EVIDENCE_LEDGER_SCHEMA.resolve(),
            "evidence-ledger schema",
        ),
    ):
        recorded_path = Path(receipt.get(path_key, "")).resolve()
        if recorded_path != expected_path:
            errors.append(f"Content receipt does not use Alexandria's canonical {label}.")
        elif receipt.get(hash_key) != file_sha256(expected_path):
            errors.append(f"Alexandria's bundled {label} has changed.")

    review_value = receipt.get("review_note_path")
    if not review_value:
        errors.append("Content receipt is missing the review-note path.")
        review_path = None
    else:
        review_path = Path(review_value).resolve()
        try:
            review_hash = file_sha256(review_path)
        except OSError as exc:
            errors.append(f"Content review note could not be verified: {exc}")
        else:
            if receipt.get("review_note_sha256") != review_hash:
                errors.append("Content review note has changed since the gate.")

    if not errors and review_path is not None:
        with tempfile.TemporaryDirectory() as directory:
            regenerated = Path(directory) / "receipt.json"
            rerun_errors = run_content_gate(
                report_path,
                ledger_path,
                review_path,
                regenerated,
            )
            errors.extend(
                f"Content gate recheck failed: {error}"
                for error in rerun_errors
            )
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Alexandria's final content-quality gate"
    )
    parser.add_argument("report", help="final report Markdown")
    parser.add_argument("--ledger", required=True, help="evidence ledger JSON")
    parser.add_argument(
        "--review-note",
        required=True,
        help="completed content review JSON",
    )
    parser.add_argument(
        "--receipt",
        required=True,
        help="content-gate receipt JSON to write",
    )
    args = parser.parse_args(argv)

    errors = run_content_gate(
        args.report,
        args.ledger,
        args.review_note,
        args.receipt,
    )
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[OK] Content quality gate passed: {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
