"""Runtime addresses of datasets, collection manifests, and resource contents."""

import posixpath
from dataclasses import dataclass, field
from io import TextIOWrapper
from typing import Any

import fsspec
from fsspec import AbstractFileSystem
from fsspec.spec import AbstractBufferedFile

from ...manifest.loader import _relative_urlpath
from ._base import BaseRuntime


@dataclass(frozen=True, slots=True)
class Source(BaseRuntime):
    """A manifest or resource address together with its filesystem options."""

    urlpath: str
    storage_options: dict[str, Any] = field(default_factory=dict)
    _fs_path: tuple[AbstractFileSystem, str] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.urlpath:
            raise ValueError("Source urlpath must be nonempty")

    def _get_fs_path(self) -> tuple[AbstractFileSystem, str]:
        fs_path = self._fs_path
        if fs_path is None:
            fs_path = fsspec.url_to_fs(self.urlpath, **self.storage_options)
            self._setattr("_fs_path", fs_path)
        return fs_path

    def to_fsspec(self) -> dict[str, Any]:
        """Return keyword arguments for ``fsspec.open`` without opening the file."""
        return {**self.storage_options, "urlpath": self.urlpath}

    @property
    def protocol(self) -> str:
        """The filesystem selected by the URL and explicit storage options."""
        return (
            self.storage_options.get("protocol")
            or fsspec.core.split_protocol(self.urlpath)[0]
            or "file"
        )

    def resolve(self, path: str) -> Source:
        """Resolve a filesystem path beside this source, preserving its connection."""
        cls = fsspec.get_filesystem_class(self.protocol)
        fs_path = cls._strip_protocol(self.urlpath)
        if "://" in fs_path:
            urlpath = _relative_urlpath(fs_path, path)
        else:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(fs_path), path)
            )
            prefix = (
                self.urlpath[: -len(fs_path)]
                if fs_path and self.urlpath.endswith(fs_path)
                else f"{self.protocol}://"
            )
            urlpath = prefix + resolved
        return Source(urlpath, storage_options=dict(self.storage_options))

    @property
    def filesystem(self) -> AbstractFileSystem:
        """Filesystem initialized on first access and reused by this source."""
        return self._get_fs_path()[0]

    @property
    def path(self) -> str:
        """Backend path resolved together with the filesystem on first access."""
        return self._get_fs_path()[1]

    def glob(self) -> tuple[Source, ...]:
        """Expand this address as a glob into sorted file sources; no matches gives ()."""
        matches = self.filesystem.glob(self.path, detail=True)
        assert isinstance(matches, dict)
        return tuple(
            self.resolve(posixpath.relpath(path, posixpath.dirname(self.path) or "."))
            for path, info in sorted(matches.items())
            if info["type"] == "file"
        )

    def open(
        self, mode: str = "rb", **kwargs: Any
    ) -> TextIOWrapper[Any] | AbstractBufferedFile:
        """Open this source using its cached filesystem; defaults to binary reading."""
        return self.filesystem.open(self.path, mode=mode, **kwargs)

    def exists(self) -> bool:
        """Check whether this address exists on its filesystem."""
        return self.filesystem.exists(self.path)
