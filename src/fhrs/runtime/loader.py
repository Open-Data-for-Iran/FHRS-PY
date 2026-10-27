"""Build runtime datasets from manifests or Python package declarations."""

import os
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, overload

from ..manifest import load as read_manifest
from ..manifest.loader import _load_version, _resolve_collection
from ..manifest.models import Dataset as DatasetManifest
from .managed import ManagedDataset
from .objects import Dataset


@overload
def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: Literal[True],
    version: str | None = None,
    storage_options: dict[str, Any] | None = None,
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> ManagedDataset: ...


@overload
def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: bool = False,
    version: str | None = None,
    storage_options: dict[str, Any] | None = None,
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset: ...


def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: bool = False,
    version: str | None = None,
    storage_options: dict[str, Any] | None = None,
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load a manifest, optionally binding managed runtime subclasses."""
    manifest = read_manifest(urlpath, version=version, storage_options=storage_options)
    dataset_type = ManagedDataset if manage else Dataset
    return dataset_type(manifest, local_directory=local_directory)


@overload
def load_package(
    package_name: str,
    *,
    manage: Literal[True],
    version: str | None = None,
    setup_module: str = "fhrs_setup",
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> ManagedDataset: ...


@overload
def load_package(
    package_name: str,
    *,
    manage: bool = False,
    version: str | None = None,
    setup_module: str = "fhrs_setup",
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset: ...


def load_package(
    package_name: str,
    *,
    manage: bool = False,
    version: str | None = None,
    setup_module: str = "fhrs_setup",
    local_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load ``<package_name>.<setup_module>.dataset`` as a runtime dataset.

    The package must be importable and declare a manifest Dataset. Hyphens
    in package names are treated as underscores. Relative resources and
    collection manifests resolve beside the setup module. Import errors
    propagate, and the package's original declaration is left unchanged.
    Pass manage=True to bind managed runtime subclasses.
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
    manifest = (
        _load_version(manifest, version)
        if version is not None
        else _resolve_collection(manifest)
    )
    dataset_type = ManagedDataset if manage else Dataset
    return dataset_type(manifest, local_directory=local_directory)
