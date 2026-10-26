"""Manifest declarations and loading."""

from .collection import BaseCollection, Collection, ManifestReference
from .dataset import Dataset, DumpOptions
from .resource import Checksums, Location, Resource
from .storage import BaseStorage, EmbeddedStorage, HTTPStorage, S3Storage
from .table import Table
from .version import VersionIndex, VersionReference, Versions

__all__ = [
    "BaseCollection",
    "BaseStorage",
    "Checksums",
    "Collection",
    "Dataset",
    "DumpOptions",
    "EmbeddedStorage",
    "HTTPStorage",
    "Location",
    "ManifestReference",
    "Resource",
    "S3Storage",
    "Table",
    "VersionIndex",
    "VersionReference",
    "Versions",
]
