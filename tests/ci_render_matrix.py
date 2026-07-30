"""Render the full layout matrix through a deterministic production boundary."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import md_to_pdf, validate_report  # noqa: E402
from tests.build_gated_fixtures import (  # noqa: E402
    CASES,
    build_case,
    localized_ledger_report_date,
)
from tests.source_fidelity_transport import (  # noqa: E402
    mock_production_transport,
)

TEMPLATES = (
    "executive",
    "spectrum",
    "atlas",
    "horizon",
    "maison",
    "blueprint",
    "terrain",
    "orbit",
    "sunbeam",
    "current",
    "apricot",
)
SOURCE_RESPONSES = {
    "example.com": (
        200,
        {"content-type": "text/html"},
        b"<html><body><h1>Example Domain</h1></body></html>",
    )
}


def _validation_args(case, case_root, output):
    args = [
        str(case_root / "report.md"),
        "--ledger",
        str(case_root / "ledger.json"),
        "--rewild-receipt",
        str(case_root / "receipt.json"),
        "--source-fidelity-receipt",
        str(case_root / "source-fidelity-receipt.json"),
        "--content-receipt",
        str(case_root / "content-receipt.json"),
        "--pdf",
        str(output),
        "--expected-lang",
        case["lang"],
        "--min-sources",
        "1",
        "--min-sections",
        "4",
        "--min-pages",
        "3",
        "--min-links",
        "1",
    ]
    if case["lang"] == "en":
        args.extend(
            [
                "--min-words",
                "7500",
                "--max-words",
                "15000",
                "--min-text-chars",
                "300",
            ]
        )
    else:
        args.extend(
            [
                "--min-chars",
                "5000",
                "--max-chars",
                "10000",
                "--min-text-chars",
                "100",
            ]
        )
    return args


def run_matrix(output_root):
    fixtures = output_root / "fixtures"
    pdfs = output_root / "pdfs"
    if output_root.exists():
        raise ValueError(f"Matrix output already exists: {output_root}")
    fixtures.mkdir(parents=True)
    pdfs.mkdir()

    with mock_production_transport(SOURCE_RESPONSES):
        for case in CASES:
            build_case(case, fixtures)
        for case in CASES:
            case_root = fixtures / case["name"]
            ledger = json.loads(
                (case_root / "ledger.json").read_text(encoding="utf-8")
            )
            report_date = localized_ledger_report_date(case, ledger)
            for template in TEMPLATES:
                output = pdfs / f"{case['name']}-{template}.pdf"
                md_to_pdf.render_pdf(
                    case_root / "report.md",
                    output,
                    lang=case["lang"],
                    template=template,
                    rewild_receipt=case_root / "receipt.json",
                    ledger=case_root / "ledger.json",
                    source_fidelity_receipt=(
                        case_root / "source-fidelity-receipt.json"
                    ),
                    content_receipt=case_root / "content-receipt.json",
                    report_date=report_date,
                    force=True,
                )
                code = validate_report.main(
                    _validation_args(case, case_root, output)
                )
                if code:
                    raise RuntimeError(
                        f"Validation failed for {case['name']}/{template}."
                    )

    generated = list(pdfs.glob("*.pdf"))
    expected = len(CASES) * len(TEMPLATES)
    if len(generated) != expected:
        raise RuntimeError(f"Expected {expected} PDFs, generated {len(generated)}.")
    print(f"[OK] Rendered and validated {expected} language/template combinations.")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    run_matrix(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
