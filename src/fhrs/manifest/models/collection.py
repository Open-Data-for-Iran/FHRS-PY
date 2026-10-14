"""Nested groups of resources and tables."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from ._base import RelativePath
from .resource import Resource
from .table import Table


class ManifestReference(BaseModel, extra="forbid"):
    """A manifest path relative to the file containing this reference."""

    manifest: RelativePath


class BaseCollection(BaseModel, extra="forbid"):
    """Shared declaration for named groups and dataset roots."""

    _storage: dict[str, Any] = PrivateAttr()

    fhrs_version: Literal["0.1"] = "0.1"
    name: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    resources: dict[str, Resource] = Field(default_factory=dict)
    tables: dict[str, Table] = Field(default_factory=dict)
    collections: dict[str, Collection | ManifestReference] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_table_resources(self) -> Self:
        for name, table in self.tables.items():
            if table.resource not in self.resources:
                raise ValueError(
                    f"Table {name!r} references unknown local resource {table.resource!r}"
                )
        return self


class Collection(BaseCollection):
    """A logical group with an optional name and child collections."""

    name: str | None = Field(default=None, min_length=1)


BaseCollection.model_rebuild()
