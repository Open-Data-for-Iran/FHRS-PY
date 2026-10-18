import unittest
from dataclasses import FrozenInstanceError

from pydantic import ValidationError

from fhrs import runtime
from fhrs.manifest import Collection as CollectionManifest
from fhrs.manifest import Dataset as DatasetManifest
from fhrs.manifest import ManifestReference


class RuntimeCollectionTests(unittest.TestCase):
    def test_resource_key_is_its_dataset_relative_lookup_path(self):
        resource = {"locations": [{"uri": "https://example.org/download?id=1"}]}
        dataset = runtime.Dataset(
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "resources": {"report": resource},
                    "collections": {
                        "waves": {
                            "name": "Annual waves",
                            "collections": {
                                "1403": {
                                    "name": "Report 1403",
                                    "resources": {"report": resource},
                                }
                            },
                        }
                    },
                }
            )
        )
        for key in ("report", "waves/1403/report"):
            with self.subTest(key=key):
                item = dataset.resource(key)
                self.assertEqual(item.key, key)
                self.assertIs(dataset.resource(item.key), item)

    def test_resource_lookup_traverses_paths_before_resolving_members(self):
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "collections": {
                    "waves": {
                        "collections": {
                            "1403": {
                                "resources": {
                                    "raw": {
                                        "type": "directory",
                                        "locations": [{"uri": "memory://data/1403/"}],
                                        "members": {"households": "nested/01.csv"},
                                    }
                                },
                            }
                        }
                    }
                },
            }
        )
        dataset = runtime.Dataset(manifest)
        waves = dataset.collection("waves")
        wave = waves.collection("1403")
        raw = wave.resource("raw")
        self.assertIs(dataset.resource("waves/1403/raw"), raw)
        self.assertIs(waves.resource("1403/raw"), raw)
        self.assertIs(
            dataset.resource("waves/1403/raw#households"), raw.member("households")
        )
        inline = dataset.resource("waves/1403/raw#member:nested/*.csv")
        self.assertIs(inline.resource, raw)
        self.assertEqual(inline.pattern, "nested/*.csv")
        self.assertEqual(inline.sources[0].urlpath, "memory://data/1403/nested/*.csv")
        for path in (
            "missing/raw",
            "waves/1403/missing",
            "waves//raw",
            "waves/1403/raw#missing",
        ):
            with self.subTest(path=path), self.assertRaises(KeyError):
                dataset.resource(path)
        with self.assertRaisesRegex(TypeError, "unresolved"):
            self.make_dataset().resource("external/data")

    def test_table_lookup_traverses_collection_paths(self):
        dataset = self.make_dataset()
        wave = dataset.collection("wave")
        nested = wave.collection("nested")
        self.assertIs(dataset.table("wave/rows"), wave.table("rows"))
        self.assertIs(dataset.table("wave/nested/rows"), nested.table("rows"))
        self.assertIs(wave.table("nested/rows"), nested.table("rows"))
        self.assertIs(dataset.table("rows"), dataset.tables["rows"])
        for path in (
            "missing/rows",
            "wave/missing/rows",
            "wave/missing",
            "wave//rows",
            "wave/",
        ):
            with self.subTest(path=path), self.assertRaises(KeyError):
                dataset.table(path)
        with self.assertRaisesRegex(TypeError, "unresolved"):
            dataset.table("external/rows")

    def test_tables_bind_resources_and_members_in_order_with_owner_context(self):
        contents = {
            "resources": {
                "raw": {
                    "type": "directory",
                    "locations": [{"uri": "memory://tables/data/"}],
                    "members": {"households": "01.csv"},
                },
                "standalone": {"locations": [{"uri": "memory://tables/other.csv"}]},
            },
            "tables": {
                "declared": {"resource": "raw#households", "reader": "csv"},
                "inline": {"resource": "raw#member:nested/*.csv", "reader": "csv"},
                "mixed": {
                    "resource": ["raw#households", "standalone", "raw#member:*.csv"],
                    "reader": "csv",
                },
            },
        }
        dataset = runtime.Dataset(
            DatasetManifest.model_validate(
                {"name": "survey", **contents, "collections": {"wave": contents}}
            )
        )
        for node in (dataset, dataset.collection("wave")):
            with self.subTest(node=type(node).__name__):
                resource = node.resource("raw")
                declared = node.table("declared").resources[0]
                self.assertIs(declared, resource.member("households"))
                self.assertIs(node.resource("raw#households"), declared)
                inline = node.table("inline").resources[0]
                self.assertIsInstance(inline, runtime.ResourceMember)
                self.assertIs(inline.resource, resource)
                self.assertEqual(inline.pattern, "nested/*.csv")
                mixed = node.table("mixed").resources
                self.assertIs(mixed[0], declared)
                self.assertIs(mixed[1], node.resource("standalone"))
                self.assertEqual(mixed[2].pattern, "*.csv")
                for table in node.tables.values():
                    self.assertIs(table.dataset, dataset)
                    self.assertIs(table.parent, node)
                self.assertEqual(set(resource.members), {"households"})

    def test_invalid_table_member_references_are_rejected(self):
        for reference, error in (
            ("missing#member:*.csv", ValidationError),
            ("raw#unknown", KeyError),
            ("raw#", KeyError),
            ("raw#member:", ValueError),
            ("raw#member:../*.csv", ValueError),
            ("file#member:*.csv", ValueError),
        ):
            with self.subTest(reference=reference), self.assertRaises(error):
                runtime.Dataset(
                    DatasetManifest.model_validate(
                        {
                            "name": "survey",
                            "resources": {
                                "raw": {
                                    "type": "directory",
                                    "locations": [{"uri": "memory://data/"}],
                                },
                                "file": {"locations": [{"uri": "memory://data.csv"}]},
                            },
                            "tables": {
                                "rows": {"resource": reference, "reader": "csv"}
                            },
                        }
                    )
                )

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
