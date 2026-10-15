import unittest
from dataclasses import FrozenInstanceError

from pydantic import ValidationError

from fhrs import runtime
from fhrs.manifest import Collection as CollectionManifest
from fhrs.manifest import Dataset as DatasetManifest
from fhrs.manifest import ManifestReference


class RuntimeCollectionTests(unittest.TestCase):
    def test_tables_bind_single_or_multiple_resources_in_declared_order(self):
        for reference, expected in (
            ("urban", ["urban"]),
            (["rural", "urban"], ["rural", "urban"]),
        ):
            with self.subTest(reference=reference):
                contents = {
                    "resources": {
                        name: {"locations": [{"uri": f"{name}.csv"}]}
                        for name in ("urban", "rural")
                    },
                    "tables": {"rows": {"resource": reference, "reader": "csv"}},
                }
                manifest = DatasetManifest.model_validate(
                    {"name": "survey", **contents, "collections": {"wave": contents}}
                )
                dataset = runtime.Dataset(
                    manifest, runtime.Source("catalog/manifest.yaml")
                )
                for node in (dataset, dataset.collection("wave")):
                    table = node.table("rows")
                    self.assertIsInstance(table.resources, list)
                    self.assertEqual([r.name for r in table.resources], expected)
                    for resource, name in zip(table.resources, expected, strict=True):
                        self.assertIs(resource, node.resource(name))
                    self.assertIs(table.parent, node)
                    self.assertIs(table.dataset, dataset)
        for reference in ([], [""], [1], ["urban", "missing"]):
            with self.subTest(reference=reference), self.assertRaises(ValidationError):
                DatasetManifest.model_validate(
                    {
                        "name": "survey",
                        "resources": {"urban": {"locations": [{"uri": "urban.csv"}]}},
                        "tables": {"rows": {"resource": reference, "reader": "csv"}},
                    }
                )

    def test_runtime_base_preserves_frozen_slots(self):
        dataset = self.make_dataset()
        objects = (
            dataset,
            dataset.collection("wave"),
            dataset.resource("data"),
            dataset.table("rows"),
            dataset.storage("archive"),
            dataset.source,
        )
        for obj in objects:
            with self.subTest(runtime_type=type(obj).__name__):
                self.assertIsInstance(obj, runtime.BaseRuntime)
                self.assertFalse(hasattr(obj, "__dict__"))
                attribute = "urlpath" if isinstance(obj, runtime.Source) else "manifest"
                with self.assertRaises(FrozenInstanceError):
                    setattr(obj, attribute, getattr(obj, attribute))

    def make_dataset(self):
        contents = {
            "resources": {"data": {"locations": [{"uri": "data.csv"}]}},
            "tables": {"rows": {"resource": "data", "reader": "csv"}},
        }
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "storages": {"archive": {"bucket": "datasets"}},
                **contents,
                "collections": {
                    "wave": {
                        **contents,
                        "collections": {"nested": contents},
                    },
                    "external": {"manifest": "other/manifest.yaml"},
                },
            }
        )
        return runtime.Dataset(manifest, runtime.Source("catalog/manifest.yaml"))

    def test_shared_base(self):
        dataset = self.make_dataset()
        self.assertIsInstance(dataset, runtime.BaseCollection)
        self.assertIsInstance(dataset.collection("wave"), runtime.BaseCollection)

    def test_owner_context_and_local_table_resolution(self):
        dataset = self.make_dataset()
        wave = dataset.collection("wave")
        nested = wave.collection("nested")
        for node, parent in ((wave, dataset), (nested, wave)):
            self.assertIs(node.parent, parent)
            self.assertIs(node.dataset, dataset)
            self.assertIs(node.source, dataset.source)
            self.assertIs(node.resource("data").parent, node)
            self.assertIs(node.resource("data").dataset, dataset)
            self.assertIs(node.table("rows").resources[0], node.resource("data"))
            self.assertIs(node.table("rows").parent, node)
            self.assertIs(node.table("rows").dataset, dataset)
        self.assertIs(dataset.resource("data").parent, dataset)
        self.assertIs(dataset.resource("data").dataset, dataset)
        self.assertIs(dataset.table("rows").parent, dataset)
        self.assertIs(dataset.table("rows").dataset, dataset)
        self.assertIs(dataset.table("rows").resources[0], dataset.resource("data"))
        self.assertIsNot(wave.resource("data"), dataset.resource("data"))
        self.assertIs(dataset.storage("archive").dataset, dataset)

    def test_reference_and_read_only_snapshot(self):
        dataset = self.make_dataset()
        self.assertIsInstance(dataset.collection("external"), ManifestReference)
        self.assertIs(
            dataset.collection("external"), dataset.manifest.collections["external"]
        )
        wave = dataset.collection("wave")
        for node in (dataset, wave):
            for mapping in (node.resources, node.tables, node.collections):
                with self.assertRaises(TypeError):
                    mapping["new"] = None
            for lookup in (node.resource, node.table, node.collection):
                with self.assertRaises(KeyError):
                    lookup("missing")
        dataset.manifest.resources["later"] = dataset.manifest.resources["data"]
        self.assertNotIn("later", dataset.resources)

    def test_attached_collection_constructor(self):
        dataset = self.make_dataset()
        source = runtime.Source("standalone.yaml")
        collection = runtime.Collection(
            CollectionManifest(title="Attached"), "empty", dataset, dataset, source
        )
        self.assertEqual(collection.title, "Attached")
        self.assertIs(collection.source, source)
        self.assertIs(collection.dataset, dataset)
        self.assertIs(collection.parent, dataset)
        self.assertEqual(collection.resources, {})
        self.assertEqual(collection.tables, {})
        self.assertEqual(collection.collections, {})

    def test_owners_are_required(self):
        dataset = self.make_dataset()
        for constructor, manifest in (
            (runtime.Collection, CollectionManifest()),
            (runtime.Resource, dataset.manifest.resources["data"]),
        ):
            for owners in ({}, {"dataset": dataset}, {"parent": dataset}):
                with (
                    self.subTest(constructor=constructor, owners=list(owners)),
                    self.assertRaises(TypeError),
                ):
                    constructor(manifest, name="unbound", **owners)

        table_manifest = dataset.manifest.tables["rows"]
        with self.assertRaises(TypeError):
            runtime.Table(table_manifest, name="unbound")


if __name__ == "__main__":
    unittest.main()
