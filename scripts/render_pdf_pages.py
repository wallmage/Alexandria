#!/usr/bin/env python3
"""Render every PDF page to PNG for visual inspection."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PDFKIT_RENDERER = Path(__file__).with_name("render_pdfkit_pages.swift")


def validate_paths(pdf_path, output_dir):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file():
        raise ValueError(f"PDF file not found: {pdf_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return pdf_path, output_dir


def render_with_pdfium(pdf_path, output_dir, *, dpi):
    try:
        import pypdfium2 as pdfium
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "PDF page rendering needs pypdfium2. Install dependencies with "
            "'python3 -m pip install -r requirements.txt'."
        ) from exc

    document = pdfium.PdfDocument(pdf_path)
    page_count = len(document)
    try:
        for page_number in range(page_count):
            page = document[page_number]
            try:
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    try:
                        image.save(output_dir / f"page-{page_number + 1:04d}.png")
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        document.close()


def render_with_pdfkit(pdf_path, output_dir, *, dpi):
    swift = shutil.which("swift")
    if not swift:
        raise RuntimeError(
            "Native macOS PDF rendering needs the Swift command-line tool."
        )
    result = subprocess.run(
        [
            swift,
            str(PDFKIT_RENDERER),
            str(pdf_path),
            str(output_dir),
            str(dpi),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"PDFKit page rendering failed: {detail}")


def _renderer_command(*names):
    for name in names:
        command = shutil.which(name)
        if command:
            return command
    raise RuntimeError(f"PDF renderer not found: {', '.join(names)}")


def _run_renderer(command, label):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{label} page rendering failed: {detail}")


def _normalize_page_names(output_dir):
    pages = []
    for path in output_dir.glob("page-*.png"):
        try:
            number = int(path.stem.rsplit("-", 1)[1])
        except ValueError:
            continue
        pages.append((number, path))
    for number, path in sorted(pages):
        target = output_dir / f"page-{number:04d}.png"
        if path != target:
            path.rename(target)


def render_with_poppler(pdf_path, output_dir, *, dpi):
    _run_renderer(
        [
            _renderer_command("pdftocairo"),
            "-png",
            "-r",
            str(dpi),
            str(pdf_path),
            str(output_dir / "page"),
        ],
        "Poppler",
    )
    _normalize_page_names(output_dir)


def render_with_mupdf(pdf_path, output_dir, *, dpi):
    _run_renderer(
        [
            _renderer_command("mutool"),
            "draw",
            "-q",
            "-r",
            str(dpi),
            "-o",
            str(output_dir / "page-%04d.png"),
            str(pdf_path),
        ],
        "MuPDF",
    )


def render_with_ghostscript(pdf_path, output_dir, *, dpi):
    _run_renderer(
        [
            _renderer_command("gs", "gswin64c", "gswin32c"),
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=png16m",
            f"-r{dpi}",
            f"-o{output_dir / 'page-%04d.png'}",
            str(pdf_path),
        ],
        "Ghostscript",
    )


def render_pages(pdf_path, output_dir, *, dpi=144, backend="auto"):
    pdf_path, output_dir = validate_paths(pdf_path, output_dir)
    selected = "pdfkit" if backend == "auto" and sys.platform == "darwin" else backend
    if selected == "auto":
        selected = "pdfium"
    if selected == "pdfkit":
        if sys.platform != "darwin":
            raise RuntimeError("The PDFKit backend is available only on macOS.")
        render_with_pdfkit(pdf_path, output_dir, dpi=dpi)
    elif selected == "pdfium":
        render_with_pdfium(pdf_path, output_dir, dpi=dpi)
    elif selected == "poppler":
        render_with_poppler(pdf_path, output_dir, dpi=dpi)
    elif selected == "mupdf":
        render_with_mupdf(pdf_path, output_dir, dpi=dpi)
    elif selected == "ghostscript":
        render_with_ghostscript(pdf_path, output_dir, dpi=dpi)
    else:
        raise ValueError(f"Unknown PDF rendering backend: {selected}")
    page_count = len(list(output_dir.glob("page-*.png")))
    if not page_count:
        raise RuntimeError(f"{selected} rendered no PDF pages.")
    print(f"[OK] Rendered {page_count} pages: {output_dir}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render PDF pages to PNG")
    parser.add_argument("pdf", help="Input PDF")
    parser.add_argument("output_dir", help="New or empty output directory")
    parser.add_argument("--dpi", type=int, default=144, help="Render resolution")
    parser.add_argument(
        "--backend",
        choices=(
            "auto",
            "pdfium",
            "pdfkit",
            "poppler",
            "mupdf",
            "ghostscript",
        ),
        default="auto",
        help="Rendering engine (auto uses PDFKit on macOS, PDFium elsewhere)",
    )
    args = parser.parse_args(argv)
    if not 72 <= args.dpi <= 300:
        parser.error("--dpi must be between 72 and 300")
    try:
        render_pages(
            args.pdf,
            args.output_dir,
            dpi=args.dpi,
            backend=args.backend,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
