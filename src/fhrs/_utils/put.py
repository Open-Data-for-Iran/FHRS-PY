"""Copy local files and directories with staging and replacement handling."""

import os
import shutil
import stat
import warnings
from collections.abc import Callable
from contextlib import ExitStack, suppress
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from typing import BinaryIO


def _retry_readonly(
    function: Callable[[str], object], path: str, error: BaseException
) -> None:
    """Make read-only entries writable and retry their deletion once."""
    if not isinstance(error, PermissionError) or function not in (os.unlink, os.rmdir):
        raise error
    mode = os.stat(path, follow_symlinks=False).st_mode
    if stat.S_ISLNK(mode):
        raise error
    os.chmod(path, mode | stat.S_IWRITE)
    function(path)


def put_file(
    data: str | os.PathLike[str] | bytes | BinaryIO,
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write file content, leaving caller-owned streams open.

    Read streams from their current position. Publish only after copying succeeds;
    an existing destination requires overwrite=True.
    """
    destination = destination.resolve()
    if not overwrite and destination.exists():
        raise FileExistsError(destination)

    temporary = None
    try:
        with ExitStack() as stack:
            if isinstance(data, (str, os.PathLike)):
                path = Path(data)
                if path.is_dir():
                    raise IsADirectoryError(path)
                stream = stack.enter_context(path.open("rb"))
            elif isinstance(data, bytes):
                stream = stack.enter_context(BytesIO(data))
            elif callable(getattr(data, "read", None)):
                stream = data
            else:
                raise TypeError("data must be a local path, bytes, or binary stream")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as target:
                temporary = Path(target.name)
                shutil.copyfileobj(stream, target)

        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            os.rename(temporary, destination)
        else:
            # Publishing a hard link fails if another writer created the target.
            os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def put_directory(
    source: str | os.PathLike[str],
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Copy directory contents, replacing the entire destination when requested.

    Stage copies before publication. Restore the original on publication failure;
    if restoration also fails, retain its backup and report the recovery path.
    Cleanup failures emit a warning with the retained temporary directory path.
    """
    destination = destination.resolve()
    if not overwrite and destination.exists():
        raise FileExistsError(destination)

    source = Path(source).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if not source.is_dir():
        raise NotADirectoryError(source)
    if source != destination and destination.is_relative_to(source):
        raise ValueError("Destination cannot be inside the source directory")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(mkdtemp(dir=destination.parent, prefix=f".{destination.name}."))
    staged = temporary / "content"
    backup = temporary / "previous"
    published = False
    try:
        shutil.copytree(source, staged)
        if destination.exists():
            if not overwrite:
                raise FileExistsError(destination)
            if not destination.is_dir():
                raise NotADirectoryError(destination)
            os.rename(destination, backup)
        try:
            if not overwrite and os.name != "nt":
                # Reserve the name: POSIX rename can replace an empty directory.
                destination.mkdir()
                try:
                    os.rename(staged, destination)
                except OSError:
                    with suppress(OSError):
                        destination.rmdir()
                    raise
            else:
                os.rename(staged, destination)
        except OSError:
            if backup.exists():
                try:
                    os.rename(backup, destination)
                except OSError as error:
                    raise OSError(
                        f"Could not restore original directory; preserved at {backup}"
                    ) from error
            raise
        published = True
    finally:
        # Retain the backup for recovery if restoring the original also failed.
        if published or not backup.exists():
            try:
                shutil.rmtree(temporary, onexc=_retry_readonly)
            except OSError as error:
                warnings.warn(
                    f"Temporary directory cleanup failed; remaining files are at "
                    f"{temporary}: {error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
    return destination
