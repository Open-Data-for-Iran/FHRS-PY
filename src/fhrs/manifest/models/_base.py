"""Shared manifest field types."""

import re
from typing import Annotated

from pydantic import Field, StringConstraints

Name = Annotated[
    str,
    Field(
        description="Lowercase alphanumeric identifier with underscores or hyphens.",
    ),
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9_-]+$",
    ),
]

RelativePath = Annotated[
    str,
    Field(
        pattern=re.compile(
            r"\A(?!/)(?![A-Za-z][A-Za-z0-9+.-]*:)[^\\\s?#\x00-\x1f\x7f]+\Z"
        )
    ),
]
