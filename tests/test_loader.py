import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import fsspec

import fhrs
from fhrs import runtime


class LoaderTests(unittest.TestCase):
    def test_explicit_paths_and_urls_use_manifest_loader(self):
        paths = (
            Path("survey"),
            ".",
            "..",
            ".fhrs",
            "./survey",
            "survey/manifest.yaml",
            r"survey\manifest.yaml",
            r"C:\survey",
            "manifest.yaml",
            "manifest.YML",
            "manifest.json",
            "https://example.org/survey",
            "memory:survey",
        )
        for source in paths:
            with (
                self.subTest(source=source),
                patch("fhrs.runtime.loader.load_manifest") as load_manifest,
            ):
                result = fhrs.load(source, working_directory="work")
                load_manifest.assert_called_once_with(
                    source, manage=False, storage_options=None, working_directory="work"
                )
                self.assertIs(result, load_manifest.return_value)

    def test_reads_local_manifest(self):
        source = Path(__file__).resolve().parents[1] / "examples/basic/fhrs.yaml"
        for path in (source, str(source)):
            with self.subTest(path=path):
                dataset = fhrs.load(path)
                self.assertIsInstance(dataset, runtime.Dataset)
                self.assertEqual(Path(dataset.source.urlpath), source)

    def test_forwards_storage_options_to_manifest_loader(self):
        root = f"/loader-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(f"{root}/fhrs.yaml", b"name: remote\n")
        self.addCleanup(filesystem.rm, root, recursive=True)
        dataset = fhrs.load(
            root, storage_options={"protocol": "memory"}, working_directory="work"
        )
        self.assertEqual(dataset.name, "remote")
        self.assertEqual(dataset.working_directory, Path("work").resolve())
        self.assertEqual(dataset.source.storage_options, {"protocol": "memory"})
        self.assertEqual(fhrs.load(f"memory://{root}/fhrs.yaml").name, "remote")

    def test_missing_explicit_path_does_not_fall_back_to_package(self):
        with self.assertRaises(FileNotFoundError):
            fhrs.load(Path(f"missing_{uuid4().hex}"))

    def test_package_rejects_storage_options(self):
        with self.assertRaisesRegex(ValueError, "storage_options"):
            fhrs.load("survey", storage_options={"protocol": "memory"})


if __name__ == "__main__":
    unittest.main()
