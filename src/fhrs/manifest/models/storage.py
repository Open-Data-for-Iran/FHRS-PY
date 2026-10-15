"""Base model for named storage declarations."""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, HttpUrl


class BaseStorage(BaseModel, extra="forbid"):
    """Storage declaration with a mapping to an fsspec implementation."""

    protocol: str = Field(min_length=1)
    storage_options: dict[str, Any] = Field(default_factory=dict)

    @property
    def base_path(self) -> str:
        """Root path within the filesystem; specialized storages define their scope."""
        return ""

    def to_fsspec(self) -> dict[str, Any]:
        """Return keyword arguments for ``fsspec.filesystem``."""
        return {**self.storage_options, "protocol": self.protocol}


class EmbeddedStorage(BaseStorage):
    """Data shipped with the code, relative to the dataset manifest on its filesystem."""

    type: Literal["embedded"] = "embedded"
    protocol: Literal["file", "local"] = "file"
    path: str = Field(default="", validation_alias=AliasChoices("path", "base_path"))

    @property
    def base_path(self) -> str:
        """Directory resolved relative to the dataset manifest."""
        return self.path


class HTTPStorage(BaseStorage):
    """An HTTP(S) base URL with options for fsspec's HTTPFileSystem."""

    type: Literal["http"] = "http"
    protocol: Literal["http", "https"] = "http"
    url: HttpUrl = Field(validation_alias=AliasChoices("url", "base_url"))

    @property
    def base_path(self) -> str:
        """Base URL used for resource paths on this storage."""
        return str(self.url)


class S3Storage(BaseStorage):
    """A bucket and optional prefix on AWS or an S3-compatible service."""

    type: Literal["s3"] = "s3"
    protocol: Literal["s3"] = "s3"
    bucket: str = Field(pattern=r"^[^\s/\\:]+\z")
    prefix: str = ""
    endpoint: HttpUrl | None = None
    region: str | None = Field(default=None, min_length=1)

    @property
    def base_path(self) -> str:
        """Bucket and prefix expressed as an fsspec S3 path."""
        prefix = self.prefix.strip("/")
        return f"{self.bucket}/{prefix}" if prefix else self.bucket

    def to_fsspec(self) -> dict[str, Any]:
        """Translate storage fields to s3fs options; explicit fields take priority."""
        options = super().to_fsspec()
        if self.endpoint is not None:
            options["endpoint_url"] = str(self.endpoint)
        if self.region is not None:
            options["client_kwargs"] = {
                **options.get("client_kwargs", {}),
                "region_name": self.region,
            }
        return options
