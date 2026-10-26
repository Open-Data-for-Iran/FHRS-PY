import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fhrs
from fhrs import runtime
from fhrs.manifest.models import Dataset as DatasetManifest


class ManagedRuntimeTests(unittest.TestCase):
    def make_manifest(self):
        contents = {
            "resources": {
                "raw": {
                    "type": "directory",
                    "locations": [{"storage": "archive", "uri": "raw"}],
                    "members": {"rows": "*.csv"},
                }
            },
            "tables": {"rows": {"resource": "raw#rows", "reader": "csv"}},
        }
        return DatasetManifest.model_validate(
            {
                "name": "survey",
                "storages": {"archive": {"protocol": "memory"}},
                **contents,
                "collections": {
                    "wave": {**contents, "collections": {"nested": contents}},
                },
            }
        )

    def test_managed_graph_inherits_runtime_behavior_and_ownership(self):
        with patch("fsspec.url_to_fs") as connect:
            dataset = runtime.ManagedDataset(self.make_manifest())
            connect.assert_not_called()

        self.assertIsInstance(dataset, runtime.Dataset)
        for name in ("working", "archive"):
            storage = dataset.storage(name)
            self.assertIsInstance(storage, runtime.ManagedStorage)
            self.assertIsInstance(storage, runtime.Storage)
            self.assertIs(storage.dataset, dataset)

        wave = dataset.collection("wave")
        nested = wave.collection("nested")
        for node in (dataset, wave, nested):
            with self.subTest(node=type(node).__name__):
                if node is not dataset:
                    self.assertIsInstance(node, runtime.ManagedCollection)
                    self.assertIsInstance(node, runtime.Collection)
                    self.assertIs(node.dataset, dataset)
                resource = node.resource("raw")
                self.assertIsInstance(resource, runtime.ManagedResource)
                self.assertIsInstance(resource, runtime.Resource)
                self.assertIs(resource.dataset, dataset)
                self.assertIs(resource.parent, node)
                for selector in ("rows", "member:nested/*.csv"):
                    member = resource.member(selector)
                    self.assertIsInstance(member, runtime.ManagedResourceMember)
                    self.assertIsInstance(member, runtime.ResourceMember)
                    self.assertIs(member.resource, resource)
                    self.assertIs(member.dataset, dataset)
                table = node.table("rows")
                self.assertIsInstance(table, runtime.ManagedTable)
                self.assertIsInstance(table, runtime.Table)
                self.assertIs(table.resources[0], resource.member("rows"))
                self.assertIs(table.dataset, dataset)
                self.assertIs(table.parent, node)

        self.assertIs(nested.parent, wave)
        self.assertIs(wave.parent, dataset)
        self.assertIs(dataset.resource("wave/nested/raw"), nested.resource("raw"))
        working = nested.resource("raw").source("working")
        self.assertEqual(
            Path(working.urlpath), dataset.working_directory / "wave/nested/raw"
        )

    def test_plain_dataset_keeps_plain_runtime_objects(self):
        dataset = runtime.Dataset(self.make_manifest())
        self.assertIs(type(dataset.collection("wave")), runtime.Collection)
        self.assertIs(type(dataset.resource("raw")), runtime.Resource)
        self.assertIs(type(dataset.resource("raw#rows")), runtime.ResourceMember)
        self.assertIs(type(dataset.table("rows")), runtime.Table)
        self.assertIs(type(dataset.storage("archive")), runtime.Storage)

    def test_manifest_loaders_select_managed_objects_only_when_requested(self):
        source = Path(__file__).resolve().parents[1] / "examples/manifest-pointers"
        for load in (fhrs.load, runtime.load_manifest):
            for manage in (False, True):
                with self.subTest(loader=load, manage=manage):
                    dataset = load(source, manage=manage, working_directory="work")
                    expected = runtime.ManagedDataset if manage else runtime.Dataset
                    self.assertIs(type(dataset), expected)
                    self.assertEqual(dataset.working_directory, Path("work").resolve())
                    notes = (
                        dataset.collection("waves")
                        .collection("1403")
                        .collection("notes")
                    )
                    collection_type = (
                        runtime.ManagedCollection if manage else runtime.Collection
                    )
                    self.assertIs(type(notes), collection_type)
                    self.assertIs(notes.dataset, dataset)
                    self.assertTrue(notes.source.exists())
            self.assertIs(type(load(source)), runtime.Dataset)

    def test_package_loaders_preserve_declaration_and_select_managed_types(self):
        manifest = DatasetManifest(name="survey")
        setup = SimpleNamespace(
            dataset=manifest, __file__=str(Path("setup.py").resolve())
        )
        for load in (fhrs.load, runtime.load_package):
            for manage in (False, True):
                with (
                    self.subTest(loader=load, manage=manage),
                    patch(
                        "fhrs.runtime.loader.import_module", return_value=setup
                    ) as import_module,
                ):
                    dataset = load(
                        "survey-package", manage=manage, setup_module="custom"
                    )
                    expected = runtime.ManagedDataset if manage else runtime.Dataset
                    self.assertIs(type(dataset), expected)
                    self.assertIsNot(dataset.manifest, manifest)
                    self.assertFalse(hasattr(manifest, "_storage"))
                    import_module.assert_called_once_with("survey_package.custom")


if __name__ == "__main__":
    unittest.main()
