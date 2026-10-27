"""Named resources built from manifest declarations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from ...manifest.models.resource import Checksums, Location
from ...manifest.models.resource import Resource as ResourceManifest
from .._paths import _location_path
from ._base import BaseRuntime
from .member import ResourceMember
from .source import Source

if TYPE_CHECKING:
    from ._base import BaseCollection
    from .dataset import Dataset


@dataclass(frozen=True, slots=True)
class Resource(BaseRuntime):
    """A named resource whose metadata comes from its validated manifest."""

    _member_type: ClassVar[type[ResourceMember]] = ResourceMember

    manifest: ResourceManifest
    name: str
    parent: BaseCollection = field(repr=False, compare=False)
    sources: tuple[Source, ...] = field(init=False)
    members: Mapping[str, ResourceMember] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Bind sources in location order without accessing their contents."""
        resolved = []
        for location in self.locations:
            if location.storage is not None:
                address = self.dataset.storage(location.storage).resolve(location.uri)
            elif "://" in location.uri:
                address = Source(location.uri)
            else:
                source = self.dataset.source
                if source is None:
                    raise ValueError(
                        f"Resource {self.name!r} requires its dataset source"
                    )
                path = _location_path(location.uri, source.protocol)
                address = source.resolve(path)
            resolved.append(address)
        self._setattr("sources", tuple(resolved))
        self._set_mapping(
            "members",
            {
                name: self._member_type(name, pattern, self)
                for name, pattern in (self.manifest.members or {}).items()
            },
        )

    @property
    def dataset(self) -> Dataset:
        """The dataset owning this resource, derived from its parent."""
        from .collection import Collection
        from .dataset import Dataset

        if isinstance(self.parent, Dataset):
            return self.parent
        assert isinstance(self.parent, Collection)
        return self.parent.dataset

    def member(self, name: str) -> ResourceMember:
        """Look up a declared member or bind an inline ``member:pattern``.

        Accepts the selector after ``#`` in a resource address. Inline members
        are temporary and neither modify declarations nor expand their patterns.
        """
        if name.startswith("member:"):
            pattern = name.removeprefix("member:")
            return self._member_type(pattern, pattern, self)
        return self.members[name]

    @property
    def key(self) -> str:
        """Resource lookup path relative to its dataset, independent of locations."""
        from .collection import Collection

        parts = [self.name]
        node = self.parent
        while node is not self.dataset:
            assert isinstance(node, Collection)
            parts.append(node.name)
            node = node.parent
        return "/".join(reversed(parts))

    @property
    def title(self) -> str | None:
        return self.manifest.title

    @property
    def description(self) -> str | None:
        return self.manifest.description

    @property
    def resource_type(self) -> Literal["file", "directory"]:
        return self.manifest.type

    @property
    def locations(self) -> tuple[Location, ...]:
        return tuple(self.manifest.locations)

    @property
    def size(self) -> int | None:
        """Declared complete file size in bytes, if supplied."""
        return self.manifest.size

    @property
    def suffix(self) -> str | None:
        """Preferred file extension, including its leading dot, if declared."""
        return self.manifest.suffix

    @property
    def checksums(self) -> Checksums | None:
        return self.manifest.checksums

    @property
    def workspace_path(self) -> Path:
        """Editable path within the local workspace, without creating any files."""
        root = Path(self.dataset.local_directory) / "workspace"
        if root.resolve() != root:
            raise ValueError("Workspace root must not redirect to another directory")
        path = (root / (self.key + (self.suffix or ""))).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Resource path escapes its workspace: {self.key!r}")
        return path

    def source(self, name: str | None = None) -> Source:
        """Select a named source, defaulting to the first location or workspace."""
        if name is None:
            if self.sources:
                return self.sources[0]
            name = "local"
        for location, source in zip(self.locations, self.sources, strict=True):
            if location.name == name:
                return source
        for location, source in zip(self.locations, self.sources, strict=True):
            if location.storage == name:
                return source
        if name == "local":
            return Source(self.workspace_path.as_posix())
        raise KeyError(name)
