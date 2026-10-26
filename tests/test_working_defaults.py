import importlib.util
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec

from fhrs import manifest, runtime


class WorkingDefaultChecks:
    backend: str

    def setUp(self):
        for dependency in (self.backend, "pyarrow"):
            if importlib.util.find_spec(dependency) is None:
                self.skipTest(f"{dependency} is not installed")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "working"
        self.declaration = manifest.models.Dataset.model_validate(
            {
                "name": "survey",
                "resources": {
                    "rows": {"suffix": ".csv"},
                    "columnar": {"suffix": ".parquet"},
                    "parts": {
                        "type": "directory",
                        "members": {"csv": "*.csv", "parquet": "*.parquet"},
                    },
                },
                "tables": {
                    "csv_parts": {"resource": "parts#csv", "reader": "csv"},
                    "parquet_parts": {"resource": "parts#parquet", "reader": "parquet"},
                },
            }
        )
        self.dataset = runtime.ManagedDataset(
            self.declaration, working_directory=self.root
        )

    def parquet(self, ids):
        import pyarrow as pa
        import pyarrow.parquet as pq

        stream = BytesIO()
        pq.write_table(pa.table({"id": ids}), stream)
        return stream.getvalue()

    def test_defaults_resolve_working_without_io_or_manifest_changes(self):
        before = self.declaration.model_dump()
        rows = self.dataset.resource("rows")
        self.assertEqual(rows.source(), rows.source("working"))
        self.assertEqual(rows.source(None), rows.source("working"))
        self.assertEqual(rows.locations, ())
        self.assertEqual(rows.sources, ())
        member = self.dataset.resource("parts#csv")
        self.assertEqual(member.source(), member.source("working"))
        self.assertFalse(self.root.exists())
        self.assertEqual(self.declaration.model_dump(), before)

    def test_loads_files_and_directory_members_without_explicit_source(self):
        self.dataset.resource("rows").put(b"id\n1\n2\n")
        self.dataset.resource("columnar").put(self.parquet([1, 2]))
        parts = self.dataset.resource("parts")
        for name, identifier in (("b", 2), ("a", 1)):
            parts.add(f"{name}.csv", f"id\n{identifier}\n".encode())
            parts.add(f"{name}.parquet", self.parquet([identifier]))
        for dataset_type in (runtime.Dataset, runtime.ManagedDataset):
            dataset = dataset_type(self.declaration, working_directory=self.root)
            for name in ("rows", "columnar", "csv_parts", "parquet_parts"):
                with self.subTest(dataset_type=dataset_type, table=name):
                    frame = dataset.table(name).load(backend=self.backend)
                    self.assertEqual(list(frame["id"]), [1, 2])
        self.assertEqual(len(parts.member("csv").files()), 2)

    def test_declared_sources_take_priority_and_do_not_fall_back_on_failure(self):
        memory = fsspec.filesystem("memory")
        uri = f"memory://working-default-{uuid4().hex}"
        memory.pipe(uri, b"id\n9\n")
        self.addCleanup(memory.rm, uri)
        declaration = manifest.models.Dataset(
            name="survey",
            resources={
                "rows": {
                    "suffix": ".csv",
                    "locations": [{"name": "primary", "uri": uri}],
                }
            },
        )
        dataset = runtime.ManagedDataset(declaration, working_directory=self.root)
        rows = dataset.resource("rows")
        rows.put(b"id\n1\n")
        self.assertIs(rows.source(), rows.sources[0])
        self.assertEqual(
            list(dataset.table("rows").load(backend=self.backend)["id"]), [9]
        )
        self.assertEqual(
            list(
                dataset.table("rows").load(backend=self.backend, source="working")["id"]
            ),
            [1],
        )
        memory.rm(uri)
        self.addCleanup(memory.pipe, uri, b"")
        with self.assertRaises(FileNotFoundError):
            dataset.table("rows").load(backend=self.backend)


class PandasWorkingDefaultTests(WorkingDefaultChecks, unittest.TestCase):
    backend = "pandas"


class PolarsWorkingDefaultTests(WorkingDefaultChecks, unittest.TestCase):
    backend = "polars"


if __name__ == "__main__":
    unittest.main()
