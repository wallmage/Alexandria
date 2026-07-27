#!/usr/bin/env python3
"""Render every PDF page to PNG for visual inspection."""

import argparse
from pathlib import Path


def validate_paths(pdf_path, output_dir):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file():
        raise ValueError(f"PDF file not found: {pdf_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return pdf_path, output_dir


def render_pages(pdf_path, output_dir, *, dpi=144):
    pdf_path, output_dir = validate_paths(pdf_path, output_dir)
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
    print(f"[OK] Rendered {page_count} pages: {output_dir}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render PDF pages to PNG")
    parser.add_argument("pdf", help="Input PDF")
    parser.add_argument("output_dir", help="New or empty output directory")
    parser.add_argument("--dpi", type=int, default=144, help="Render resolution")
    args = parser.parse_args(argv)
    if not 72 <= args.dpi <= 300:
        parser.error("--dpi must be between 72 and 300")
    try:
        render_pages(args.pdf, args.output_dir, dpi=args.dpi)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
