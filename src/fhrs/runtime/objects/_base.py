"""Shared bases for runtime objects and collection binding."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from ...manifest.models.collection import Collection as CollectionManifest
from ...manifest.models.collection import ManifestReference

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


@dataclass(frozen=True, slots=True, eq=False)
class BaseCollection(BaseRuntime, ABC):
    """Common metadata and locally bound contents of a manifest node."""

    manifest: CollectionManifest
    resources: Mapping[str, Resource] = field(init=False, repr=False)
    tables: Mapping[str, Table] = field(init=False, repr=False)
    collections: Mapping[str, Collection | ManifestReference] = field(
        init=False, repr=False
    )

    @abstractmethod
    def __post_init__(self) -> None:
        """Bind contents using the concrete node's ownership context."""

    def _bind_contents(
        self,
        *,
        dataset: Dataset,
    ) -> None:
        from .collection import Collection
        from .resource import Resource
        from .table import Table

        self._setattr(
            "resources",
            MappingProxyType(
                {
                    name: Resource(manifest, name=name, dataset=dataset, parent=self)
                    for name, manifest in self.manifest.resources.items()
                }
            ),
        )
        self._setattr(
            "tables",
            MappingProxyType(
                {
                    name: Table(
                        manifest,
                        name=name,
                        resources=[
                            self.resource(reference)
                            for reference in (
                                [manifest.resource]
                                if isinstance(manifest.resource, str)
                                else manifest.resource
                            )
                        ],
                    )
                    for name, manifest in self.manifest.tables.items()
                }
            ),
        )
        self._setattr(
            "collections",
            MappingProxyType(
                {
                    name: manifest
                    if isinstance(manifest, ManifestReference)
                    else Collection(manifest, name=name, dataset=dataset, parent=self)
                    for name, manifest in self.manifest.collections.items()
                }
            ),
        )

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
            child = node.collection(part)
            if isinstance(child, ManifestReference):
                raise TypeError(f"Cannot traverse unresolved collection {part!r}")
            node = child
        return node, parts[-1]

    def collection(self, name: str) -> Collection | ManifestReference:
        return self.collections[name]
