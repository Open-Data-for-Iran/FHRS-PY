"""Read and validate dataset and collection declarations."""

import json
import os
import posixpath
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import fsspec
from ruamel.yaml import YAML

from .discovery import discover
from .models.collection import BaseCollection, Collection
from .models.dataset import Dataset


def load(
    urlpath: str | os.PathLike[str],
    *,
    storage_options: dict[str, Any] | None = None,
) -> Dataset:
    """Load a manifest file or discover one in a directory through fsspec.

    Returns a validated declaration with all collection references loaded.
    """
    urlpath = discover(urlpath, storage_options=storage_options)
    return _load_dataset(urlpath, storage_options=storage_options, resolve=True)


def _load_dataset(
    urlpath: str,
    *,
    storage_options: dict[str, Any] | None,
    resolve: bool = False,
) -> Dataset:
    dataset = Dataset.model_validate(_read_manifest(urlpath, storage_options))
    dataset._storage = {
        "urlpath": urlpath,
        "storage_options": dict(storage_options or {}),
    }
    if resolve:
        dataset = _resolve_collection(dataset)
    return dataset


def _load_internal_collection(
    urlpath: str,
    *,
    storage_options: dict[str, Any] | None,
) -> Collection:
    collection = Collection.model_validate(_read_manifest(urlpath, storage_options))
    collection._storage = {
        "urlpath": urlpath,
        "storage_options": dict(storage_options or {}),
    }
    return collection


def _file_key(urlpath: str, options: dict[str, Any]) -> str:
    """Identify a manifest file for detecting loops in the active reference chain."""
    filesystem, fs_path = fsspec.url_to_fs(urlpath, **options)
    if filesystem.protocol == "file" or "file" in filesystem.protocol:
        return os.path.normcase(os.path.realpath(fs_path))
    return posixpath.normpath(fs_path)


def _resolve_collection[T: BaseCollection](collection: T) -> T:
    """Resolve all descendants in place, rejecting loops between manifest files."""
    active: dict[str, str] = {}

    def resolve(node: BaseCollection, *, inline: bool = False) -> None:
        if not node.collections:
            return
        storage = node._storage
        urlpath = storage["urlpath"]
        options = storage["storage_options"]
        key = None if inline else _file_key(urlpath, options)
        if key is not None:
            if key in active:
                chain = " -> ".join([*active.values(), urlpath])
                raise ValueError(f"Collection manifest loop: {chain}")
            active[key] = urlpath
        try:
            for child in node.collections.values():
                if isinstance(child, BaseCollection):
                    continue
                child_urlpath = _relative_urlpath(urlpath, child.manifest)
                if _file_key(child_urlpath, options) in active:
                    chain = " -> ".join([*active.values(), child_urlpath])
                    raise ValueError(f"Collection manifest loop: {chain}")
            _resolve_collection_child(node)
            for child in node.collections.values():
                assert isinstance(child, BaseCollection)
                resolve(child, inline=child._storage is storage)
        finally:
            if key is not None:
                del active[key]

    resolve(collection)
    return collection


def _resolve_collection_child[T: BaseCollection](collection: T) -> T:
    """Resolve immediate file references in place and return the same collection."""
    for name, child_collection in collection.collections.items():
        if isinstance(child_collection, BaseCollection):
            if not hasattr(child_collection, "_storage"):
                child_collection._storage = collection._storage
            continue
        urlpath = _relative_urlpath(
            collection._storage["urlpath"], child_collection.manifest
        )
        collection.collections[name] = _load_internal_collection(
            urlpath, storage_options=collection._storage["storage_options"]
        )
    return collection


def _relative_urlpath(urlpath: str, relative: str) -> str:
    if "://" in urlpath:
        parts = urlsplit(urlpath)
        path = posixpath.normpath(
            posixpath.join(posixpath.dirname(parts.path), relative)
        )
        return f"{parts.scheme}://{parts.netloc}{path}"
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(urlpath.replace("\\", "/")), relative)
    )


def _read_manifest(
    urlpath: str,
    storage_options: dict[str, Any] | None = None,
) -> Any:
    filesystem, fs_path = fsspec.url_to_fs(urlpath, **(storage_options or {}))
    suffix = Path(urlsplit(fs_path).path).suffix.lower()

    with filesystem.open(fs_path, mode="rt", encoding="utf-8") as f:
        match suffix:
            case ".json":
                return json.load(f, object_pairs_hook=_unique_json_object)
            case ".yaml" | ".yml":
                return YAML(typ="safe").load(f)
            case _:
                raise ValueError(f"Unsupported manifest format: {suffix}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys before JSON objects are converted into mappings."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result
