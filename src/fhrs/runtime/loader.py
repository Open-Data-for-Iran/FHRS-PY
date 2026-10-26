"""Build runtime datasets from manifests or Python package declarations."""

import os
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, overload

from ..manifest import load as read_manifest
from ..manifest.loader import _resolve_collection
from ..manifest.models import Dataset as DatasetManifest
from .managed import ManagedDataset
from .objects import Dataset


@overload
def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: Literal[True],
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> ManagedDataset: ...


@overload
def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: bool = False,
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset: ...


def load_manifest(
    urlpath: str | os.PathLike[str],
    *,
    manage: bool = False,
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load a manifest, optionally binding managed runtime subclasses."""
    manifest = read_manifest(urlpath, storage_options=storage_options)
    dataset_type = ManagedDataset if manage else Dataset
    return dataset_type(manifest, working_directory=working_directory)


@overload
def load_package(
    package_name: str,
    *,
    manage: Literal[True],
    setup_module: str = "fhrs_setup",
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> ManagedDataset: ...


@overload
def load_package(
    package_name: str,
    *,
    manage: bool = False,
    setup_module: str = "fhrs_setup",
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset: ...


def load_package(
    package_name: str,
    *,
    manage: bool = False,
    setup_module: str = "fhrs_setup",
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
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
    manifest = _resolve_collection(manifest)
    dataset_type = ManagedDataset if manage else Dataset
    return dataset_type(manifest, working_directory=working_directory)
