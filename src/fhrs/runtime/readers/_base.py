"""Shared interface for table format readers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    from ..objects.member import ResourceMember
    from ..objects.resource import Resource


class BaseReader(ABC):
    """Read one resource or member using format-specific input handling.

    Source selects a location name, then a storage name. Format readers own
    file expansion and directory handling. Constructing a reader performs no I/O.
    """

    @abstractmethod
    def read_pandas(
        self,
        resource: Resource | ResourceMember,
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Read from one mirror into pandas, forwarding pandas reader options."""
        ...

    @abstractmethod
    def read_polars(
        self,
        resource: Resource | ResourceMember,
        *,
        source: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Read from one mirror into Polars, forwarding Polars reader options."""
        ...
