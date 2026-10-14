"""Logical tabular views of manifest resources."""

from pydantic import BaseModel, Field


class Table(BaseModel, extra="forbid"):
    """A resource interpreted by a named reader."""

    resource: str = Field(min_length=1)
    reader: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
