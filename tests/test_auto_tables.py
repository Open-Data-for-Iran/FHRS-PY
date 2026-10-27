import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fhrs import manifest, runtime


class AutoTableTests(unittest.TestCase):
    def test_infers_tables_without_mutating_manifest_or_accessing_files(self):
        declaration = manifest.models.Dataset.model_validate(
            {
                "name": "survey",
                "resources": {
                    "rows": {"suffix": ".CSV"},
                    "columnar": {"suffix": ".Parquet"},
                    "archive": {"suffix": ".csv.gz"},
                    "unknown": {"locations": [{"uri": "memory://missing.csv"}]},
                    "pages": {"type": "directory"},
                },
                "collections": {
                    "wave": {"resources": {"rows": {"suffix": ".parquet"}}}
                },
            }
        )
        before = declaration.model_dump()
        for dataset_type in (runtime.Dataset, runtime.ManagedDataset):
            with self.subTest(dataset_type=dataset_type):
                dataset = dataset_type(declaration)
                self.assertEqual(set(dataset.tables), {"rows", "columnar"})
                self.assertEqual(dataset.table("rows").reader, "csv")
                self.assertEqual(dataset.table("columnar").reader, "parquet")
                self.assertIs(
                    dataset.table("rows").resources[0], dataset.resource("rows")
                )
                self.assertEqual(dataset.table("wave/rows").reader, "parquet")
                if dataset_type is runtime.ManagedDataset:
                    self.assertIsInstance(dataset.table("rows"), runtime.ManagedTable)
        self.assertEqual(declaration.model_dump(), before)
        self.assertEqual(declaration.tables, {})

    def test_explicit_tables_override_inferred_tables(self):
        dataset = runtime.Dataset(
            manifest.models.Dataset.model_validate(
                {
                    "name": "survey",
                    "resources": {"rows": {"suffix": ".csv"}, "other": {}},
                    "tables": {
                        "rows": {
                            "resource": "other",
                            "reader": "custom",
                            "title": "Explicit",
                        },
                        "alias": {"resource": "rows", "reader": "csv"},
                    },
                }
            )
        )
        self.assertEqual(set(dataset.tables), {"rows", "alias"})
        self.assertEqual(dataset.table("rows").reader, "custom")
        self.assertEqual(dataset.table("rows").title, "Explicit")
        self.assertIs(dataset.table("rows").resources[0], dataset.resource("other"))

    def test_inferred_csv_loads_from_local_storage(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas is not installed")
        with TemporaryDirectory() as directory:
            dataset = runtime.ManagedDataset(
                manifest.models.Dataset(
                    name="survey", resources={"rows": {"suffix": ".csv"}}
                ),
                local_directory=Path(directory),
            )
            dataset.resource("rows").put(b"id,value\n1,10\n")
            self.assertEqual(
                dataset.table("rows").load(source="local")["id"].tolist(), [1]
            )


if __name__ == "__main__":
    unittest.main()
