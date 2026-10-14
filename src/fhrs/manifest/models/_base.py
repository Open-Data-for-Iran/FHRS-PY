"""Shared manifest field types."""

import re
from typing import Annotated

from pydantic import Field

RelativePath = Annotated[
    str,
    Field(
        pattern=re.compile(
            r"\A(?!/)(?![A-Za-z][A-Za-z0-9+.-]*:)[^\\\s?#\x00-\x1f\x7f]+\Z"
        )
    ),
]
