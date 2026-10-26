"""Version references, index contents, and dataset version declarations."""

from pydantic import BaseModel, Field, RootModel

from ._base import RelativePath
from .collection import ManifestReference


class VersionReference(ManifestReference):
    """A version manifest path relative to the file containing this reference."""


class VersionIndex(RootModel[dict[str, VersionReference]]):
    """Version identifiers mapped to their manifest references."""

    root: dict[str, VersionReference] = Field(default_factory=dict)


class Versions(BaseModel, extra="forbid"):
    """Inline version entries and paths to external version indexes."""

    entries: VersionIndex = Field(default_factory=VersionIndex)
    indexes: list[RelativePath] = Field(default_factory=list)
