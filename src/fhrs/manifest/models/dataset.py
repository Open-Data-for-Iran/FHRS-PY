"""Dataset roots."""

from pydantic import Field

from .collection import BaseCollection
from .storage import BaseStorage, HTTPStorage, LocalStorage, S3Storage


class Dataset(BaseCollection):
    """A named dataset containing resources, tables, and collections."""

    storages: dict[str, S3Storage | LocalStorage | HTTPStorage | BaseStorage] = Field(
        default_factory=dict
    )
