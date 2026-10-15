"""Dataset context and its named runtime storages."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

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
