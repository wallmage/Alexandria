#!/usr/bin/env python3
"""Build full-length, Rewild-gated PDF fixtures for the CI workflow."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.rewild_gate import file_sha256, run_gate  # noqa: E402
from scripts.content_gate import run_content_gate  # noqa: E402


SCORES = (
    "question_answered",
    "evidence_strength",
    "evidence_coverage",
    "reasoning_integrity",
    "counterevidence",
    "explanatory_depth",
    "decision_value",
    "writing_clarity",
)
CHECKS = (
    "central_judgment_answers_question",
    "priority_coverage_resolved",
    "key_claims_traceable",
    "source_independence_calibrated",
    "counterevidence_tested",
    "uncertainty_visible",
    "recommendations_or_implications_supported",
    "forecasts_conditional",
    "section_value_density_reviewed",
    "length_is_substantive_not_padded",
)


CASES = (
    {
        "name": "en",
        "fixture": "sample-report.md",
        "lang": "en",
        "profile": "rewild",
        "url": "https://example.com/research/a-very-long-but-valid-path-that-must-wrap-inside-the-page-instead-of-running-through-the-margin",
        "excerpt": "The pipeline converts Markdown into a styled PDF, builds a contents page, and keeps a source link clickable.",
        "sources_heading": "## Sources",
        "depth": lambda: " ".join(f"observation{index}" for index in range(7500))
        + ".",
    },
    {
        "name": "zh-CN",
        "fixture": "sample-report.zh-CN.md",
        "lang": "zh-CN",
        "profile": "rewild-zh",
        "url": "https://example.com/cn-source",
        "excerpt": "系统会把 Markdown 转成 PDF，建立目录，并保留可点击的资料来源，让测试可以同时核对排版结果和引用路径。",
        "sources_heading": "## 参考资料",
        "depth": lambda: "研究数据市场方法结果分析证据" * 500 + "。",
    },
    {
        "name": "zh-HK",
        "fixture": "sample-report.zh-HK.md",
        "lang": "zh-HK",
        "profile": "rewild-hk",
        "url": "https://example.com/hk-source",
        "excerpt": "系統會把 Markdown 轉成 PDF，建立目錄，並保留可按的資料來源，讓測試可以同時核對排版結果和引用路徑。",
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
    ledger = case_root / "ledger.json"
    content_review = case_root / "content-review.json"
    content_receipt = case_root / "content-receipt.json"
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

    ledger_data = json.loads(
        (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
            encoding="utf-8"
        )
    )
    ledger_data["brief"]["report_language"] = case["lang"]
    ledger_data["sources"][0]["url"] = case["url"]
    ledger_data["claims"][0]["report_excerpts"] = [case["excerpt"]]
    ledger.write_text(
        json.dumps(ledger_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    content_review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "report_path": str(report.resolve()),
                "report_sha256": file_sha256(report),
                "ledger_path": str(ledger.resolve()),
                "ledger_sha256": file_sha256(ledger),
                "report_lang": case["lang"],
                "reviewed_at": "2026-07-28T12:00:00Z",
                "reviewer_mode": "fresh_eyes",
                "scores": {
                    name: {
                        "score": 4,
                        "rationale": (
                            f"The production fixture satisfies the {name} "
                            "requirement within its deliberately synthetic scope."
                        ),
                    }
                    for name in SCORES
                },
                "checks": {name: True for name in CHECKS},
                "findings": [],
                "evidence_limitations": [
                    "This fixture tests production controls, not real-world research."
                ],
                "completion_note": (
                    "The fixture is traceable and fit for exercising the complete "
                    "production gate."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    errors = run_content_gate(
        report,
        ledger,
        content_review,
        content_receipt,
    )
    if errors:
        raise RuntimeError(
            f"{case['name']} fixture failed the Content quality gate: "
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
