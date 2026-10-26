import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from fhrs import manifest


class VersionModelTests(unittest.TestCase):
    def test_version_reference_accepts_storage_options(self):
        reference = manifest.models.VersionReference(
            manifest="memory://archive/fixed.json",
            storage_options={"token": "test"},
        )
        self.assertEqual(reference.storage_options, {"token": "test"})
        self.assertIsNone(
            manifest.models.VersionReference(manifest="one.yaml").storage_options
        )
        for fields in ({"storage": "archive"}, {"storage_options": "archive"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                manifest.models.VersionReference(manifest="one.yaml", **fields)

    def test_version_declarations_survive_manifest_round_trip(self):
        entries = {"1.0@001": {"manifest": "releases/001/manifest.yaml"}}
        versions = {"entries": entries, "indexes": ["versions/main.yaml"]}
        index = manifest.models.VersionIndex.model_validate(entries)
        self.assertEqual(index.model_dump(exclude_none=True), entries)
        self.assertIsInstance(index.root["1.0@001"], manifest.models.VersionReference)
        dataset = manifest.models.Dataset(name="survey", versions=versions)
        self.assertEqual(dataset.versions.entries, index)
        for format in ("yaml", "json"):
            with (
                self.subTest(format=format),
                TemporaryDirectory(dir=Path(__file__).parent) as directory,
            ):
                manifest.dump(dataset, directory, format=format)
                loaded = manifest.load(Path(directory) / f"manifest.{format}")
                self.assertEqual(
                    loaded.versions.model_dump(exclude_none=True), versions
                )

    def test_defaults_are_empty_and_independent(self):
        self.assertIsNone(manifest.models.Dataset(name="survey").versions)
        first = manifest.models.Versions()
        second = manifest.models.Versions()
        self.assertEqual(first.model_dump(), {"entries": {}, "indexes": []})
        first.entries.root["1.0@001"] = manifest.models.VersionReference(
            manifest="one.yaml"
        )
        first.indexes.append("index.yaml")
        self.assertEqual(second.model_dump(), {"entries": {}, "indexes": []})

    def test_invalid_paths_and_unknown_fields_are_rejected(self):
        for value in (
            {"indexes": ["/absolute.yaml"]},
            {"entries": {"1.0@001": {"manifest": ""}}},
            {"unknown": True},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                manifest.models.Versions.model_validate(value)
