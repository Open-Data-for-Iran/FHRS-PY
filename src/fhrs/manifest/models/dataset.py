"""Dataset roots."""

from pathlib import Path
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, Field, model_validator

from ._base import Name
from .collection import BaseCollection
from .storage import BaseStorage, EmbeddedStorage, HTTPStorage, S3Storage


class DumpOptions(BaseModel, extra="forbid"):
    """Default manifest writing options, excluded from dataset serialization."""

    destination: str | Path = "."
    format: Literal["yaml", "json"] = "yaml"
    layout: dict[str, str] | None = None
    storage_options: dict[str, Any] | None = None


class Dataset(BaseCollection):
    """A named dataset containing resources, tables, and collections."""

    # Explicit dump order places identity before inherited collection contents.
    _dump_field_order: ClassVar[tuple[str, ...]] = (
        "fhrs_version",
        "name",
        "title",
        "description",
        "schema_version",
        "release",
        "status",
        "storages",
        "resources",
        "tables",
        "collections",
    )

    fhrs_version: Literal["0.1"] = "0.1"
    name: Name
    schema_version: str | None = Field(default=None, min_length=1, pattern=r"\S")
    release: str | None = Field(default=None, min_length=1, pattern=r"\S")
    status: Literal["in_development", "published"] = "in_development"
    dump_options: DumpOptions = Field(default_factory=DumpOptions, exclude=True)
    storages: dict[str, S3Storage | EmbeddedStorage | HTTPStorage | BaseStorage] = (
        Field(default_factory=dict)
    )

    @model_validator(mode="after")
    def check_storage_names(self) -> Self:
        if "working" in self.storages:
            raise ValueError(
                "Storage name 'working' is reserved for runtime working storage; "
                "use working_directory to configure its location"
            )
        return self
