"""Dataset roots."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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

    fhrs_version: Literal["0.1"] = "0.1"
    dump_options: DumpOptions = Field(default_factory=DumpOptions, exclude=True)
    storages: dict[str, S3Storage | EmbeddedStorage | HTTPStorage | BaseStorage] = (
        Field(default_factory=dict)
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError("Dataset name must not contain path components")
        return name
