"""Named tables bound to their backing runtime resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, overload

from ...manifest.models.table import Table as TableManifest
from ._base import BaseRuntime
from .resource import Resource

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    from ._base import BaseCollection
    from .dataset import Dataset


@dataclass(frozen=True, slots=True)
class Table(BaseRuntime):
    """A table declaration bound to ordered resources in the same manifest node."""

    manifest: TableManifest
    name: str
    resources: list[Resource] = field(repr=False)

    def __post_init__(self) -> None:
        if not self.resources:
            raise ValueError("Table requires at least one resource")

    @property
    def reader(self) -> str:
        return self.manifest.reader

    @property
    def title(self) -> str | None:
        return self.manifest.title

    @property
    def dataset(self) -> Dataset:
        return self.resources[0].dataset

    @property
    def parent(self) -> BaseCollection:
        return self.resources[0].parent

    @overload
    def load(
        self,
        backend: Literal["pandas"] = "pandas",
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame: ...

    @overload
    def load(
        self,
        backend: Literal["polars"],
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame: ...

    def load(
        self,
        backend: Literal["pandas", "polars"] = "pandas",
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame | pl.DataFrame:
        """Load a DataFrame using the table reader and optional named source.

        Planned readers are csv, parquet, and excel (Excel workbooks).
        Loading is not implemented yet.

        Defaults to pandas. Source selects a location name, then a storage name;
        omission uses declared mirror order. Keyword arguments configure the reader.
        """
        raise NotImplementedError("Table loading is not implemented yet")
