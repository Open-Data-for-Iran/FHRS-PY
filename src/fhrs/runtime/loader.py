"""Build runtime datasets from manifest files or dataset directories."""

import os
from typing import Any

from ..manifest import load as load_manifest
from .objects import Dataset


def load(
    urlpath: str | os.PathLike[str],
    *,
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load a manifest and bind its resolved contents to a runtime dataset."""
    manifest = load_manifest(urlpath, storage_options=storage_options)
    return Dataset(manifest, working_directory=working_directory)
