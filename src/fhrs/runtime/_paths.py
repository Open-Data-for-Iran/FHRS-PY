"""Validate resource URI paths before resolving them on a filesystem."""

import re
from urllib.parse import unquote

from pydantic import TypeAdapter

from ..manifest.models._base import RelativePath

_RELATIVE_PATH = TypeAdapter(RelativePath)


def _validate_relative_path(path: str) -> str:
    return _RELATIVE_PATH.validate_python(path)


def _location_path(uri: str, protocol: str, *, scoped: bool = False) -> str:
    _validate_relative_path(uri)
    if ":" in uri.split("/", 1)[0] or re.search(r"%(?![0-9a-fA-F]{2})", uri):
        raise ValueError(f"Invalid relative resource URI: {uri!r}")
    segments = [unquote(segment, errors="strict") for segment in uri.split("/")]
    if scoped and any(
        segment in (".", "..") or any(char in segment for char in ("/", "\\", "\0"))
        for segment in segments
    ):
        raise ValueError(f"Resource path must stay inside its named storage: {uri!r}")
    return uri if protocol in ("http", "https") else "/".join(segments)
