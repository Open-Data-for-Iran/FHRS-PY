"""Logical tabular views of manifest resources."""

from typing import Annotated

from pydantic import BaseModel, Field


class Table(BaseModel, extra="forbid"):
    """One or more ordered resources interpreted by a named reader."""

    resource: str | list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    reader: str = Field(
        min_length=1, description="Reader name, such as csv, parquet, or excel."
    )
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
