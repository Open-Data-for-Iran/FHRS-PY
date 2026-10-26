import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fhrs
from fhrs import manifest, runtime
from fhrs.manifest.models import Dataset


class DescriptiveMetadataTests(unittest.TestCase):
    def test_resource_and_table_metadata_survive_manifest_round_trip(self):
        declaration = Dataset(
            name="catalog",
            resources={
                "data": {
                    "suffix": ".csv",
                    "title": "Dataset catalog",
                    "description": "Metadata for SCI datasets.",
                }
            },
            tables={
                "data": {
                    "resource": "data",
                    "reader": "csv",
                    "title": "Datasets",
                    "description": "One row per dataset.",
                }
            },
        )
        with TemporaryDirectory() as directory:
            for format in ("yaml", "json"):
                with self.subTest(format=format):
                    manifest.dump(declaration, directory, format=format)
                    dataset = fhrs.load(Path(directory) / f"manifest.{format}")
                    self.assertEqual(dataset.resource("data").title, "Dataset catalog")
                    self.assertEqual(
                        dataset.resource("data").description,
                        "Metadata for SCI datasets.",
                    )
                    self.assertEqual(dataset.table("data").title, "Datasets")
                    self.assertEqual(
                        dataset.table("data").description, "One row per dataset."
                    )
        dataset = runtime.Dataset(
            Dataset(
                name="plain",
                resources={"data": {}},
                tables={"data": {"resource": "data", "reader": "csv"}},
            )
        )
        self.assertIsNone(dataset.resource("data").title)
        self.assertIsNone(dataset.resource("data").description)
        self.assertIsNone(dataset.table("data").description)
