"""Dataset roots."""

from typing import Literal

from pydantic import Field

from .collection import BaseCollection
from .storage import BaseStorage, EmbeddedStorage, HTTPStorage, S3Storage


class Dataset(BaseCollection):
    """A named dataset containing resources, tables, and collections."""

    fhrs_version: Literal["0.1"] = "0.1"
    storages: dict[str, S3Storage | EmbeddedStorage | HTTPStorage | BaseStorage] = (
        Field(default_factory=dict)
    )
