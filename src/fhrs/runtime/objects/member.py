"""Named file patterns bound to directory resources and their mirrors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ._base import BaseRuntime
from .source import Source

if TYPE_CHECKING:
    from ._base import BaseCollection
    from .dataset import Dataset
    from .resource import Resource


@dataclass(frozen=True, slots=True)
class ResourceMember(BaseRuntime):
    """A named glob within a directory, with one source per resource mirror."""

    name: str
    pattern: str
    resource: Resource = field(repr=False, compare=False)
    sources: tuple[Source, ...] = field(init=False)

    def __post_init__(self) -> None:
        """Bind pattern addresses without listing directories or opening files."""
        if self.resource.resource_type != "directory":
            raise ValueError("Resource members require a directory resource")
        if not self.name or not self.pattern:
            raise ValueError("Member name and pattern must be nonempty")
        if (
            self.pattern.startswith("/")
            or ".." in self.pattern.split("/")
            or ":" in self.pattern.split("/", 1)[0]
            or "\\" in self.pattern
            or "\0" in self.pattern
        ):
            raise ValueError(
                f"Member pattern must stay inside its directory: {self.pattern!r}"
            )
        self._setattr(
            "sources",
            tuple(
                Source(
                    source.urlpath
                    + ("" if source.urlpath.endswith("/") else "/")
                    + self.pattern,
                    dict(source.storage_options),
                )
                for source in self.resource.sources
            ),
        )

    @property
    def dataset(self) -> Dataset:
        """The dataset owning this member's resource."""
        return self.resource.dataset

    @property
    def parent(self) -> BaseCollection:
        """The collection owning this member's resource."""
        return self.resource.parent

    def source(self, name: str | None = None) -> Source:
        """Select a pattern source using the resource's location/storage lookup."""
        source = self.resource.source(name)
        if source in self.resource.sources:
            return self.sources[self.resource.sources.index(source)]
        return Source(
            source.urlpath.rstrip("/") + "/" + self.pattern,
            dict(source.storage_options),
        )

    def files(self, source: str | None = None) -> tuple[Source, ...]:
        """List sorted files from the first location, or working data if none exist.

        Matches are refreshed on every call; no matches returns an empty tuple.
        Filesystem errors propagate without falling back to another mirror.
        """
        return self.source(source).glob()
