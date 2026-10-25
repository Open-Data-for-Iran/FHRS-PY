import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from fhrs import manifest, runtime


class DatasetVersionTests(unittest.TestCase):
    def test_combined_version_is_computed_and_serialized(self):
        for status, suffix in (("in_development", "~dev"), ("published", "")):
            with self.subTest(status=status):
                declaration = manifest.Dataset(
                    name="survey",
                    schema_version="2.3.1",
                    release="2026-10-26.1",
                    status=status,
                )
                expected = f"2.3.1@2026-10-26.1{suffix}"
                self.assertEqual(declaration.version, expected)
                self.assertEqual(runtime.Dataset(declaration).version, expected)
                self.assertEqual(declaration.model_dump()["version"], expected)
                self.assertEqual(
                    declaration.model_dump(mode="json")["version"], expected
                )
                self.assertNotIn("version", type(declaration).model_fields)
                self.assertIn("version", type(declaration).model_computed_fields)
                for format in ("yaml", "json"):
                    with TemporaryDirectory() as destination:
                        manifest.dump(declaration, destination, format=format)
                        loaded = runtime.load_manifest(
                            Path(destination) / f"manifest.{format}"
                        )
                        self.assertEqual(loaded.version, expected)

    def test_combined_version_requires_both_components(self):
        for fields in ({}, {"schema_version": "2.3.1"}, {"release": "1"}):
            declaration = manifest.Dataset(name="survey", **fields)
            self.assertIsNone(declaration.version)
            self.assertIsNone(runtime.Dataset(declaration).version)

    def test_version_components_reject_reserved_characters(self):
        for field in ("schema_version", "release"):
            for value in ("2@1", "1~dev", "2@1\n", "1~dev\n"):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValidationError),
                ):
                    manifest.Dataset(name="survey", **{field: value})

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
