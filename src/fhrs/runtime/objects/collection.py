"""Collection context and its named runtime contents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ._base import BaseCollection
from .source import Source

if TYPE_CHECKING:
    from .dataset import Dataset


@dataclass(frozen=True, slots=True, eq=False)
class Collection(BaseCollection):
    """A collection bound to its parent, dataset, and defining manifest source."""

    name: str
    dataset: Dataset = field(repr=False)
    parent: BaseCollection = field(repr=False)
    source: Source | None = None

    def __post_init__(self) -> None:
        if self.source is None:
            storage = getattr(self.manifest, "_storage", None)
            parent_storage = getattr(self.parent.manifest, "_storage", None)
            source = (
                self.dataset.source
                if storage is None or storage is parent_storage
                else Source(**storage)
            )
            self._setattr("source", source)
        self._bind_contents(dataset=self.dataset)
