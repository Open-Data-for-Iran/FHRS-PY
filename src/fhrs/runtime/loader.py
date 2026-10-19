"""Build runtime datasets from manifests or Python package declarations."""

import os
from importlib import import_module
from pathlib import Path
from typing import Any

from ..manifest import Dataset as DatasetManifest
from ..manifest import load as read_manifest
from ..manifest.loader import _resolve_collection
from .objects import Dataset


def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load a manifest and bind its resolved contents to a runtime dataset."""
    manifest = read_manifest(urlpath, storage_options=storage_options)
    return Dataset(manifest, working_directory=working_directory)


def load_package(
    package_name: str,
    *,
    setup_module: str = "fhrs_setup",
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load ``<package_name>.<setup_module>.dataset`` as a runtime dataset.

    The package must be importable and declare a manifest Dataset. Hyphens
    in package names are treated as underscores. Relative resources and
    collection manifests resolve beside the setup module. Import errors
    propagate, and the package's original declaration is left unchanged.
    """
    setup = import_module(f"{package_name.replace('-', '_')}.{setup_module}")
    setup_file = getattr(setup, "__file__", None)
    if setup_file is None:
        raise ValueError(f"Setup module {setup.__name__!r} has no file location")
    manifest = setup.dataset
    if not isinstance(manifest, DatasetManifest):
        raise TypeError(f"{setup.__name__}.dataset must be a manifest Dataset")
    manifest = manifest.model_copy(deep=True)
    manifest._storage = {
        "urlpath": str(Path(setup_file).resolve()),
        "storage_options": {},
    }
    manifest = _resolve_collection(manifest)
    return Dataset(manifest, working_directory=working_directory)
