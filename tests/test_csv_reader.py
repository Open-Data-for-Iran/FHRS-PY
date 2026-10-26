import importlib.util
import unittest
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec

from fhrs import runtime
from fhrs.manifest.models import Dataset as DatasetManifest
from fhrs.manifest.models import Table as TableManifest
from fhrs.runtime.readers import READERS, CSVReader


class CSVReaderChecks:
    backend: str

    def setUp(self):
        if importlib.util.find_spec(self.backend) is None:
            self.skipTest(f"{self.backend} is not installed")
        self.root = f"/csv-reader-{uuid4().hex}"
        self.fs = fsspec.filesystem("memory")
        self.fs.pipe(f"{self.root}/primary/b.csv", b"id,value\n2,20\n")
        self.fs.pipe(f"{self.root}/primary/a.csv", b"id,value\n1,10\n")
        self.fs.pipe(f"{self.root}/backup/a.csv", b"id,value\n3,30\n")
        self.fs.pipe(f"{self.root}/primary/other.txt", b"not a CSV")
        self.addCleanup(self.fs.rm, self.root, recursive=True)
        self.dataset = runtime.Dataset(
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "file": {
                            "locations": [
                                {
                                    "name": "primary",
                                    "uri": f"memory://{self.root}/primary/a.csv",
                                },
                                {
                                    "name": "backup",
                                    "uri": f"memory://{self.root}/backup/a.csv",
                                },
                            ],
                        },
                        "directory": {
                            "type": "directory",
                            "locations": [
                                {
                                    "name": "primary",
                                    "uri": f"memory://{self.root}/primary/",
                                },
                                {
                                    "name": "backup",
                                    "uri": f"memory://{self.root}/backup/",
                                },
                            ],
                            "members": {"rows": "*.csv"},
                        },
                    },
                }
            )
        )
        self.read = getattr(CSVReader(), f"read_{self.backend}")

    def ids(self, frame):
        self.assertEqual(type(frame).__module__.split(".")[0], self.backend)
        return list(frame["id"])

    def test_reads_file_from_default_or_named_mirror(self):
        resource = self.dataset.resource("file")
        self.assertEqual(self.ids(self.read(resource)), [1])
        self.assertEqual(self.ids(self.read(resource, source="backup")), [3])

    def test_missing_working_files_raise_file_not_found(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        dataset = runtime.Dataset(
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "file": {},
                        "directory": {"type": "directory", "locations": []},
                    },
                }
            ),
            working_directory=directory.name,
        )
        for key in ("file", "directory#member:*.csv"):
            with (
                self.subTest(key=key),
                self.assertRaises(FileNotFoundError),
            ):
                self.read(dataset.resource(key))

    def test_table_load_uses_registry_and_preserves_reference_order(self):
        READERS["test_csv"] = CSVReader()
        self.addCleanup(READERS.pop, "test_csv")
        table = runtime.Table(
            TableManifest(resource=["directory#rows", "file"], reader="test_csv"),
            name="rows",
            parent=self.dataset,
        )
        self.assertEqual(self.ids(table.load(backend=self.backend)), [1, 2, 1])
        self.assertEqual(
            self.ids(table.load(backend=self.backend, source="backup")), [3, 3]
        )

    def test_table_load_forwards_reader_options(self):
        self.fs.pipe(f"{self.root}/primary/a.csv", b"id;value\n7;70\n")
        table = runtime.Table(
            TableManifest(resource="file", reader="csv"),
            name="rows",
            parent=self.dataset,
        )
        options = {"sep": ";"} if self.backend == "pandas" else {"separator": ";"}
        self.assertEqual(self.ids(table.load(backend=self.backend, **options)), [7])
        if self.backend == "pandas":
            self.assertEqual(self.ids(table.load(**options)), [7])
        with self.assertRaisesRegex(ValueError, "backend"):
            table.load(backend="unknown")
        unknown = runtime.Table(
            TableManifest(resource="file", reader="unknown"),
            name="rows",
            parent=table.parent,
        )
        with self.assertRaisesRegex(ValueError, "reader"):
            unknown.load(backend=self.backend)

    def test_reads_declared_and_inline_members_in_sorted_order(self):
        resource = self.dataset.resource("directory")
        for selector in ("rows", "member:*.csv"):
            with self.subTest(selector=selector):
                member = resource.member(selector)
                self.assertEqual(self.ids(self.read(member)), [1, 2])
                self.assertEqual(self.ids(self.read(member, source="backup")), [3])

    def test_forwards_backend_reader_options(self):
        self.fs.pipe(f"{self.root}/primary/a.csv", b"id;value\n7;70\n")
        separator = {"sep": ";"} if self.backend == "pandas" else {"separator": ";"}
        self.assertEqual(
            self.ids(self.read(self.dataset.resource("file"), **separator)), [7]
        )

    def test_rejects_bare_directories_and_empty_members(self):
        resource = self.dataset.resource("directory")
        with self.assertRaisesRegex(ValueError, "member"):
            self.read(resource)
        with self.assertRaises(FileNotFoundError):
            self.read(resource.member("member:missing*.csv"))
        with self.assertRaises(KeyError):
            self.read(resource.member("rows"), source="unknown")


class PandasCSVReaderTests(CSVReaderChecks, unittest.TestCase):
    backend = "pandas"

    def test_rejects_chunked_outputs(self):
        for options in ({"chunksize": 1}, {"iterator": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.read(self.dataset.resource("file"), **options)


class PolarsCSVReaderTests(CSVReaderChecks, unittest.TestCase):
    backend = "polars"


if __name__ == "__main__":
    unittest.main()
