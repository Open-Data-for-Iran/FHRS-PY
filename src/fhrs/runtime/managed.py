"""Runtime subclasses supporting dataset maintenance operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, cast

from .._utils.put import put_directory, put_file
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

    def put(
        self,
        data: str | os.PathLike[str] | bytes | BinaryIO,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Place file or directory content in working storage; return its path.

        Paths are opened in binary mode. Caller-owned binary streams are read
        from their current position and left open. Existing files require
        overwrite=True. Directory resources accept directory paths only, and
        overwrite replaces their entire contents. Copies are staged first;
        directory publication failures restore the original when possible.
        Manifest declarations are never modified.
        """
        destination = Path(
            self.dataset.storage("working")
            .resolve(self.key + (self.suffix or ""))
            .urlpath
        )
        if not overwrite and destination.exists():
            raise FileExistsError(destination)

        if self.resource_type == "directory":
            if not isinstance(data, (str, os.PathLike)):
                raise TypeError("Directory resources require a local directory path")
            return put_directory(data, destination, overwrite=overwrite)

        return put_file(data, destination, overwrite=overwrite)

    def add(
        self,
        path: str,
        data: str | os.PathLike[str] | bytes | BinaryIO,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write one file inside a directory resource's working storage.

        Accept a relative file path using forward slashes, without glob patterns
        or traversal. Create parent directories and preserve other files.
        Inputs and overwrite behavior match put(); manifests are unchanged.
        """
        if self.resource_type != "directory":
            raise TypeError("add() requires a directory resource")
        return put_file(data, self._directory_file_path(path), overwrite=overwrite)

    def remove(self, path: str) -> None:
        """Remove one file from a directory resource's working storage.

        Use the same relative paths as add(). Missing files raise
        FileNotFoundError; directories raise IsADirectoryError. Other files,
        parent directories, and manifest declarations are preserved.
        """
        if self.resource_type != "directory":
            raise TypeError("remove() requires a directory resource")
        destination = self._directory_file_path(path)
        if destination.is_dir():
            raise IsADirectoryError(destination)
        destination.unlink()

    def _directory_file_path(self, path: str) -> Path:
        """Validate a single file path within this resource's working directory."""
        if (
            not path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or any(char in path for char in "\\:\0*?[]")
        ):
            raise ValueError(
                f"Expected a relative file path inside the resource: {path!r}"
            )
        directory = Path(self.source("working").urlpath).resolve()
        destination = directory / path
        if not destination.resolve().is_relative_to(directory):
            raise ValueError(f"File path escapes its directory resource: {path!r}")
        return destination


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
