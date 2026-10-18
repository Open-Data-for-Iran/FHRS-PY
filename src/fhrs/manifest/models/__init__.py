"""Manifest declarations and loading."""

from .collection import BaseCollection, Collection, ManifestReference
from .dataset import Dataset
from .resource import Checksums, Location, Resource
from .storage import BaseStorage, EmbeddedStorage, HTTPStorage, S3Storage
from .table import Table

__all__ = [
    "BaseCollection",
    "BaseStorage",
    "Checksums",
    "Collection",
    "Dataset",
    "EmbeddedStorage",
    "HTTPStorage",
    "Location",
    "ManifestReference",
    "Resource",
    "S3Storage",
    "Table",
]
