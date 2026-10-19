"""Dataset context and its named runtime storages."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

from ...manifest import dump as dump_manifest
from ...manifest.models.dataset import Dataset as DatasetManifest
from ...manifest.models.storage import BaseStorage as StorageManifest
from ._base import BaseCollection
from .collection import Collection
from .resource import Resource
from .source import Source
from .storage import Storage, _WorkingStorage
from .table import Table


@dataclass(frozen=True, slots=True, eq=False)
class Dataset(BaseCollection):
    """A dataset manifest bound to its source, contents, and storages."""

    # Concrete types used when binding this dataset's entire runtime graph.
    _collection_type: ClassVar[type[Collection]] = Collection
    _resource_type: ClassVar[type[Resource]] = Resource
    _table_type: ClassVar[type[Table]] = Table
    _storage_type: ClassVar[type[Storage]] = Storage
    _working_storage_type: ClassVar[type[_WorkingStorage]] = _WorkingStorage

    manifest: DatasetManifest
    source: Source | None = None
    working_directory: str | os.PathLike[str] = "data/<dataset.name>"
    storages: Mapping[str, Storage] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        directory = os.fspath(self.working_directory)
        if "<dataset.name>" in directory:
            if Path(self.name).name != self.name or self.name in (".", ".."):
                raise ValueError(
                    "Working directory template requires a dataset name without path components"
                )
            directory = directory.replace("<dataset.name>", self.name)
        self._setattr("working_directory", Path(directory).resolve())
        if self.source is None and hasattr(self.manifest, "_storage"):
            self._setattr("source", Source(**self.manifest._storage))
        self._set_mapping(
            "storages",
            {
                "working": self._working_storage_type(
                    StorageManifest(protocol="file"), name="working", dataset=self
                ),
                **{
                    name: self._storage_type(manifest, name=name, dataset=self)
                    for name, manifest in self.manifest.storages.items()
                },
            },
        )
        self._bind_contents(dataset=self)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def schema_version(self) -> str | None:
        """The declared data schema version, if supplied."""
        return self.manifest.schema_version

    @property
    def release(self) -> str | None:
        """The declared data release identifier, if supplied."""
        return self.manifest.release

    def storage(self, name: str) -> Storage:
        return self.storages[name]

    def dump(
        self,
        destination: str | os.PathLike[str] | None = None,
        *,
        format: Literal["yaml", "json"] | None = None,
        layout: Mapping[str, str] | None = None,
        storage_options: dict[str, Any] | None = None,
    ) -> None:
        """Write this dataset's manifest using :func:`fhrs.manifest.dump`.

        Only declarations are written; resource contents and paths are unchanged.
        """
        dump_manifest(
            self.manifest,
            destination,
            format=format,
            layout=layout,
            storage_options=storage_options,
        )
