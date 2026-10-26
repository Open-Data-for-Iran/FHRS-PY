import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from fhrs import manifest, runtime


class WorkingSourceTests(unittest.TestCase):
    def test_working_storage_resolves_paths_without_entering_manifest(self):
        dataset = runtime.Dataset(
            manifest.models.Dataset(
                name="survey", resources={"report": {"suffix": ".pdf"}}
            )
        )
        storage = dataset.storage("working")
        self.assertIs(storage, dataset.storages["working"])
        self.assertIs(storage.dataset, dataset)
        self.assertEqual(storage.protocol, "file")
        self.assertEqual(Path(storage.base_path), Path.cwd() / "data/survey")
        self.assertEqual(
            storage.resolve("report.pdf"), dataset.resource("report").source("working")
        )
        self.assertEqual(storage.filesystem().protocol, ("file", "local"))
        self.assertNotIn("working", dataset.manifest.storages)
        with self.assertRaises(ValueError):
            storage.resolve("../outside")

    def test_working_path_is_local_for_files_directories_and_managed_resources(self):
        declaration = manifest.models.Dataset(
            name="survey",
            collections={
                "wave": {
                    "resources": {
                        "report": {
                            "suffix": ".csv",
                            "locations": [{"uri": "memory://remote/report.csv"}],
                        },
                        "parts": {"type": "directory"},
                    }
                }
            },
        )
        before = declaration.model_dump()
        with TemporaryDirectory() as directory:
            root = Path(directory) / "working"
            for dataset_type in (runtime.Dataset, runtime.ManagedDataset):
                with self.subTest(dataset_type=dataset_type):
                    dataset = dataset_type(declaration, working_directory=root)
                    report = dataset.resource("wave/report")
                    parts = dataset.resource("wave/parts")
                    self.assertIsInstance(report.working_path, Path)
                    self.assertEqual(report.working_path, root / "wave/report.csv")
                    self.assertEqual(parts.working_path, root / "wave/parts")
                    self.assertEqual(
                        report.working_path, Path(report.source("working").urlpath)
                    )
                    self.assertEqual(
                        report.source().urlpath, "memory://remote/report.csv"
                    )
                    self.assertFalse(root.exists())
        self.assertEqual(declaration.model_dump(), before)

    def test_working_path_ignores_declared_working_location(self):
        declaration = manifest.models.Dataset(
            name="survey",
            resources={
                "report": {
                    "suffix": ".csv",
                    "locations": [{"storage": "working", "uri": "archive.csv"}],
                }
            },
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive.csv"
            archive.write_bytes(b"original")
            dataset = runtime.ManagedDataset(declaration, working_directory=root)
            report = dataset.resource("report")
            self.assertEqual(report.working_path, root / "report.csv")
            self.assertEqual(report.put(b"new", overwrite=True), root / "report.csv")
            self.assertEqual((root / "report.csv").read_bytes(), b"new")
            self.assertEqual(archive.read_bytes(), b"original")

    def test_default_directory_is_captured_when_dataset_is_created(self):
        dataset = runtime.Dataset(
            manifest.models.Dataset(
                name="survey", resources={"report": {"suffix": ".pdf"}}
            )
        )
        expected = Path.cwd() / "data/survey/report.pdf"
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(
                    Path(dataset.resource("report").source("working").path), expected
                )
            finally:
                os.chdir(previous)
        self.assertEqual(dataset.resource("report").sources, ())

    def test_custom_directory_supports_nested_resources_and_members(self):
        declaration = manifest.models.Dataset(
            name="survey",
            collections={
                "wave": {
                    "resources": {
                        "report": {
                            "suffix": ".csv",
                            "locations": [{"uri": "https://example.org/report.csv"}],
                        },
                        "parts": {"type": "directory", "members": {"rows": "*.csv"}},
                    }
                }
            },
        )
        before = declaration.model_dump()
        with TemporaryDirectory() as directory:
            root = Path(directory) / "work"
            dataset = runtime.Dataset(declaration, working_directory=root)
            report = dataset.resource("wave/report")
            self.assertFalse(root.exists())
            self.assertEqual(
                Path(report.source("working").path), root / "wave/report.csv"
            )
            self.assertEqual(
                report.sources[0].urlpath, "https://example.org/report.csv"
            )
            self.assertEqual(len(report.sources), 1)
            parts = dataset.resource("wave/parts")
            (root / "wave/parts").mkdir(parents=True)
            (root / "wave/parts/a.csv").write_text("value\n1\n")
            for member in (parts.member("rows"), parts.member("member:*.csv")):
                self.assertEqual(member.sources, ())
                files = member.files(source="working")
                self.assertEqual(
                    [Path(source.path) for source in files], [root / "wave/parts/a.csv"]
                )
        self.assertEqual(declaration.model_dump(), before)

    def test_loader_accepts_working_directory(self):
        examples = Path(__file__).resolve().parents[1] / "examples/basic"
        dataset = runtime.load_manifest(examples, working_directory="local-data")
        self.assertEqual(
            Path(dataset.resource("data").source("working").path),
            Path.cwd() / "local-data/data",
        )

    def test_loader_defaults_to_dataset_data_directory(self):
        examples = Path(__file__).resolve().parents[1] / "examples/basic"
        dataset = runtime.load_manifest(examples)
        self.assertEqual(
            Path(dataset.resource("data").source("working").path),
            Path.cwd() / "data" / dataset.name / "data",
        )

    def test_working_directory_expands_dataset_name_template(self):
        for directory in (
            "cache/<dataset.name>/files",
            Path("cache/<dataset.name>/files"),
        ):
            with self.subTest(directory=directory):
                dataset = runtime.Dataset(
                    manifest.models.Dataset(name="survey"), working_directory=directory
                )
                self.assertEqual(
                    dataset.working_directory, Path.cwd() / "cache/survey/files"
                )

    def test_declared_working_location_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "working.*reserved"):
            manifest.models.Dataset(
                name="survey",
                resources={
                    "data": {"locations": [{"name": "working", "uri": "memory://data"}]}
                },
            )

    def test_default_directory_rejects_dataset_names_with_path_components(self):
        for name in ("../outside", ".", "..", "/outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime.Dataset(manifest.models.Dataset(name=name))

    def test_working_path_cannot_escape_directory(self):
        dataset = runtime.Dataset(
            manifest.models.Dataset(name="survey", resources={"../outside": {}})
        )
        with self.assertRaises(ValueError):
            dataset.resources["../outside"].source("working")
        with self.assertRaises(ValueError):
            _ = dataset.resources["../outside"].working_path
