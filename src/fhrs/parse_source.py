"""Normalize browser URLs into fsspec dataset sources."""

import os
from urllib.parse import urlsplit


def parse(source: str | os.PathLike[str]) -> str | os.PathLike[str]:
    """Normalize a dataset source, preserving path-like objects."""
    return parse_github(source) if isinstance(source, str) else source


def parse_github(source: str) -> str:
    """Convert GitHub repo, tree, and blob URLs; leave other sources unchanged.

    No network requests are made. A tree/blob reference occupies one URL segment;
    remaining segments identify the directory or file inside the repository.
    """
    url = urlsplit(source)
    if url.scheme not in ("http", "https") or url.netloc.lower() != "github.com":
        return source
    parts = url.path.strip("/").split("/")
    if len(parts) < 2 or not all(parts[:2]):
        return source
    owner, repo, *rest = parts
    repo = repo.removesuffix(".git")
    if not repo:
        return source
    ref, path = "", []
    if rest:
        if len(rest) < 2 or rest[0] not in ("tree", "blob") or not rest[1]:
            return source
        # ponytail: refs use one segment; API lookup needed for ambiguous slash refs.
        ref, *path = rest[1:]
    suffix = "/" + "/".join(path) if path else ""
    return f"github://{owner}:{repo}@{ref}{suffix}"
