#!/usr/bin/env python3
"""Validate Alexandria's final content review and issue a bound receipt."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from .artifact_safety import artifact_collision_errors
    from .html_policy import (
        SAFE_ATTRIBUTES,
        SAFE_TAGS,
        safe_image_destination,
        safe_link_destination,
    )
    from .report_blocks import validation_report_blocks
    from .validate_ledger import validate_references, validate_schema
    from .validate_report import (
        SOURCE_HEADINGS,
        _h2_sections,
        validate_report_against_ledger,
    )
except ImportError:
    from artifact_safety import artifact_collision_errors
    from html_policy import (
        SAFE_ATTRIBUTES,
        SAFE_TAGS,
        safe_image_destination,
        safe_link_destination,
    )
    from report_blocks import validation_report_blocks
    from validate_ledger import validate_references, validate_schema
    from validate_report import (
        SOURCE_HEADINGS,
        _h2_sections,
        validate_report_against_ledger,
    )

try:
    from .source_fidelity import validate_source_fidelity_receipt
except ImportError:
    from source_fidelity import validate_source_fidelity_receipt


ROOT = Path(__file__).resolve().parents[1]
CONTENT_REVIEW_SCHEMA = ROOT / "references" / "content-review.schema.json"
EVIDENCE_LEDGER_SCHEMA = ROOT / "references" / "evidence-ledger.schema.json"
_TABLE_ALIGNMENT_STYLE_RE = re.compile(
    r"text-align:\s*(?:left|right|center)\s*;?",
    re.IGNORECASE,
)


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


def _normalized_heading(text):
    return _normalized(text).casefold()


def _same_bound_name(recorded, actual):
    """Allow a hash-bound artifact directory to move without weakening identity."""
    return bool(recorded) and Path(str(recorded)).name == Path(actual).name


def _section_review_errors(report_text, review):
    report_headings = [
        heading
        for heading, _ in _h2_sections(report_text)
        if heading.casefold() not in SOURCE_HEADINGS
    ]
    reviews = review.get("section_reviews", [])
    if not isinstance(reviews, list):
        return []
    reviewed_headings = [
        item.get("section_heading", "")
        for item in reviews
        if isinstance(item, dict)
    ]
    report_map = {
        _normalized_heading(heading): heading for heading in report_headings
    }
    review_map = {}
    errors = []
    for heading in reviewed_headings:
        normalized = _normalized_heading(heading)
        if normalized in review_map:
            errors.append(f"Duplicate section review: {heading}.")
        review_map[normalized] = heading
    for normalized, heading in report_map.items():
        if normalized not in review_map:
            errors.append(f"Section review is missing for {heading}.")
    for normalized, heading in review_map.items():
        if normalized not in report_map:
            errors.append(
                f"Section review {heading} is not in the final report."
            )
    return errors


class _RenderedImageParser(HTMLParser):
    """Collect renderer inputs and reject anything outside its safe policy."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.links = []
        self.policy_violations = []
        self.user_facing_attributes = []

    def _record_element(self, tag, attrs):
        if tag not in SAFE_TAGS:
            self.policy_violations.append(f"tag <{tag}>")
        values = {}
        for name, value in attrs:
            name = name.casefold()
            if (
                tag in {"th", "td"}
                and name == "style"
                and value is not None
                and _TABLE_ALIGNMENT_STYLE_RE.fullmatch(value.strip())
            ):
                continue
            if name not in SAFE_ATTRIBUTES.get(tag, frozenset()):
                self.policy_violations.append(f"attribute {name} on <{tag}>")
                continue
            if tag == "img" and name in {"src", "alt", "title"} and value is not None:
                values[name] = value
            if (
                value is not None
                and (
                    (tag == "img" and name in {"alt", "title"})
                    or (tag == "a" and name == "title")
                )
            ):
                self.user_facing_attributes.append(
                    {"tag": tag, "attribute": name, "value": value}
                )
            if tag == "a" and name == "href" and value is not None:
                self.links.append(value)
        if tag == "img":
            self.images.append(values)

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        self._record_element(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._record_element(tag.casefold(), attrs)


def _rendered_markdown_model(report_text):
    """Parse renderer-preserved images and user-facing attributes."""
    try:
        import markdown
    except ModuleNotFoundError:
        return None, [
            "Image validation needs Markdown. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ]
    renderer = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
        output_format="html5",
    )
    parser = _RenderedImageParser()
    try:
        parser.feed(renderer.convert(report_text))
        parser.close()
    except Exception as exc:
        return None, [f"Report images could not be parsed for review: {exc}"]
    return parser, []


def _is_nonlocal_image_reference(reference):
    parsed = urlparse(str(reference).strip())
    return (
        parsed.scheme.casefold() == "data"
        or not safe_image_destination(reference)
    )


def rendered_markdown_visual_paths(report_text):
    """Discover local raster paths that Markdown can render."""
    paths = set()
    rendered, _errors = _rendered_markdown_model(report_text)
    for image in rendered.images if rendered is not None else []:
        reference = image.get("src")
        if not reference or _is_nonlocal_image_reference(reference):
            continue
        parsed = urlparse(reference.strip())
        if reference.startswith("#"):
            continue
        paths.add(Path(unquote(parsed.path)).as_posix())
    return paths


def _user_facing_attribute_errors(report_text, attributes):
    """Forbid renderer metadata from asserting anything absent from gated prose."""
    gated_units = [
        _normalized(block.text)
        for block in validation_report_blocks(report_text)
        if block.text
    ]
    errors = []
    for record in attributes:
        value = _normalized(record.get("value", ""))
        if value and not any(value in unit for unit in gated_units):
            errors.append(
                "Renderer-preserved accessibility text must repeat "
                "evidence-gated report prose "
                f"({record.get('tag')} {record.get('attribute')}): {value[:120]}"
            )
    return errors


def _approved_visual_assets(
    report_path,
    report_text,
    review,
    *,
    allowed_link_urls=(),
):
    """Validate reviewed local visuals and return receipt-safe bindings."""
    report_root = Path(report_path).resolve().parent
    approved = []
    rendered, errors = _rendered_markdown_model(report_text)
    images = rendered.images if rendered is not None else []
    if rendered is not None:
        allowed_link_urls = set(allowed_link_urls)
        for violation in sorted(set(rendered.policy_violations)):
            errors.append(
                "Raw HTML outside Alexandria's renderer allowlist is not "
                f"allowed in report Markdown: {violation}."
            )
        for reference in rendered.links:
            value = reference.strip()
            if not safe_link_destination(value):
                errors.append(
                    "Unsafe or non-web link destination is not allowed in "
                    f"report Markdown: {reference}"
                )
            elif (
                not value.startswith("#")
                and value not in allowed_link_urls
            ):
                errors.append(
                    "Rendered report link is not present in the evidence "
                    f"ledger: {reference}"
                )
    for image in images:
        reference = image.get("src")
        if reference and _is_nonlocal_image_reference(reference):
            if urlparse(reference.strip()).scheme.casefold() == "data":
                errors.append(
                    "Embedded data images are not allowed in report Markdown; "
                    "use a reviewed local raster asset."
                )
            else:
                errors.append(
                    "Nonlocal image references are not allowed in report Markdown: "
                    f"{reference}"
                )
    errors.extend(
        _user_facing_attribute_errors(
            report_text,
            rendered.user_facing_attributes if rendered is not None else [],
        )
    )
    seen = set()
    for record in review.get("visual_assets", []):
        if not isinstance(record, dict):
            continue
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            continue
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(
                f"Reviewed visual asset must use a report-relative path: {raw_path}."
            )
            continue
        normalized_path = relative.as_posix()
        if normalized_path in seen:
            errors.append(f"Duplicate visual asset review: {normalized_path}.")
            continue
        seen.add(normalized_path)
        candidate = (report_root / relative).resolve()
        try:
            candidate.relative_to(report_root)
        except ValueError:
            errors.append(
                f"Reviewed visual asset escapes the report directory: {raw_path}."
            )
            continue
        try:
            digest = file_sha256(candidate)
        except OSError as exc:
            errors.append(
                f"Reviewed visual asset could not be verified: {raw_path}: {exc}"
            )
            continue
        if digest != record.get("sha256"):
            errors.append(
                f"Reviewed visual asset hash does not match: {raw_path}."
            )
            continue
        if record.get("disposition") != "approved":
            errors.append(f"Visual asset is not approved: {raw_path}.")
            continue
        approved.append(
            {
                "path": normalized_path,
                "sha256": digest,
                "usage": record.get("usage"),
            }
        )
    discovered = rendered_markdown_visual_paths(report_text)
    body_approvals = {
        record["path"]
        for record in approved
        if record.get("usage") in {"body", "body_and_cover"}
    }
    for path in sorted(discovered - body_approvals):
        errors.append(f"Unapproved visual asset in report Markdown: {path}.")
    for path in sorted(body_approvals - discovered):
        errors.append(f"Unused visual asset approval in report Markdown: {path}.")
    return approved, errors


def _write_receipt(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise


def run_content_gate(
    report_path,
    ledger_path,
    review_note_path,
    receipt_path,
    *,
    source_fidelity_receipt_path=None,
    force=False,
):
    """Return errors; on success write a receipt bound to every input."""
    report_path = Path(report_path).resolve()
    ledger_path = Path(ledger_path).resolve()
    review_note_path = Path(review_note_path).resolve()
    receipt_path = Path(receipt_path).resolve()

    errors = []
    if not source_fidelity_receipt_path:
        errors.append(
            "Source-fidelity receipt is required before content review."
        )
        return errors
    source_fidelity_receipt_path = Path(
        source_fidelity_receipt_path
    ).resolve()
    collisions = artifact_collision_errors(
        {
            "final report": report_path,
            "evidence ledger": ledger_path,
            "content review": review_note_path,
            "source-fidelity receipt": source_fidelity_receipt_path,
        },
        {"content receipt": receipt_path},
    )
    if collisions:
        return collisions
    if receipt_path.exists() and not force:
        return [
            f"Content receipt already exists: {receipt_path}. "
            "Use --force to replace it."
        ]
    source_receipt, source_errors = _read_json(
        source_fidelity_receipt_path,
        "Source-fidelity receipt",
    )
    errors.extend(source_errors)
    if source_receipt is not None:
        errors.extend(
            validate_source_fidelity_receipt(ledger_path, source_receipt)
        )
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
    errors.extend(_section_review_errors(report_text, review))
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

    scores = review.get("scores", {})
    if isinstance(scores, dict):
        for name, result in scores.items():
            if (
                isinstance(result, dict)
                and isinstance(result.get("score"), int)
                and result["score"] < 4
            ):
                errors.append(
                    f"Content review score {name} is {result['score']}; "
                    "minimum passing score is 4."
                )
    checks = review.get("checks", {})
    if isinstance(checks, dict):
        for name, passed in checks.items():
            if passed is False:
                errors.append(f"Content review check {name} did not pass.")

    report_hash = file_sha256(report_path)
    ledger_hash = file_sha256(ledger_path)
    approved_visual_assets, visual_asset_errors = _approved_visual_assets(
        report_path,
        report_text,
        review,
        allowed_link_urls={
            source.get("url")
            for source in ledger.get("sources", [])
            if isinstance(source, dict) and source.get("url")
        },
    )
    errors.extend(visual_asset_errors)
    errors.extend(
        artifact_collision_errors(
            {
                f"approved visual asset {index}": (
                    report_path.parent / record["path"]
                )
                for index, record in enumerate(
                    approved_visual_assets,
                    start=1,
                )
            },
            {"content receipt": receipt_path},
        )
    )
    if not _same_bound_name(review.get("report_path"), report_path):
        errors.append("Content review belongs to a different final report.")
    if review.get("report_sha256") != report_hash:
        errors.append("Content review does not match the final report.")
    if not _same_bound_name(review.get("ledger_path"), ledger_path):
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
        "schema_version": 2,
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
        "source_fidelity_receipt_path": str(source_fidelity_receipt_path),
        "source_fidelity_receipt_sha256": file_sha256(
            source_fidelity_receipt_path
        ),
        "minimum_score": min(item["score"] for item in scores.values()),
        "approved_visual_assets": approved_visual_assets,
    }
    _write_receipt(receipt_path, receipt)
    return []


def validate_content_receipt(
    report_path,
    ledger_path,
    receipt,
    *,
    source_fidelity_receipt_path=None,
    expected_lang=None,
):
    """Verify and deterministically replay a content-gate receipt."""
    report_path = Path(report_path).resolve()
    ledger_path = Path(ledger_path).resolve()
    if not isinstance(receipt, dict):
        return ["Content receipt root must be an object."]

    errors = []
    if receipt.get("schema_version") != 2:
        errors.append("Content receipt has an unsupported schema version.")
    if receipt.get("status") != "passed":
        errors.append("Content receipt does not record a passing gate.")
    if expected_lang and receipt.get("report_lang") != expected_lang:
        errors.append("Content receipt language does not match the expected report language.")
    if not _same_bound_name(receipt.get("report_path"), report_path):
        errors.append("Content receipt belongs to a different report.")
    if not _same_bound_name(receipt.get("ledger_path"), ledger_path):
        errors.append("Content receipt belongs to a different ledger.")
    if not source_fidelity_receipt_path:
        errors.append("Source-fidelity receipt is required.")
        source_fidelity_receipt_path = None
    else:
        source_fidelity_receipt_path = Path(
            source_fidelity_receipt_path
        ).resolve()
        if not _same_bound_name(
            receipt.get("source_fidelity_receipt_path"),
            source_fidelity_receipt_path,
        ):
            errors.append(
                "Content receipt belongs to a different source-fidelity receipt."
            )
        source_receipt, source_errors = _read_json(
            source_fidelity_receipt_path,
            "Source-fidelity receipt",
        )
        errors.extend(source_errors)
        if source_receipt is not None:
            errors.extend(
                validate_source_fidelity_receipt(ledger_path, source_receipt)
            )
        try:
            source_hash = file_sha256(source_fidelity_receipt_path)
        except OSError as exc:
            errors.append(
                f"Source-fidelity receipt could not be verified: {exc}"
            )
        else:
            if receipt.get("source_fidelity_receipt_sha256") != source_hash:
                errors.append(
                    "Source-fidelity receipt has changed since content review."
                )

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
                source_fidelity_receipt_path=source_fidelity_receipt_path,
            )
            errors.extend(
                f"Content gate recheck failed: {error}"
                for error in rerun_errors
            )
            if not rerun_errors:
                regenerated_receipt, regenerated_errors = _read_json(
                    regenerated,
                    "Regenerated content receipt",
                )
                errors.extend(regenerated_errors)
                if (
                    regenerated_receipt is not None
                    and receipt.get("approved_visual_assets")
                    != regenerated_receipt.get("approved_visual_assets")
                ):
                    errors.append(
                        "Content receipt visual asset approvals differ from "
                        "the completed content review."
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
    parser.add_argument(
        "--source-fidelity-receipt",
        required=True,
        help="passing source-fidelity receipt bound to the evidence ledger",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing content-gate receipt",
    )
    args = parser.parse_args(argv)

    errors = run_content_gate(
        args.report,
        args.ledger,
        args.review_note,
        args.receipt,
        source_fidelity_receipt_path=args.source_fidelity_receipt,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[OK] Content quality gate passed: {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
