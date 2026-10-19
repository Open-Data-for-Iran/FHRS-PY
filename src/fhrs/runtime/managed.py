"""Runtime subclasses reserved for dataset maintenance operations.

These currently inherit all behavior unchanged. Sources remain shared runtime
addresses; the dataset selects managed types for its bound objects.
"""

from __future__ import annotations

from typing import cast

from .objects import Collection, Dataset, Resource, ResourceMember, Storage, Table
from .objects.storage import _WorkingStorage


class ManagedResourceMember(ResourceMember):
    """A resource member in a managed dataset."""

    __slots__ = ()

    @property
    def dataset(self) -> ManagedDataset:
        return cast(ManagedDataset, super().dataset)

    @property
    def parent(self) -> ManagedDataset | ManagedCollection:
        return cast(ManagedDataset | ManagedCollection, super().parent)


class ManagedResource(Resource):
    """A resource in a managed dataset."""

    __slots__ = ()
    _member_type = ManagedResourceMember

    def member(self, name: str) -> ManagedResourceMember:
        return cast(ManagedResourceMember, super().member(name))

    @property
    def dataset(self) -> ManagedDataset:
        return cast(ManagedDataset, super().dataset)


class ManagedTable(Table):
    """A table in a managed dataset."""

    __slots__ = ()

    @property
    def dataset(self) -> ManagedDataset:
        return cast(ManagedDataset, super().dataset)


class ManagedStorage(Storage):
    """A storage in a managed dataset."""

    __slots__ = ()


class _ManagedWorkingStorage(_WorkingStorage, ManagedStorage):
    """Managed storage rooted at the dataset's working directory."""

    __slots__ = ()


class ManagedCollection(Collection):
    """A collection in a managed dataset."""

    __slots__ = ()

    @property
    def dataset(self) -> ManagedDataset:
        return cast(ManagedDataset, super().dataset)

    def resource(self, name: str) -> ManagedResource | ManagedResourceMember:
        return cast(ManagedResource | ManagedResourceMember, super().resource(name))

    def table(self, name: str) -> ManagedTable:
        return cast(ManagedTable, super().table(name))

    def collection(self, name: str) -> ManagedCollection:
        return cast(ManagedCollection, super().collection(name))


class ManagedDataset(Dataset):
    """A dataset that binds managed subclasses throughout its contents."""

    __slots__ = ()
    _collection_type = ManagedCollection
    _resource_type = ManagedResource
    _table_type = ManagedTable
    _storage_type = ManagedStorage
    _working_storage_type = _ManagedWorkingStorage

    def resource(self, name: str) -> ManagedResource | ManagedResourceMember:
        return cast(ManagedResource | ManagedResourceMember, super().resource(name))

    def table(self, name: str) -> ManagedTable:
        return cast(ManagedTable, super().table(name))

    def collection(self, name: str) -> ManagedCollection:
        return cast(ManagedCollection, super().collection(name))

    def storage(self, name: str) -> ManagedStorage:
        return cast(ManagedStorage, super().storage(name))
