"""Bind a rendered PDF to the exact artifacts authorized for delivery."""

import hashlib
import html
import json
import re
import tempfile
from pathlib import Path

RENDER_BINDING_PREFIX = "alexandria-input-v1:"
ARTIFACT_LABELS = (
    "report",
    "ledger",
    "rewild_receipt",
    "content_receipt",
    "source_fidelity_receipt",
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def render_manifest(
    *paths,
    render_inputs=None,
    rendered_html=None,
    assets=(),
):
    """Describe every gated artifact and visible renderer input."""
    if len(paths) != len(ARTIFACT_LABELS):
        raise ValueError(
            f"Render binding requires {len(ARTIFACT_LABELS)} artifacts."
        )
    asset_records = sorted(
        (
            {
                "path": str(Path(record["path"]).resolve()),
                "sha256": str(record["sha256"]),
            }
            for record in assets
        ),
        key=lambda record: record["path"],
    )
    return {
        "artifacts": {
            label: file_sha256(path)
            for label, path in zip(ARTIFACT_LABELS, paths, strict=True)
        },
        "render_inputs": _json_safe(render_inputs or {}),
        "rendered_html_sha256": (
            hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
            if rendered_html is not None
            else None
        ),
        "assets": asset_records,
    }


def _binding_for_manifest(manifest):
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RENDER_BINDING_PREFIX + hashlib.sha256(canonical).hexdigest()


def expected_render_binding(
    *paths,
    render_inputs=None,
    rendered_html=None,
    assets=(),
):
    """Return one stable token for all inputs that determine visible output."""
    return _binding_for_manifest(
        render_manifest(
            *paths,
            render_inputs=render_inputs,
            rendered_html=rendered_html,
            assets=assets,
        )
    )


def binding_meta_tag(binding):
    return (
        '<meta name="keywords" content="'
        + html.escape(str(binding), quote=True)
        + '">'
    )


def validate_render_binding(binding, *paths):
    """Return an error unless a PDF token matches the current gated artifacts."""
    value = str(binding or "").strip()
    if re.fullmatch(
        re.escape(RENDER_BINDING_PREFIX) + r"[0-9a-f]{64}",
        value,
    ) is None:
        return ["PDF is missing a valid Alexandria render binding."]
    try:
        expected = expected_render_binding(*paths)
    except (OSError, ValueError) as exc:
        return [f"Render binding inputs could not be verified: {exc}"]
    if value != expected:
        return ["PDF was rendered from different gated artifacts."]
    return []


def build_render_receipt(
    pdf_path,
    *artifact_paths,
    binding,
    render_inputs,
    rendered_html,
    assets=(),
    recorded_pdf_path=None,
):
    """Return a renderer-issued receipt bound to the exact PDF bytes."""
    manifest = render_manifest(
        *artifact_paths,
        render_inputs=render_inputs,
        rendered_html=rendered_html,
        assets=assets,
    )
    expected = _binding_for_manifest(manifest)
    if binding != expected:
        raise ValueError("Render binding does not match the renderer manifest.")
    return {
        "schema_version": 1,
        "status": "rendered",
        "pdf_path": str(
            Path(recorded_pdf_path or pdf_path).resolve()
        ),
        "pdf_sha256": file_sha256(pdf_path),
        "binding": binding,
        "manifest": manifest,
    }


def validate_render_receipt(
    pdf_path,
    receipt,
    *artifact_paths,
    pdf_binding=None,
):
    """Verify renderer provenance and the exact delivered PDF bytes."""
    if isinstance(receipt, (str, Path)):
        try:
            receipt = json.loads(
                Path(receipt).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            return [f"Render receipt could not be read: {exc}"]
    if not isinstance(receipt, dict):
        return ["Render receipt root must be an object."]
    errors = []
    if receipt.get("schema_version") != 1:
        errors.append("Render receipt has an unsupported schema version.")
    if receipt.get("status") != "rendered":
        errors.append("Render receipt does not record a completed render.")
    if pdf_binding is not None and receipt.get("binding") != str(
        pdf_binding or ""
    ).strip():
        errors.append(
            "PDF metadata binding does not match the renderer-issued receipt."
        )
    if receipt.get("pdf_path") != str(Path(pdf_path).resolve()):
        errors.append("Render receipt belongs to a different PDF path.")
    try:
        actual_pdf_hash = file_sha256(pdf_path)
    except OSError as exc:
        errors.append(f"Rendered PDF could not be hashed: {exc}")
    else:
        if receipt.get("pdf_sha256") != actual_pdf_hash:
            errors.append(
                "Rendered PDF bytes do not match the renderer-issued receipt."
            )
    manifest = receipt.get("manifest")
    if not isinstance(manifest, dict):
        errors.append("Render receipt is missing its input manifest.")
        return errors
    try:
        current_artifacts = {
            label: file_sha256(path)
            for label, path in zip(
                ARTIFACT_LABELS,
                artifact_paths,
                strict=True,
            )
        }
    except (OSError, ValueError) as exc:
        errors.append(f"Render receipt inputs could not be verified: {exc}")
    else:
        if manifest.get("artifacts") != current_artifacts:
            errors.append(
                "Render receipt was issued for different gated artifacts."
            )

    assets = manifest.get("assets")
    if not isinstance(assets, list):
        errors.append("Render receipt asset manifest must be an array.")
    else:
        for record in assets:
            if not isinstance(record, dict):
                errors.append("Render receipt contains an invalid asset entry.")
                continue
            try:
                digest = file_sha256(record.get("path", ""))
            except OSError as exc:
                errors.append(
                    f"Render receipt asset could not be verified: {exc}"
                )
                continue
            if digest != record.get("sha256"):
                errors.append(
                    "A visible render asset changed after PDF generation: "
                    f"{record.get('path')}"
                )
    try:
        expected_binding = _binding_for_manifest(manifest)
    except (TypeError, ValueError) as exc:
        errors.append(f"Render receipt manifest is invalid: {exc}")
    else:
        if receipt.get("binding") != expected_binding:
            errors.append("Render receipt binding does not match its manifest.")

    render_inputs = manifest.get("render_inputs")
    if not isinstance(render_inputs, dict):
        errors.append("Render receipt is missing its visible render inputs.")
        return errors
    try:
        try:
            from .md_to_pdf import prepare_pdf_render, write_prepared_pdf
        except ImportError:
            from md_to_pdf import prepare_pdf_render, write_prepared_pdf

        with tempfile.TemporaryDirectory() as directory:
            reproduced_pdf = Path(directory) / "reproduced.pdf"
            prepared = prepare_pdf_render(
                artifact_paths[0],
                ledger=artifact_paths[1],
                rewild_receipt=artifact_paths[2],
                content_receipt=artifact_paths[3],
                source_fidelity_receipt=artifact_paths[4],
                render_inputs=render_inputs,
            )
            write_prepared_pdf(
                prepared,
                reproduced_pdf,
                asset_root=Path(artifact_paths[0]).resolve().parent,
            )
            reproduced_hash = file_sha256(reproduced_pdf)
    except (IndexError, OSError, RuntimeError, TypeError, ValueError) as exc:
        errors.append(f"Deterministic rerender could not be completed: {exc}")
    else:
        if prepared["binding"] != receipt.get("binding"):
            errors.append(
                "Deterministic rerender produced a different input binding."
            )
        if reproduced_hash != receipt.get("pdf_sha256"):
            errors.append(
                "Deterministic rerender does not match the delivered PDF bytes."
            )
    return errors
