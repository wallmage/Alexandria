#!/usr/bin/env python3
"""Build full-length, Rewild-gated PDF fixtures for the CI workflow."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.rewild_gate import file_sha256, run_gate  # noqa: E402


CASES = (
    {
        "name": "en",
        "fixture": "sample-report.md",
        "lang": "en",
        "profile": "rewild",
        "sources_heading": "## Sources",
        "depth": lambda: " ".join(f"observation{index}" for index in range(7500))
        + ".",
    },
    {
        "name": "zh-CN",
        "fixture": "sample-report.zh-CN.md",
        "lang": "zh-CN",
        "profile": "rewild-zh",
        "sources_heading": "## 参考资料",
        "depth": lambda: "研究数据市场方法结果分析证据" * 500 + "。",
    },
    {
        "name": "zh-HK",
        "fixture": "sample-report.zh-HK.md",
        "lang": "zh-HK",
        "profile": "rewild-hk",
        "sources_heading": "## 參考資料",
        "depth": lambda: "研究數據市場方法結果分析證據" * 500 + "。",
    },
)


def build_case(case, output_root):
    case_root = output_root / case["name"]
    case_root.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tests" / "fixtures" / case["fixture"]
    original = fixture.read_text(encoding="utf-8")
    heading = case["sources_heading"]
    if original.count(heading) != 1:
        raise ValueError(f"{fixture} must contain exactly one {heading!r}")
    report_text = original.replace(
        heading,
        case["depth"]() + "\n\n" + heading,
    )

    report = case_root / "report.md"
    source = case_root / "pre-rewild.md"
    review = case_root / "review.json"
    receipt = case_root / "receipt.json"
    report.write_text(report_text, encoding="utf-8")
    source.write_text(report_text, encoding="utf-8")
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "report_sha256": file_sha256(report),
                "source_sha256": file_sha256(source),
                "report_lang": case["lang"],
                "profile": case["profile"],
                "fidelity_checks": {
                    "facts_and_figures": True,
                    "attribution_and_uncertainty": True,
                    "direction_and_negation": True,
                    "causality": True,
                },
                "findings": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    errors = run_gate(
        report,
        source,
        report_lang=case["lang"],
        review_note_path=review,
        receipt_path=receipt,
    )
    if errors:
        raise RuntimeError(
            f"{case['name']} fixture failed the Rewild gate: "
            + " ".join(errors)
        )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        build_case(case, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
