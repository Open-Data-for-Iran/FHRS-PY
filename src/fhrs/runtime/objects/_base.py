"""Shared bases for runtime objects and collection binding."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from ...manifest.models.collection import Collection as CollectionManifest
from ...manifest.models.dataset import Dataset as DatasetManifest
from ...manifest.models.table import Table as TableManifest

if TYPE_CHECKING:
    from .collection import Collection
    from .dataset import Dataset
    from .member import ResourceMember
    from .resource import Resource
    from .table import Table


class BaseRuntime:
    """Shared support for initializing frozen runtime dataclasses."""

    __slots__ = ()

    def _setattr(self, name: str, value: object) -> None:
        """Assign a field during initialization without invoking the frozen setter."""
        object.__setattr__(self, name, value)

    def _set_mapping[T](self, name: str, values: dict[str, T]) -> None:
        """Assign a read-only mapping during initialization."""
        self._setattr(name, MappingProxyType(values))


@dataclass(frozen=True, slots=True, eq=False)
class BaseCollection(BaseRuntime, ABC):
    """Common metadata and locally bound contents of a manifest node."""

    manifest: CollectionManifest | DatasetManifest
    resources: Mapping[str, Resource] = field(init=False, repr=False)
    tables: Mapping[str, Table] = field(init=False, repr=False)
    collections: Mapping[str, Collection] = field(init=False, repr=False)

    def _bind_contents(
        self,
        *,
        dataset: Dataset,
    ) -> None:
        self._set_mapping(
            "resources",
            {
                name: dataset._resource_type(manifest, name=name, parent=self)
                for name, manifest in self.manifest.resources.items()
            },
        )
        tables = {
            name: TableManifest(
                resource=name,
                reader=resource.suffix.lower()[1:],  # pyright: ignore[reportOptionalMemberAccess]
            )
            for name, resource in self.resources.items()
            if resource.resource_type == "file"
            and (resource.suffix or "").lower() in (".csv", ".parquet")
        }
        tables.update(self.manifest.tables)
        self._set_mapping(
            "tables",
            {
                name: dataset._table_type(manifest, name=name, parent=self)
                for name, manifest in tables.items()
            },
        )
        collections = {}
        for name, manifest in self.manifest.collections.items():
            if not isinstance(manifest, CollectionManifest):
                raise TypeError(
                    f"Collection {name!r} references unresolved manifest "
                    f"{manifest.manifest!r}; use fhrs.load() or fhrs.manifest.load() "
                    "to resolve references before constructing runtime objects"
                )
            collections[name] = dataset._collection_type(
                manifest, name=name, parent=self
            )
        self._set_mapping("collections", collections)

    @property
    def title(self) -> str | None:
        return self.manifest.title

    @property
    def description(self) -> str | None:
        return self.manifest.description

    def resource(self, name: str) -> Resource | ResourceMember:
        """Resolve a relative resource path and optional member selector after ``#``."""
        resource_path, separator, member = name.partition("#")
        node, resource_name = self._lookup_parent(resource_path)
        resource = node.resources[resource_name]
        return resource.member(member) if separator else resource

    def table(self, name: str) -> Table:
        """Look up a table by name or a collection path relative to this node."""
        node, table_name = self._lookup_parent(name)
        return node.tables[table_name]

    def _lookup_parent(self, path: str) -> tuple[BaseCollection, str]:
        """Traverse collection segments and return the owning node and final name."""
        parts = path.split("/")
        node = self
        for part in parts[:-1]:
            node = node.collection(part)
        return node, parts[-1]

    def collection(self, name: str) -> Collection:
        return self.collections[name]
