"""Find the main manifest in a dataset directory."""

import os
import posixpath
from typing import Any

import fsspec


def discover(
    urlpath: str | os.PathLike[str],
    *,
    storage_options: dict[str, Any] | None = None,
) -> str:
    """Return a file unchanged or find a directory's unique FHRS manifest.

    Recognizes fhrs and .fhrs files, or manifest files inside fhrs and .fhrs
    directories, with .yaml, .yml, or .json extensions. Does not search upward
    or recursively. Raises FileNotFoundError for missing entries and ValueError
    for ambiguous directories.
    """
    urlpath = os.fspath(urlpath)
    if not urlpath:
        raise ValueError("Manifest path must be nonempty")
    filesystem, fs_path = fsspec.url_to_fs(urlpath, **(storage_options or {}))
    if filesystem.isfile(fs_path):
        return urlpath
    if not filesystem.isdir(fs_path):
        raise FileNotFoundError(f"Manifest path does not exist: {urlpath}")

    entries = ("fhrs", ".fhrs", "fhrs/manifest", ".fhrs/manifest")
    if posixpath.basename(fs_path.rstrip("/")) in ("fhrs", ".fhrs"):
        entries = ("manifest",)
    matches = [
        f"{entry}.{suffix}"
        for entry in entries
        for suffix in ("yaml", "yml", "json")
        if filesystem.isfile(posixpath.join(fs_path, f"{entry}.{suffix}"))
    ]
    if not matches:
        raise FileNotFoundError(f"No FHRS manifest found in {urlpath}")
    if len(matches) > 1:
        raise ValueError(f"Multiple FHRS manifests found in {urlpath}: {matches}")
    separator = "" if urlpath.endswith(("/", "\\")) else "/"
    return f"{urlpath}{separator}{matches[0]}"
