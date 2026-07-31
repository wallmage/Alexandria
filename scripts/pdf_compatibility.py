#!/usr/bin/env python3
"""Compare PDF pages rendered by independent engines."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

try:
    from .render_pdf_pages import render_pages
except ImportError:
    from render_pdf_pages import render_pages

MIN_DETAIL_RATIO = 0.75


def _edge_energy(path):
    with Image.open(path) as image:
        grayscale = image.convert("L")
        if grayscale.width > 4 and grayscale.height > 4:
            grayscale = grayscale.crop(
                (2, 2, grayscale.width - 2, grayscale.height - 2)
            )
        return ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).mean[0]


def compare_render_sets(reference_dir, candidate_dir):
    reference_pages = sorted(Path(reference_dir).glob("page-*.png"))
    candidate_pages = sorted(Path(candidate_dir).glob("page-*.png"))
    errors = []
    metrics = {"page_count": len(reference_pages), "pages": []}
    if len(reference_pages) != len(candidate_pages):
        errors.append(
            f"page count differs: {len(reference_pages)} vs {len(candidate_pages)}"
        )
        return errors, metrics

    for reference, candidate in zip(
        reference_pages, candidate_pages, strict=True
    ):
        with Image.open(reference) as ref_image, Image.open(candidate) as image:
            if ref_image.size != image.size:
                errors.append(
                    f"{candidate.name} dimensions differ: "
                    f"{ref_image.size} vs {image.size}"
                )
                continue
        reference_energy = _edge_energy(reference)
        candidate_energy = _edge_energy(candidate)
        ratio = (
            candidate_energy / reference_energy
            if reference_energy > 1e-9
            else 1.0 if candidate_energy <= 1e-9 else float("inf")
        )
        metrics["pages"].append(
            {"page": candidate.name, "detail_ratio": round(ratio, 3)}
        )
        if ratio < MIN_DETAIL_RATIO:
            errors.append(
                f"{candidate.name} visual detail ratio {ratio:.3f} is below "
                f"{MIN_DETAIL_RATIO:.2f}"
            )
    return errors, metrics


def audit_pdfs(pdf_dir, output_dir, backends):
    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDFs found: {pdf_dir}")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {}
    for pdf in pdfs:
        engine_dirs = {}
        for backend in backends:
            target = output_dir / pdf.stem / backend
            render_pages(pdf, target, dpi=96, backend=backend)
            engine_dirs[backend] = target
        reference = "pdfium" if "pdfium" in engine_dirs else backends[0]
        report[pdf.name] = {}
        for backend in backends:
            if backend == reference:
                continue
            errors, metrics = compare_render_sets(
                engine_dirs[reference], engine_dirs[backend]
            )
            report[pdf.name][backend] = metrics
            if errors:
                detail = "; ".join(errors)
                raise RuntimeError(f"{pdf.name}/{backend}: {detail}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross-render PDFs with independent engines"
    )
    parser.add_argument("pdf_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--backends",
        default="pdfium,poppler,mupdf,ghostscript",
        help="Comma-separated renderers",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    backends = tuple(
        backend.strip() for backend in args.backends.split(",") if backend.strip()
    )
    if len(backends) < 2:
        parser.error("--backends needs at least two renderers")
    try:
        report = audit_pdfs(args.pdf_dir, args.output_dir, backends)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    print(
        f"[OK] Cross-rendered {len(report)} PDFs with "
        f"{len(backends)} independent engines."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
