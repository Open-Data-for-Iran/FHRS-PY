"""Dataset context and its named runtime storages."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from ...manifest import dump as dump_manifest
from ...manifest.models.dataset import Dataset as DatasetManifest
from ._base import BaseCollection
from .source import Source
from .storage import Storage


@dataclass(frozen=True, slots=True, eq=False)
class Dataset(BaseCollection):
    """A dataset manifest bound to its source, contents, and storages."""

    manifest: DatasetManifest
    source: Source | None = None
    storages: Mapping[str, Storage] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.source is None and hasattr(self.manifest, "_storage"):
            self._setattr("source", Source(**self.manifest._storage))
        self._setattr(
            "storages",
            MappingProxyType(
                {
                    name: Storage(manifest, name=name, dataset=self)
                    for name, manifest in self.manifest.storages.items()
                }
            ),
        )
        self._bind_contents(dataset=self)

    @property
    def name(self) -> str:
        return self.manifest.name

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
