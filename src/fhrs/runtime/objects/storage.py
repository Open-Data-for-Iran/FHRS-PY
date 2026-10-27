"""Named storage declarations bound to their dataset."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import fsspec
from fsspec import AbstractFileSystem

from ...manifest.models.storage import BaseStorage as StorageManifest
from ...manifest.models.storage import EmbeddedStorage, HTTPStorage
from .._paths import _location_path, _validate_relative_path
from ._base import BaseRuntime
from .source import Source

if TYPE_CHECKING:
    from .dataset import Dataset


@dataclass(frozen=True, slots=True)
class Storage(BaseRuntime):
    """A named storage with an on-demand fsspec filesystem."""

    manifest: StorageManifest
    name: str
    dataset: Dataset | None = field(default=None, repr=False, compare=False)

    @property
    def protocol(self) -> str:
        if isinstance(self.manifest, EmbeddedStorage):
            return self._embedded_source().protocol
        return self.manifest.protocol

    @property
    def base_path(self) -> str:
        return self.manifest.base_path

    def filesystem(self) -> AbstractFileSystem:
        """Create the filesystem using the manifest's backend mapping."""
        if isinstance(self.manifest, EmbeddedStorage):
            source = self._embedded_source()
            return fsspec.url_to_fs(source.urlpath, **source.storage_options)[0]
        return fsspec.filesystem(**self.manifest.to_fsspec())

    def _embedded_source(self) -> Source:
        if self.dataset is None or self.dataset.source is None:
            raise ValueError(
                f"Embedded storage {self.name!r} requires its dataset source"
            )
        source = self.dataset.source
        return Source(
            source.urlpath,
            {
                **source.storage_options,
                **self.manifest.storage_options,
                "protocol": source.protocol,
            },
        )

    def resolve(self, uri: str) -> Source:
        """Resolve a scope-relative URI using its configured backend or dataset source."""
        if isinstance(self.manifest, EmbeddedStorage):
            source = self._embedded_source()
            path = _location_path(uri, source.protocol, scoped=True)
            base = _validate_relative_path(self.base_path or ".")
            return source.resolve(posixpath.join(base, path))
        path = _location_path(uri, self.protocol, scoped=True)
        options = self.manifest.to_fsspec()
        protocol = options.pop("protocol")
        if isinstance(self.manifest, HTTPStorage):
            urlpath = f"{self.base_path.rstrip('/')}/{path}"
        else:
            urlpath = f"{protocol}://{posixpath.join(self.base_path, path)}"
        return Source(urlpath, storage_options=options)


class LocalStorage(Storage):
    """Local storage rooted at the runtime dataset's local directory."""

    __slots__ = ()

    @property
    def base_path(self) -> str:
        assert self.dataset is not None
        return Path(self.dataset.local_directory).as_posix()

    def resolve(self, uri: str) -> Source:
        root = Path(self.base_path)
        path = (root / uri).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Local resource path escapes its directory: {uri!r}")
        return Source(path.as_posix())
