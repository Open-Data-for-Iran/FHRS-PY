"""Named tables bound to their backing runtime resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, overload

from ...manifest.models.table import Table as TableManifest
from ._base import BaseRuntime
from .member import ResourceMember
from .resource import Resource

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    from ._base import BaseCollection
    from .dataset import Dataset


@dataclass(frozen=True, slots=True)
class Table(BaseRuntime):
    """A table bound to ordered resources or members in the same manifest node."""

    manifest: TableManifest
    name: str
    parent: BaseCollection = field(repr=False, compare=False)
    resources: list[Resource | ResourceMember] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        references = self.manifest.resource
        self._setattr(
            "resources",
            [
                self.parent.resource(reference)
                for reference in (
                    [references] if isinstance(references, str) else references
                )
            ],
        )
        if not self.resources:
            raise ValueError("Table requires at least one resource")

    @property
    def reader(self) -> str:
        return self.manifest.reader

    @property
    def title(self) -> str | None:
        return self.manifest.title

    @property
    def description(self) -> str | None:
        return self.manifest.description

    @property
    def dataset(self) -> Dataset:
        """The dataset owning this table, derived from its parent."""
        from .collection import Collection
        from .dataset import Dataset

        if isinstance(self.parent, Dataset):
            return self.parent
        assert isinstance(self.parent, Collection)
        return self.parent.dataset

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

        Defaults to pandas. Source selects a location name, then a storage name;
        omission uses the first declared mirror, or local data when none exist.
        Keyword arguments configure the
        registered reader. Results are concatenated in resource reference order.
        """
        from ..readers import READERS

        if backend not in ("pandas", "polars"):
            raise ValueError(f"Unsupported table backend: {backend!r}")
        try:
            reader = READERS[self.reader]
        except KeyError:
            raise ValueError(f"Unknown table reader: {self.reader!r}") from None

        if backend == "pandas":
            import pandas as pd

            frames = [
                reader.read_pandas(resource, source=source, **kwargs)
                for resource in self.resources
            ]
            return (
                frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
            )

        import polars as pl

        frames = [
            reader.read_polars(resource, source=source, **kwargs)
            for resource in self.resources
        ]
        return frames[0] if len(frames) == 1 else pl.concat(frames)
