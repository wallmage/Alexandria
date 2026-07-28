#!/usr/bin/env python3
"""Validate an Alexandria evidence ledger and its internal references."""

import argparse
import json
import sys
from datetime import date
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
    sources_by_id = {
        source.get("source_id"): source
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }
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
        if (
            item.get("priority") == "high"
            and item.get("status") in {"unstarted", "in_progress"}
        ):
            errors.append(f"High-priority coverage {area} is unresolved.")
        if item.get("status") == "gap" and not str(
            item.get("gap_impact") or ""
        ).strip():
            errors.append(f"Coverage {area} is a gap but has no gap impact.")

    report_date_value = data.get("report_date")
    try:
        report_day = (
            date.fromisoformat(report_date_value)
            if isinstance(report_date_value, str)
            else None
        )
    except ValueError:
        report_day = None
    for source_id, source in sources_by_id.items():
        try:
            published = (
                date.fromisoformat(source["published"])
                if isinstance(source.get("published"), str)
                else None
            )
            accessed = (
                date.fromisoformat(source["accessed"])
                if isinstance(source.get("accessed"), str)
                else None
            )
        except ValueError:
            continue
        if published and report_day and published > report_day:
            errors.append(f"{source_id} is published after the report date.")
        if published and accessed and published > accessed:
            errors.append(f"{source_id} is published after it was accessed.")

    def foundation_source_ids(claim_id, visited=None):
        visited = set() if visited is None else set(visited)
        if claim_id in visited:
            return set()
        visited.add(claim_id)
        claim = claims_by_id.get(claim_id, {})
        linked = claim.get("source_ids", [])
        foundations = set(linked) if isinstance(linked, list) else set()
        supports = claim.get("supports", [])
        if isinstance(supports, list):
            for related_id in supports:
                foundations.update(foundation_source_ids(related_id, visited))
        return foundations

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
                elif relation == "contradicts":
                    other = claims_by_id.get(related_id, {})
                    reverse = other.get("contradicts", [])
                    if not isinstance(reverse, list) or claim_id not in reverse:
                        errors.append(
                            f"{claim_id} contradicts {related_id}, but the "
                            "relationship is not reciprocal."
                        )
        if claim.get("status") == "disputed":
            if not str(claim.get("resolution") or "").strip():
                errors.append(f"{claim_id} is disputed but has no resolution.")
            if not claim.get("contradicts"):
                errors.append(
                    f"{claim_id} is disputed but has no contradicting claim."
                )

        if (
            claim.get("kind") == "analysis"
            and claim.get("importance") == "key"
        ):
            triangulation = claim.get("triangulation", {})
            triangulation_status = (
                triangulation.get("status")
                if isinstance(triangulation, dict)
                else None
            )
            families = {
                sources_by_id[source_id].get("source_family")
                for source_id in foundation_source_ids(claim_id)
                if source_id in sources_by_id
                and sources_by_id[source_id].get("source_family")
            }
            if triangulation_status == "met" and len(families) < 2:
                errors.append(
                    f"{claim_id} declares triangulation met but has "
                    f"{len(families)} source family."
                )
            if triangulation_status == "limited":
                if claim.get("confidence") == "high":
                    errors.append(
                        f"{claim_id}: high-confidence key judgment cannot "
                        "use limited triangulation."
                    )
                if not str(claim.get("limitations") or "").strip():
                    errors.append(
                        f"{claim_id} has limited triangulation but no limitation."
                    )
            if triangulation_status == "not_applicable":
                errors.append(
                    f"{claim_id} is a key analysis; triangulation cannot be "
                    "not applicable."
                )

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

    synthesis = data.get("synthesis")
    if isinstance(synthesis, dict):
        central = synthesis.get("central_judgment_claim_ids", [])
        central = central if isinstance(central, list) else []
        counterevidence = synthesis.get("counterevidence_claim_ids", [])
        counterevidence = (
            counterevidence if isinstance(counterevidence, list) else []
        )
        for claim_id in central:
            claim = claims_by_id.get(claim_id)
            if not claim:
                errors.append(f"Synthesis references unknown central judgment {claim_id}.")
            elif (
                claim.get("importance") != "key"
                or claim.get("include_in_report") is not True
            ):
                errors.append(
                    f"Central judgment {claim_id} must be an included key claim."
                )
        for claim_id, claim in claims_by_id.items():
            if (
                claim.get("importance") == "key"
                and claim.get("include_in_report") is True
                and claim_id not in central
            ):
                errors.append(
                    f"Key report claim {claim_id} is missing from the central synthesis."
                )
        for claim_id in counterevidence:
            if claim_id not in claim_set:
                errors.append(
                    f"Synthesis references unknown counterevidence {claim_id}."
                )

        for implication in synthesis.get("implications", []):
            if not isinstance(implication, dict):
                continue
            for claim_id in implication.get("claim_ids", []):
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown implication claim {claim_id}."
                    )
        for takeaway in synthesis.get("decisions_or_takeaways", []):
            if not isinstance(takeaway, dict):
                continue
            for claim_id in takeaway.get("rationale_claim_ids", []):
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown takeaway rationale {claim_id}."
                    )
        for scenario in synthesis.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            for claim_id in scenario.get("claim_ids", []):
                if claim_id not in claim_set:
                    errors.append(
                        f"Synthesis references unknown scenario claim {claim_id}."
                    )

        high_priority_claims = {
            claim_id
            for item in coverage
            if isinstance(item, dict) and item.get("priority") == "high"
            for claim_id in item.get("claim_ids", [])
        }
        for claim_id in central:
            if claim_id in claim_set and claim_id not in high_priority_claims:
                errors.append(
                    f"Central judgment {claim_id} is not covered by a "
                    "high-priority research area."
                )
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
