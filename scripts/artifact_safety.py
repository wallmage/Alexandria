"""Shared path-identity and publication checks for artifact writers."""

import os
from contextlib import suppress
from pathlib import Path


def _same_artifact(first, second):
    first = Path(first).resolve()
    second = Path(second).resolve()
    if first == second:
        return True
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def artifact_collision_errors(read_paths, write_paths):
    """Reject write targets that alias any input or another output."""
    reads = {
        label: Path(path).resolve()
        for label, path in read_paths.items()
        if path is not None
    }
    writes = {
        label: Path(path).resolve()
        for label, path in write_paths.items()
        if path is not None
    }
    errors = []
    for write_label, write_path in writes.items():
        for read_label, read_path in reads.items():
            if _same_artifact(write_path, read_path):
                errors.append(
                    f"{write_label} must be separate from {read_label}: "
                    f"{write_path}"
                )
        for other_label, other_path in writes.items():
            if write_label >= other_label:
                continue
            if _same_artifact(write_path, other_path):
                errors.append(
                    f"{write_label} must be separate from {other_label}: "
                    f"{write_path}"
                )
    return errors


def publish_temp_file(temp_path, destination, *, force=False):
    """Atomically publish a unique same-directory temporary file.

    ``force=False`` uses a hard link as create-if-absent: it either publishes
    the complete temporary inode or leaves an existing destination untouched.
    """
    temp_path = Path(temp_path)
    destination = Path(destination)
    if temp_path.parent.resolve() != destination.parent.resolve():
        temp_path.unlink(missing_ok=True)
        raise ValueError(
            "Temporary artifact must be created in the destination's same directory."
        )

    if force:
        os.replace(temp_path, destination)
        return destination
    try:
        os.link(temp_path, destination, follow_symlinks=False)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    with suppress(OSError):
        temp_path.unlink()
    # Publication already succeeded. If unlinking the private temporary name
    # failed, returning success avoids contradicting the authoritative target.
    return destination
