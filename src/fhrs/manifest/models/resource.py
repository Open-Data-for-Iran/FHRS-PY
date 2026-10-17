"""Manifest descriptions of physical files and directories."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class Location(BaseModel, extra="forbid"):
    """An artifact address, optionally relative to a named storage."""

    uri: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    storage: str | None = Field(default=None, min_length=1)
    original: bool = Field(default=False, strict=True)


class Checksums(BaseModel, extra="forbid"):
    """Checksum of the complete file bytes."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}\z")


class Resource(BaseModel, extra="forbid"):
    """A file or directory with one or more ordered mirror locations."""

    type: Literal["file", "directory"] = "file"
    locations: list[Location] = Field(min_length=1)
    size: int | None = Field(default=None, ge=0, strict=True)
    checksums: Checksums | None = None
    members: dict[
        Annotated[str, Field(min_length=1)], Annotated[str, Field(min_length=1)]
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_resource(self) -> Self:
        if self.type == "file" and "members" in self.model_fields_set:
            raise ValueError("File resources cannot declare members")
        if "size" in self.model_fields_set and self.size is None:
            raise ValueError("File size must be a nonnegative integer in bytes")
        if self.type == "directory" and self.size is not None:
            raise ValueError("Directory resources cannot declare file size")
        if self.type == "directory" and self.checksums is not None:
            raise ValueError("Directory resources cannot declare file checksums")
        locations = [
            (location.uri, location.name, location.storage, location.original)
            for location in self.locations
        ]
        if len(set(locations)) != len(locations):
            raise ValueError("Locations must be unique within a resource")
        names = [
            location.name for location in self.locations if location.name is not None
        ]
        if len(set(names)) != len(names):
            raise ValueError("Location names must be unique within a resource")
        return self
