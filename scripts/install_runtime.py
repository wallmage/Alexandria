#!/usr/bin/env python3
"""Complete an isolated installation and prove it can produce readable PDFs."""

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FONT_HASHES = {
    "sc": "dc71173babc38dfd019912965f2b4b3421fb347ebd854e7b96f64ad63673924a",
    "tc": "e822851bd9dcfdc95d4eba4d9f513b23a13a50ae0d556ed4bfed7b14a30e7e5b",
}
FONT_PACKAGE_HASHES = {
    "sc": "2mi+rXWolxvkyVmj7P4QlV/H6x+xfSaJOyrLCrUkEWHy/3CNJaKnL1lu9RrBNoaXEfycSpKMNTCpr2LxpXBzjA==",
    "tc": "/zxPzyAtuRIHhqb1434e8sQYTijLJAu8ET8VgEW29eqJuidOgxr+8qa8nL6mpR6EXmjjqvG2UhVWMkaI+ZjB6Q==",
}
LICENSE_HASH = "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9"


def download_verified(urls, target, digest, algorithm="sha256"):
    target = Path(target)
    if target.is_file() and hashlib.new(algorithm, target.read_bytes()).hexdigest() == digest:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in urls:
        temporary = None
        try:
            with urlopen(url, timeout=20) as response, tempfile.NamedTemporaryFile(
                dir=target.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                checksum = hashlib.new(algorithm)
                while chunk := response.read(1024 * 1024):
                    checksum.update(chunk)
                    output.write(chunk)
            if checksum.hexdigest() != digest:
                raise ValueError("Download checksum mismatch")
            temporary.replace(target)
            return
        except (OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise RuntimeError("Downloads failed: " + "; ".join(errors))


def install_fonts():
    """Use verified OFL fonts; npm's China mirror needs no GitHub access."""
    for language, digest in FONT_HASHES.items():
        package = f"@expo-google-fonts/noto-sans-{language}"
        font_file = f"400Regular/NotoSans{language.upper()}_400Regular.ttf"
        targets = {
            font_file: (ROOT / "assets/fonts" / f"AlexandriaCJK-{language.upper()}.ttf", digest),
            "LICENSE_FONT": (ROOT / "assets/fonts" / f"OFL-NotoSans{language.upper()}.txt", LICENSE_HASH),
        }
        if all(
            target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected
            for target, expected in targets.values()
        ):
            continue
        try:
            if os.environ.get("ALEXANDRIA_MIRROR_FIRST") == "1":
                raise RuntimeError("Use the China mirror first")
            for name, (target, expected) in targets.items():
                download_verified([
                    f"https://unpkg.com/{package}@0.4.2/{name}",
                    f"https://cdn.jsdelivr.net/npm/{package}@0.4.2/{name}",
                ], target, expected)
        except RuntimeError:
            with tempfile.TemporaryDirectory(prefix="alexandria-font-") as folder:
                archive = Path(folder) / "font.tgz"
                suffix = f"{package}/-/noto-sans-{language}-0.4.2.tgz"
                download_verified([
                    f"https://registry.npmmirror.com/{suffix}",
                    f"https://registry.npmjs.org/{suffix}",
                ], archive, base64.b64decode(FONT_PACKAGE_HASHES[language]).hex(), "sha512")
                with tarfile.open(archive) as tar:
                    for name, (target, expected) in targets.items():
                        member = tar.getmember(f"package/{name}")
                        if not member.isfile():
                            raise ValueError("Font package member is not a regular file") from None
                        with tar.extractfile(member) as source:
                            data = source.read()
                        if hashlib.sha256(data).hexdigest() != expected:
                            raise ValueError("Font checksum mismatch") from None
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)


def verify_runtime():
    for requirement in (ROOT / "requirements.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        name, version = requirement.split("==")
        if importlib.metadata.version(name) != version:
            raise RuntimeError(f"Incorrect installed version: {name}")
    for language, digest in FONT_HASHES.items():
        font = ROOT / "assets/fonts" / f"AlexandriaCJK-{language.upper()}.ttf"
        if not font.is_file() or hashlib.sha256(font.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Missing or changed installed font: {language}")

    sys.path.insert(0, str(ROOT))
    from pypdf import PdfReader

    from scripts.md_to_pdf import render_pdf
    from scripts.pdf_quality import check_cjk_fonts
    from scripts.render_pdf_pages import render_pages

    with tempfile.TemporaryDirectory(prefix="alexandria-install-check-") as folder:
        work = Path(folder)
        for language, text in (
            ("en", "The installation can generate a readable report."),
            ("zh-CN", "安装完成，中文报告可以正常阅读。"),
            ("zh-HK", "安裝完成，中文報告可以正常閱讀。"),
        ):
            report, pdf = work / f"{language}.md", work / f"{language}.pdf"
            report.write_text(f"# Alexandria\n\n> {text}\n\n## Check\n\n{text}\n", encoding="utf-8")
            render_pdf(report, pdf, lang=language, template="horizon", manual_review=True)
            reader = PdfReader(pdf)
            extracted = "".join(page.extract_text() or "" for page in reader.pages)
            if "".join(text.split()) not in "".join(extracted.split()):
                raise RuntimeError(f"PDF text check failed: {language}")
            if not any(page.images for page in reader.pages):
                raise RuntimeError(f"PDF template image missing: {language}")
            if language != "en" and any(
                finding.severity == "error" for finding in check_cjk_fonts(pdf, language)[0]
            ):
                raise RuntimeError(f"PDF font check failed: {language}")
            pages = work / f"pages-{language}"
            render_pages(pdf, pages, dpi=72, backend="pdfium")
            if len(list(pages.glob("*.png"))) != len(reader.pages):
                raise RuntimeError(f"PDF page rendering failed: {language}")


def write_launchers(runtime):
    """One path, no JSON: SKILL.md invokes RUNTIME/bin/python (or python.cmd)."""
    launchers = runtime / "bin"
    launchers.mkdir(parents=True, exist_ok=True)
    posix = launchers / "python"
    posix.write_text(
        '#!/bin/sh\n'
        'here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n'
        'MAMBA_ROOT_PREFIX="$here/mamba" exec "$here/bin/micromamba" --no-rc run --prefix "$here/env" python "$@"\n',
        encoding="utf-8",
    )
    posix.chmod(0o755)
    # Bytes, not text: text mode on Windows would turn `\r\n` into `\r\r\n`.
    (launchers / "python.cmd").write_bytes(WINDOWS_LAUNCHER.encode("utf-8"))


#: `%~fI` folds the `..` away so micromamba sees a plain prefix; a missing
#: micromamba is named instead of a silent exit code.
WINDOWS_LAUNCHER = (
    "@echo off\r\n"
    "setlocal\r\n"
    'for %%I in ("%~dp0..") do set "root=%%~fI"\r\n'
    'set "root=%root:/=\\%"\r\n'
    'set "MAMBA_ROOT_PREFIX=%root%\\mamba"\r\n'
    'if not exist "%root%\\Library\\bin\\micromamba.exe" (\r\n'
    '  echo alx launcher: micromamba.exe missing under "%root%\\Library\\bin" 1>&2\r\n'
    "  exit /b 2\r\n"
    ")\r\n"
    '"%root%\\Library\\bin\\micromamba.exe" --no-rc run --prefix "%root%\\env" python %*\r\n'
    "exit /b %ERRORLEVEL%\r\n"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        indexes = ["https://pypi.org/simple", "https://pypi.tuna.tsinghua.edu.cn/simple"]
        if os.environ.get("ALEXANDRIA_MIRROR_FIRST") == "1":
            indexes.reverse()
        for index in indexes:
            result = subprocess.run([
                sys.executable, "-m", "pip", "--isolated", "install",
                "--index-url", index, "--timeout", "20", "--retries", "1",
                "-r", str(ROOT / "requirements.txt"),
            ], check=False)
            if result.returncode == 0:
                break
        else:
            raise RuntimeError("Could not install Python packages from either source")
        install_fonts()
    verify_runtime()
    runtime = args.runtime.resolve()
    mamba = runtime / ("Library/bin/micromamba.exe" if sys.platform == "win32" else "bin/micromamba")
    manifest = {
        "command": [str(mamba), "--no-rc", "run", "--prefix", str(runtime / "env"), "python"],
        "requirements_sha256": hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest(),
        "verified_languages": ["en", "zh-CN", "zh-HK"],
    }
    text = json.dumps(manifest, indent=2) + "\n"
    for target in (runtime / ".runtime.json", ROOT / ".runtime.json"):
        target.write_text(text, encoding="utf-8")
    write_launchers(runtime)
    print("Installation verified.")


if __name__ == "__main__":
    main()
