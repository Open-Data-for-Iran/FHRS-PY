"""Load runtime datasets from Python packages, manifest paths, or URLs."""

import os
from typing import Any, Literal, overload

from .runtime import Dataset, ManagedDataset
from .runtime import loader as runtime_loader


@overload
def load(
    source: str | os.PathLike[str],
    *,
    manage: Literal[True],
    setup_module: str = "fhrs_setup",
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> ManagedDataset: ...


@overload
def load(
    source: str | os.PathLike[str],
    *,
    manage: bool = False,
    setup_module: str = "fhrs_setup",
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset: ...


def load(
    source: str | os.PathLike[str],
    *,
    manage: bool = False,
    setup_module: str = "fhrs_setup",
    storage_options: dict[str, Any] | None = None,
    working_directory: str | os.PathLike[str] = "data/<dataset.name>",
) -> Dataset:
    """Load a package declaration or manifest as a runtime dataset.

    PathLike objects, strings containing path separators or a colon, and
    YAML/JSON filenames use the manifest loader. The strings '.', '..',
    and '.fhrs' also denote paths. Other strings denote Python packages.
    Use a Path object to disambiguate a bare directory name. Errors from
    the selected loader propagate without falling back to the other loader.

    setup_module selects a package's declaration module; storage_options
    configures manifest access and is only accepted for paths and URLs.
    manage=True selects managed subclasses without performing maintenance.
    """
    if (
        isinstance(source, os.PathLike)
        or source in (".", "..", ".fhrs")
        or any(character in source for character in ("/", "\\", ":"))
        or source.lower().endswith((".yaml", ".yml", ".json"))
    ):
        return runtime_loader.load_manifest(
            source,
            manage=manage,
            storage_options=storage_options,
            working_directory=working_directory,
        )
    if storage_options is not None:
        raise ValueError("storage_options is only supported for manifest paths or URLs")
    return runtime_loader.load_package(
        source,
        manage=manage,
        setup_module=setup_module,
        working_directory=working_directory,
    )
