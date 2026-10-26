import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from fhrs import manifest


class VersionModelTests(unittest.TestCase):
    def test_version_declarations_survive_manifest_round_trip(self):
        entries = {"1.0@001": {"manifest": "releases/001/manifest.yaml"}}
        versions = {"entries": entries, "indexes": ["versions/main.yaml"]}
        index = manifest.VersionIndex.model_validate(entries)
        self.assertEqual(index.model_dump(), entries)
        self.assertIsInstance(index.root["1.0@001"], manifest.VersionReference)
        dataset = manifest.Dataset(name="survey", versions=versions)
        self.assertEqual(dataset.versions.entries, index)
        for format in ("yaml", "json"):
            with (
                self.subTest(format=format),
                TemporaryDirectory(dir=Path(__file__).parent) as directory,
            ):
                manifest.dump(dataset, directory, format=format)
                loaded = manifest.load(Path(directory) / f"manifest.{format}")
                self.assertEqual(loaded.versions.model_dump(), versions)

    def test_defaults_are_empty_and_independent(self):
        self.assertIsNone(manifest.Dataset(name="survey").versions)
        first = manifest.Versions()
        second = manifest.Versions()
        self.assertEqual(first.model_dump(), {"entries": {}, "indexes": []})
        first.entries.root["1.0@001"] = manifest.VersionReference(manifest="one.yaml")
        first.indexes.append("index.yaml")
        self.assertEqual(second.model_dump(), {"entries": {}, "indexes": []})

    def test_invalid_paths_and_unknown_fields_are_rejected(self):
        for value in (
            {"indexes": ["/absolute.yaml"]},
            {"entries": {"1.0@001": {"manifest": ""}}},
            {"unknown": True},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                manifest.Versions.model_validate(value)
