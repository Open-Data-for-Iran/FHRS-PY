"""Readers for interpreting runtime resources and members as tables."""

from ._base import BaseReader
from .csv_reader import CSVReader
from .parquet_reader import ParquetReader
from .registry import READERS

__all__ = ["READERS", "BaseReader", "CSVReader", "ParquetReader"]
