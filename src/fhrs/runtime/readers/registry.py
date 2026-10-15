"""Reader instances indexed by their manifest reader names."""

from ._base import BaseReader
from .csv_reader import CSVReader

READERS: dict[str, BaseReader] = {"csv": CSVReader()}
