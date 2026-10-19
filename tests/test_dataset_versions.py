import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from fhrs import manifest, runtime


class DatasetVersionTests(unittest.TestCase):
    def test_optional_versions_default_to_none_and_are_not_dumped(self):
        declaration = manifest.Dataset(name="survey")
        dataset = runtime.Dataset(declaration)
        self.assertIsNone(dataset.schema_version)
        self.assertIsNone(dataset.release)
        with TemporaryDirectory() as destination:
            dataset.dump(destination)
            loaded = manifest.load(Path(destination) / "manifest.yaml")
        self.assertIsNone(loaded.schema_version)
        self.assertIsNone(loaded.release)
        self.assertNotIn("release", declaration.model_dump(exclude_none=True))
        self.assertNotIn("schema_version", declaration.model_dump(exclude_none=True))

    def test_versions_survive_yaml_and_json_round_trips(self):
        declaration = manifest.Dataset(
            name="survey", schema_version="2.1", release="2026-10-20.1"
        )
        dataset = runtime.Dataset(declaration)
        self.assertEqual(dataset.schema_version, "2.1")
        self.assertEqual(dataset.release, "2026-10-20.1")
        for format in ("yaml", "json"):
            with self.subTest(format=format), TemporaryDirectory() as destination:
                dataset.dump(destination, format=format)
                loaded = runtime.load_manifest(Path(destination) / f"manifest.{format}")
                self.assertEqual(loaded.schema_version, "2.1")
                self.assertEqual(loaded.release, "2026-10-20.1")

    def test_versions_require_nonblank_strings(self):
        for field in ("schema_version", "release"):
            for value in ("", " \t\n", 2, True, [], {}):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValidationError),
                ):
                    manifest.Dataset(name="survey", **{field: value})


if __name__ == "__main__":
    unittest.main()
