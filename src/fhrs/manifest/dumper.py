"""Write dataset manifests as flat or linked YAML and JSON files."""

import json
import os
import posixpath
from collections.abc import Mapping
from io import StringIO
from typing import Any, Literal

import fsspec
from ruamel.yaml import YAML

from .models.collection import BaseCollection, ManifestReference
from .models.dataset import Dataset


def dump(
    dataset: Dataset,
    destination: str | os.PathLike[str] | None = None,
    *,
    format: Literal["yaml", "json"] | None = None,
    layout: Mapping[str, str] | None = None,
    storage_options: dict[str, Any] | None = None,
) -> None:
    """Write manifest.<format> in a local or fsspec destination directory.

    Layout maps dataset-relative collection keys to filenames relative to the
    destination. Unselected collections stay inline. All references must already
    be resolved (as returned by load()). The input is never modified.

    Linked filenames must stay inside the destination and match the format.
    Existing files are overwritten; resource contents and paths are unchanged.
    Omitted or None arguments use dataset.dump_options; empty mappings override
    stored layout or storage options. Dump options are never serialized.
    Dataset fields follow Dataset's explicit dump order, beginning with
    fhrs_version. Other declarations follow model field order.
    """
    if not isinstance(dataset, Dataset):
        raise TypeError(
            "dump() requires a manifest Dataset; use runtime_dataset.manifest"
        )
    options = dataset.dump_options
    destination = options.destination if destination is None else destination
    format = options.format if format is None else format
    layout = options.layout if layout is None else layout
    storage_options = (
        options.storage_options if storage_options is None else storage_options
    )
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported manifest format: {format}")
    if not os.fspath(destination):
        raise ValueError("Destination must be nonempty")

    files = _prepare_layout(layout, format)
    documents = _build_documents(dataset, files)
    output = _serialize_documents(documents, format)
    _write_documents(output, destination, storage_options)


def _prepare_layout(
    layout: Mapping[str, str] | None, format: Literal["yaml", "json"]
) -> dict[str, str]:
    """Validate collection paths and return normalized output filenames."""
    root_file = f"manifest.{format}"
    files = {"": root_file}
    for key, filename in (layout or {}).items():
        if not key or any(part in ("", ".", "..") for part in key.split("/")):
            raise ValueError(f"Invalid collection path: {key!r}")
        ManifestReference(manifest=filename)
        if ".." in filename.split("/"):
            raise ValueError(f"Linked file must stay inside destination: {filename!r}")
        filename = posixpath.normpath(filename)
        suffix = posixpath.splitext(filename)[1]
        if suffix not in ((".yaml", ".yml") if format == "yaml" else (".json",)):
            raise ValueError(
                f"Linked filename must match {format} format: {filename!r}"
            )
        files[key] = filename

    _check_file_conflicts(files)
    return files


def _check_file_conflicts(files: Mapping[str, str]) -> None:
    """Reject duplicate targets and paths used as both files and directories."""
    targets = sorted(filename.casefold() for filename in files.values())
    for index, filename in enumerate(targets):
        for other in targets[index + 1 :]:
            if other == filename or other.startswith(filename + "/"):
                raise ValueError(
                    f"Conflicting manifest filenames: {filename!r}, {other!r}"
                )


def _build_documents(
    dataset: Dataset, files: Mapping[str, str]
) -> dict[str, dict[str, Any]]:
    """Build manifest documents, replacing selected collections with links."""
    documents: dict[str, dict[str, Any]] = {}
    visited = set()

    def render(node: BaseCollection, key: str, containing_file: str) -> dict[str, Any]:
        visited.add(key)
        data = node.model_dump(mode="json", exclude={"collections"}, exclude_none=True)
        children = {}
        for name, child in node.collections.items():
            child_key = f"{key}/{name}" if key else name
            if isinstance(child, ManifestReference):
                raise TypeError(
                    f"Unresolved manifest reference at {child_key!r}; load it first"
                )
            child_file = files.get(child_key)
            if child_file is None:
                children[name] = render(child, child_key, containing_file)
            else:
                documents[child_file] = render(child, child_key, child_file)
                children[name] = {
                    "manifest": posixpath.relpath(
                        child_file, posixpath.dirname(containing_file) or "."
                    )
                }
        data["collections"] = children
        field_order = type(node).model_fields
        if isinstance(node, Dataset):
            field_order = (*node._dump_field_order, *field_order)
        return {name: data[name] for name in field_order if name in data}

    documents[files[""]] = render(dataset, "", files[""])
    unknown = files.keys() - visited
    if unknown:
        raise ValueError(f"Unknown collection paths in layout: {sorted(unknown)}")
    return documents


def _serialize_documents(
    documents: Mapping[str, dict[str, Any]], format: Literal["yaml", "json"]
) -> dict[str, str]:
    """Serialize all documents before any output files are opened."""
    if format == "json":
        return {
            filename: json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            for filename, data in documents.items()
        }

    output = {}
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.representer.sort_base_mapping_type_on_output = False
    for filename, data in documents.items():
        stream = StringIO()
        yaml.dump(data, stream)
        output[filename] = stream.getvalue()
    return output


def _write_documents(
    output: Mapping[str, str],
    destination: str | os.PathLike[str],
    storage_options: dict[str, Any] | None,
) -> None:
    """Create destination directories and write serialized manifests via fsspec."""
    filesystem, base_path = fsspec.url_to_fs(
        os.fspath(destination), **(storage_options or {})
    )
    for filename, content in output.items():
        path = posixpath.join(base_path, filename)
        filesystem.makedirs(posixpath.dirname(path), exist_ok=True)
        with filesystem.open(path, mode="wt", encoding="utf-8") as stream:
            stream.write(content)
