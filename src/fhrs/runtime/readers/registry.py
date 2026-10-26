"""Reader instances indexed by their manifest reader names."""

from ._base import BaseReader
from .csv_reader import CSVReader
from .parquet_reader import ParquetReader

READERS: dict[str, BaseReader] = {"csv": CSVReader(), "parquet": ParquetReader()}
