#!/usr/bin/env python3
"""Validate an Alexandria evidence ledger and its internal references."""

import argparse
import json
import sys
from pathlib import Path


DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "references"
    / "evidence-ledger.schema.json"
)


def _duplicates(values):
    seen = set()
    return sorted({value for value in values if value in seen or seen.add(value)})


def validate_references(data):
    """Check ID uniqueness and links that JSON Schema cannot express."""
    if not isinstance(data, dict):
        return []
    errors = []
    sources = data.get("sources", [])
    claims = data.get("claims", [])
    if not isinstance(sources, list) or not isinstance(claims, list):
        return []
    coverage = data.get("coverage", [])
    if not isinstance(coverage, list):
        coverage = []
    source_ids = [
        source.get("source_id")
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    ]
    claim_ids = [
        claim.get("claim_id")
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    ]
    source_set = set(source_ids)
    claim_set = set(claim_ids)
    claims_by_id = {
        claim.get("claim_id"): claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    }

    errors.extend(f"Duplicate source ID: {item}" for item in _duplicates(source_ids))
    errors.extend(f"Duplicate claim ID: {item}" for item in _duplicates(claim_ids))

    for item in coverage:
        if not isinstance(item, dict):
            continue
        area = item.get("area", "<unknown>")
        coverage_claims = item.get("claim_ids", [])
        if not isinstance(coverage_claims, list):
            continue
        for claim_id in coverage_claims:
            if claim_id not in claim_set:
                errors.append(
                    f"Coverage {area} references unknown claim {claim_id}."
                )

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id", "<unknown>")
        source_links = claim.get("source_ids", [])
        if not isinstance(source_links, list):
            source_links = []
        for source_id in source_links:
            if source_id not in source_set:
                errors.append(f"{claim_id} references unknown source {source_id}.")
        for relation in ("supports", "contradicts"):
            related_claims = claim.get(relation, [])
            if not isinstance(related_claims, list):
                continue
            for related_id in related_claims:
                if related_id == claim_id:
                    errors.append(f"{claim_id} has a circular {relation} reference.")
                if related_id not in claim_set:
                    errors.append(f"{claim_id} references unknown claim {related_id}.")

    circular_paths = set()

    def reaches_sourced_claim(claim_id, path):
        if claim_id in path:
            circular_paths.add(tuple(path + [claim_id]))
            return False
        claim = claims_by_id.get(claim_id)
        if not claim:
            return False
        source_links = claim.get("source_ids", [])
        if isinstance(source_links, list) and source_links:
            return True
        supports = claim.get("supports", [])
        if not isinstance(supports, list):
            return False
        return any(
            reaches_sourced_claim(related_id, path + [claim_id])
            for related_id in supports
        )

    for claim_id, claim in claims_by_id.items():
        if (
            claim.get("kind") == "analysis"
            and claim.get("include_in_report") is True
            and not reaches_sourced_claim(claim_id, [])
        ):
            errors.append(f"{claim_id} has no sourced foundation.")
    for path in sorted(circular_paths):
        errors.append(f"Analysis has circular support: {' -> '.join(path)}.")
    return errors


def validate_schema(data, schema):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError:
        return [
            "Ledger validation needs jsonschema. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ]

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an Alexandria evidence ledger")
    parser.add_argument("ledger", help="Evidence ledger JSON")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="JSON Schema path")
    args = parser.parse_args(argv)

    try:
        data = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    errors = validate_schema(data, schema) + validate_references(data)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Evidence ledger validated: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
