import importlib.util
import unittest
from io import BytesIO
from uuid import uuid4

import fsspec

from fhrs import manifest, runtime


class ParquetReaderChecks:
    backend: str

    def setUp(self):
        for dependency in (self.backend, "pyarrow"):
            if importlib.util.find_spec(dependency) is None:
                self.skipTest(f"{dependency} is not installed")
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.fs = fsspec.filesystem("memory")
        self.root = f"/parquet-reader-{uuid4().hex}"
        for name, identifier in (("primary/a", 1), ("primary/b", 2), ("backup/a", 3)):
            stream = BytesIO()
            pq.write_table(
                pa.table({"id": [identifier], "value": [identifier * 10]}), stream
            )
            self.fs.pipe(f"{self.root}/{name}.parquet", stream.getvalue())
        self.addCleanup(self.fs.rm, self.root, recursive=True)
        self.dataset = runtime.Dataset(
            manifest.Dataset.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "rows": {
                            "suffix": ".parquet",
                            "locations": [
                                {
                                    "name": name,
                                    "uri": f"memory://{self.root}/{name}/a.parquet",
                                }
                                for name in ("primary", "backup")
                            ],
                        },
                        "parts": {
                            "type": "directory",
                            "members": {"rows": "*.parquet"},
                            "locations": [
                                {"name": name, "uri": f"memory://{self.root}/{name}"}
                                for name in ("primary", "backup")
                            ],
                        },
                    },
                    "tables": {
                        "rows": {"resource": "rows", "reader": "parquet"},
                        "combined": {
                            "resource": ["parts#rows", "rows"],
                            "reader": "parquet",
                        },
                    },
                }
            )
        )

    def test_table_loads_default_and_named_source_and_forwards_columns(self):
        table = self.dataset.table("rows")
        frame = table.load(backend=self.backend, columns=["id"])
        self.assertEqual(type(frame).__module__.split(".")[0], self.backend)
        self.assertEqual(list(frame.columns), ["id"])
        self.assertEqual(list(frame["id"]), [1])
        self.assertEqual(
            list(table.load(backend=self.backend, source="backup")["id"]), [3]
        )

    def test_members_and_resource_lists_preserve_file_order(self):
        table = self.dataset.table("combined")
        self.assertEqual(list(table.load(backend=self.backend)["id"]), [1, 2, 1])
        self.assertEqual(
            list(table.load(backend=self.backend, source="backup")["id"]), [3, 3]
        )

    def test_rejects_directories_empty_members_and_missing_locations(self):
        from fhrs.runtime.readers import ParquetReader

        read = getattr(ParquetReader(), f"read_{self.backend}")
        parts = self.dataset.resource("parts")
        with self.assertRaisesRegex(ValueError, "member"):
            read(parts)
        with self.assertRaises(FileNotFoundError):
            read(parts.member("member:missing*.parquet"))
        with self.assertRaises(KeyError):
            read(self.dataset.resource("rows"), source="unknown")
        dataset = runtime.Dataset(
            manifest.Dataset(name="empty", resources={"rows": {}})
        )
        with self.assertRaisesRegex(ValueError, "no locations"):
            read(dataset.resource("rows"))
        self.fs.pipe(f"{self.root}/primary/a.parquet", b"invalid parquet")
        if self.backend == "pandas":
            from pyarrow import ArrowInvalid

            error = ArrowInvalid
        else:
            from polars.exceptions import ComputeError

            error = ComputeError
        with self.assertRaises(error):
            read(self.dataset.resource("rows"))


class PandasParquetReaderTests(ParquetReaderChecks, unittest.TestCase):
    backend = "pandas"


class PolarsParquetReaderTests(ParquetReaderChecks, unittest.TestCase):
    backend = "polars"


if __name__ == "__main__":
    unittest.main()
