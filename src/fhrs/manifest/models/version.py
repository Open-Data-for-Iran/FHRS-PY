"""Version references, index contents, and dataset version declarations."""

from typing import Any

from pydantic import BaseModel, Field, RootModel

from ._base import RelativePath


class VersionReference(BaseModel, extra="forbid"):
    """A version manifest path or URL with optional fsspec connection options."""

    manifest: str = Field(min_length=1, pattern=r"\S")
    storage_options: dict[str, Any] | None = None


class VersionIndex(RootModel[dict[str, VersionReference]]):
    """Version identifiers mapped to their manifest references."""

    root: dict[str, VersionReference] = Field(default_factory=dict)


class Versions(BaseModel, extra="forbid"):
    """Inline version entries and paths to external version indexes."""

    entries: VersionIndex = Field(default_factory=VersionIndex)
    indexes: list[RelativePath] = Field(default_factory=list)
