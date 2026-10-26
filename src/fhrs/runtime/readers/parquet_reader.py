"""Parquet table reading."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..objects.member import ResourceMember
from ..objects.resource import Resource
from ..objects.source import Source
from ._base import BaseReader

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl


def _parquet_files(
    resource: Resource | ResourceMember, source: str | None
) -> tuple[Source, ...]:
    if isinstance(resource, ResourceMember):
        files = resource.files(source=source)
        if not files:
            raise FileNotFoundError(
                f"Parquet member {resource.name!r} matched no files"
            )
        return files
    if resource.resource_type == "directory":
        raise ValueError("Parquet directory resources require a member selecting files")
    if source is None and not resource.sources:
        raise ValueError(f"Resource {resource.key!r} has no locations")
    return (resource.sources[0] if source is None else resource.source(source),)


class ParquetReader(BaseReader):
    """Read Parquet files from one mirror, concatenating member matches in path order."""

    def read_pandas(
        self,
        resource: Resource | ResourceMember,
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Read eagerly with pandas; multiple files receive a fresh row index."""
        import pandas as pd

        frames = []
        for file in _parquet_files(resource, source):
            with file.open() as stream:
                frames.append(pd.read_parquet(stream, **kwargs))
        return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)

    def read_polars(
        self,
        resource: Resource | ResourceMember,
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Read eagerly with Polars, using its default vertical concatenation."""
        import polars as pl

        frames = []
        for file in _parquet_files(resource, source):
            with file.open() as stream:
                frames.append(pl.read_parquet(stream, **kwargs))
        return frames[0] if len(frames) == 1 else pl.concat(frames)
