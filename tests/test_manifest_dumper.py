import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec
from ruamel.yaml import YAML

from fhrs import manifest, runtime


class ManifestWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = manifest.Dataset(
            name="survey",
            title="گزارش",
            resources={
                "report": {
                    "type": "file",
                    "size": 123,
                    "locations": [{"uri": "report.pdf"}],
                },
                "parts": {
                    "type": "directory",
                    "locations": [{"uri": "data/"}],
                    "members": {"csv": "*.csv"},
                },
            },
            storages={"web": {"type": "http", "url": "https://example.org/"}},
            collections={
                "metadata": {"title": "Metadata"},
                "waves": {
                    "title": "Annual waves",
                    "collections": {
                        "1402": {"title": "Older"},
                        "1403": {"title": "Latest"},
                    },
                },
            },
        )

    def read(self, path):
        return YAML(typ="safe").load((self.root / path).read_text(encoding="utf-8"))

    def test_dump_uses_model_field_order_including_nested_fields(self):
        dataset = manifest.Dataset(
            name="survey",
            collections={"z": {"name": "wave", "title": "Wave"}, "a": {}},
            resources={
                "z": manifest.Resource(
                    suffix=".csv",
                    locations=[manifest.Location(name="web", uri="data.csv")],
                    type="file",
                ),
                "a": {},
            },
            tables={"data": {"title": "Data", "reader": "csv", "resource": "z"}},
            storages={"web": {"url": "https://example.org/", "type": "http"}},
            title="Survey",
            release="1405-07-28",
            description="Dataset description",
            schema_version="0.1.0",
        )
        for format in ("yaml", "json"):
            with self.subTest(format=format):
                manifest.dump(dataset, self.root, format=format)
                data = self.read(f"manifest.{format}")
                self.assertEqual(
                    list(data),
                    [
                        "fhrs_version",
                        "name",
                        "title",
                        "description",
                        "schema_version",
                        "release",
                        "storages",
                        "resources",
                        "tables",
                        "collections",
                    ],
                )
                self.assertEqual(list(data["collections"]), ["z", "a"])
                self.assertEqual(
                    list(data["collections"]["z"]),
                    ["title", "resources", "tables", "collections", "name"],
                )
                self.assertEqual(list(data["resources"]), ["z", "a"])
                resource = data["resources"]["z"]
                self.assertEqual(list(resource), ["type", "locations", "suffix"])
                self.assertEqual(
                    list(resource["locations"][0]), ["uri", "name", "original"]
                )
                self.assertEqual(
                    list(data["tables"]["data"]), ["resource", "reader", "title"]
                )
                self.assertEqual(
                    list(data["storages"]["web"]),
                    ["protocol", "original", "storage_options", "type", "url"],
                )

    def test_loaded_manifest_uses_model_order_in_linked_and_flat_dumps(self):
        source = self.root / "source.yaml"
        source.write_text(
            "release: '1'\ncollections:\n  wave:\n    name: wave\n"
            "    collections: {}\n    title: Wave\nname: survey\ntitle: Survey\n",
            encoding="utf-8",
        )
        dataset = manifest.load(source)
        for format in ("yaml", "json"):
            with self.subTest(format=format):
                destination = self.root / format
                manifest.dump(
                    dataset,
                    destination,
                    format=format,
                    layout={"wave": f"wave.{format}"},
                )
                root = self.read(f"{format}/manifest.{format}")
                wave = self.read(f"{format}/wave.{format}")
                self.assertEqual(
                    list(root),
                    [
                        "fhrs_version",
                        "name",
                        "title",
                        "release",
                        "storages",
                        "resources",
                        "tables",
                        "collections",
                    ],
                )
                self.assertEqual(
                    list(wave), ["title", "resources", "tables", "collections", "name"]
                )
                manifest.dump(
                    manifest.load(destination / f"manifest.{format}"),
                    destination / "flat",
                    format=format,
                )
                flat = self.read(f"{format}/flat/manifest.{format}")
                self.assertEqual(
                    list(flat),
                    [
                        "fhrs_version",
                        "name",
                        "title",
                        "release",
                        "storages",
                        "resources",
                        "tables",
                        "collections",
                    ],
                )
                self.assertEqual(
                    list(flat["collections"]["wave"]),
                    ["title", "resources", "tables", "collections", "name"],
                )

    def test_storage_alias_uses_canonical_model_field_order(self):
        dataset = manifest.Dataset(
            name="survey",
            storages={"web": {"base_url": "https://example.org/", "type": "http"}},
        )
        manifest.dump(dataset.model_copy(deep=True), self.root)
        storage = self.read("manifest.yaml")["storages"]["web"]
        self.assertEqual(
            list(storage), ["protocol", "original", "storage_options", "type", "url"]
        )
        self.assertNotIn("base_url", storage)

    def test_members_omit_none_and_preserve_explicit_empty_directory_mapping(self):
        dataset = manifest.Dataset(
            name="survey",
            resources={
                "file": {},
                "directory": {"type": "directory"},
                "empty_directory": {"type": "directory", "members": {}},
            },
        )
        for format in ("yaml", "json"):
            with self.subTest(format=format):
                manifest.dump(dataset, self.root, format=format)
                path = f"manifest.{format}"
                resources = self.read(path)["resources"]
                self.assertNotIn("members", resources["file"])
                self.assertNotIn("members", resources["directory"])
                self.assertEqual(resources["empty_directory"]["members"], {})
                self.assertEqual(
                    manifest.load(self.root / path).model_dump(), dataset.model_dump()
                )

    def test_dump_options_loaded_as_defaults_but_not_serialized(self):
        source = self.root / "source.yaml"
        source.write_text(
            "name: survey\ncollections:\n  wave:\n    title: Wave\n"
            "dump_options:\n  format: json\n  layout:\n    wave: wave.json\n",
            encoding="utf-8",
        )
        declaration = manifest.load(source)
        self.assertNotIn("dump_options", declaration.model_dump())
        for index, dataset in enumerate((declaration, runtime.Dataset(declaration))):
            destination = self.root / str(index)
            if isinstance(dataset, runtime.Dataset):
                dataset.dump(destination)
            else:
                manifest.dump(dataset, destination)
            data = json.loads(
                (destination / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("dump_options", data)
            self.assertEqual(data["collections"]["wave"], {"manifest": "wave.json"})
            self.assertTrue((destination / "wave.json").exists())

    def test_dump_options_destination_and_storage_defaults_can_be_overridden(self):
        destination = f"/dump-options-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.makedirs(destination)
        self.addCleanup(filesystem.rm, destination, recursive=True)
        dataset = manifest.Dataset(
            name="survey",
            dump_options={
                "destination": destination,
                "format": "json",
                "layout": {"wave": "wave.json"},
                "storage_options": {"protocol": "memory"},
            },
            collections={"wave": {"title": "Wave"}},
        )
        manifest.dump(dataset)
        self.assertTrue(filesystem.exists(f"{destination}/manifest.json"))
        runtime.Dataset(dataset).dump(
            self.root, format="yaml", layout={}, storage_options={}
        )
        data = self.read("manifest.yaml")
        self.assertNotIn("dump_options", data)
        self.assertEqual(data["collections"]["wave"]["title"], "Wave")
        self.assertEqual(dataset.dump_options.format, "json")

    def test_runtime_dataset_dumps_flat_yaml_by_default(self):
        dataset = runtime.Dataset(
            self.dataset, source=runtime.Source(str(self.root / "source.yaml"))
        )
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            dataset.dump()
        finally:
            os.chdir(previous)
        self.assertEqual(
            manifest.load(self.root / "manifest.yaml").model_dump(),
            self.dataset.model_dump(),
        )
        self.assertEqual(list(self.root.iterdir()), [self.root / "manifest.yaml"])

    def test_runtime_dataset_dumps_linked_json_with_storage_options(self):
        dataset = runtime.Dataset(
            self.dataset, source=runtime.Source(str(self.root / "source.yaml"))
        )
        before = self.dataset.model_dump()
        source = dataset.source
        destination = f"/runtime-dump-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.makedirs(destination)
        self.addCleanup(filesystem.rm, destination, recursive=True)
        dataset.dump(
            destination,
            format="json",
            layout={"waves/1403": "years/latest.json"},
            storage_options={"protocol": "memory"},
        )
        with filesystem.open(f"{destination}/manifest.json", "rt") as stream:
            data = json.load(stream)
        self.assertEqual(
            data["collections"]["waves"]["collections"]["1403"],
            {"manifest": "years/latest.json"},
        )
        self.assertEqual(
            manifest.load(
                f"{destination}/manifest.json", storage_options={"protocol": "memory"}
            ).model_dump(),
            before,
        )
        self.assertEqual(dataset.manifest.model_dump(), before)
        self.assertIs(dataset.source, source)

    def test_default_writes_flat_yaml_in_cwd(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            manifest.dump(self.dataset)
        finally:
            os.chdir(previous)
        data = self.read("manifest.yaml")
        self.assertEqual(
            data["collections"]["waves"]["collections"]["1403"]["title"], "Latest"
        )
        self.assertEqual(list(self.root.iterdir()), [self.root / "manifest.yaml"])
        self.assertEqual(
            manifest.load(self.root / "manifest.yaml").model_dump(),
            self.dataset.model_dump(),
        )

    def test_nested_links_are_relative_to_the_containing_file(self):
        before = self.dataset.model_dump()
        manifest.dump(
            self.dataset,
            self.root,
            layout={
                "waves": "groups/waves.yaml",
                "waves/1403": "years/1403.yaml",
            },
        )
        self.assertEqual(
            self.read("manifest.yaml")["collections"]["waves"],
            {"manifest": "groups/waves.yaml"},
        )
        waves = self.read("groups/waves.yaml")
        self.assertEqual(
            waves["collections"]["1403"], {"manifest": "../years/1403.yaml"}
        )
        self.assertEqual(waves["collections"]["1402"]["title"], "Older")
        self.assertNotIn("fhrs_version", waves)
        self.assertEqual(self.read("years/1403.yaml")["title"], "Latest")
        self.assertEqual(
            manifest.load(self.root / "manifest.yaml").model_dump(), before
        )
        self.assertEqual(self.dataset.model_dump(), before)

    def test_json_and_link_below_an_inline_collection(self):
        manifest.dump(
            self.dataset,
            self.root,
            format="json",
            layout={"waves/1403": "years/latest.json"},
        )
        data = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "گزارش")
        self.assertEqual(
            data["collections"]["waves"]["collections"]["1403"],
            {"manifest": "years/latest.json"},
        )
        self.assertEqual(
            manifest.load(self.root / "manifest.json").model_dump(),
            self.dataset.model_dump(),
        )

    def test_remote_destination(self):
        destination = f"memory://writer-{uuid4().hex}/.fhrs"
        filesystem, path = fsspec.url_to_fs(destination)
        manifest.dump(
            self.dataset,
            destination,
            storage_options={},
            layout={"waves/1403": "waves/1403.yaml"},
        )
        self.addCleanup(filesystem.rm, path, recursive=True)
        self.assertEqual(
            manifest.load(destination).model_dump(), self.dataset.model_dump()
        )

    def test_loaded_linked_manifest_can_be_dumped_flat(self):
        manifest.dump(
            self.dataset, self.root / ".fhrs", layout={"waves/1403": "waves/1403.yaml"}
        )
        loaded = manifest.load(self.root / ".fhrs")
        manifest.dump(loaded, self.root / "flat")
        text = (self.root / "flat/manifest.yaml").read_text(encoding="utf-8")
        self.assertNotIn("_storage", text)
        self.assertEqual(
            manifest.load(self.root / "flat/manifest.yaml").model_dump(),
            self.dataset.model_dump(),
        )

    def test_invalid_layout_fails_before_creating_output(self):
        layouts = [
            {"missing": "missing.yaml"},
            {"waves/1404": "missing.yaml"},
            {"waves": "manifest.yaml"},
            {"waves": "same.yaml", "metadata": "same.yaml"},
            {"waves": "a.yaml", "metadata": "a.yaml/metadata.yaml"},
            {"waves": "../outside.yaml"},
            {"waves": "/absolute.yaml"},
            {"waves": "C:/absolute.yaml"},
            {"waves": "bad\\path.yaml"},
            {"waves": "wrong.json"},
        ]
        for layout in layouts:
            with self.subTest(layout=layout):
                with self.assertRaises(ValueError):
                    manifest.dump(self.dataset, self.root / "output", layout=layout)
                self.assertFalse((self.root / "output").exists())

    def test_unsupported_format_and_unresolved_references_fail_before_writing(self):
        with self.assertRaises(ValueError):
            manifest.dump(self.dataset, self.root / "output", format="toml")
        unresolved = manifest.Dataset(
            name="survey", collections={"wave": {"manifest": "wave.yaml"}}
        )
        with self.assertRaises(TypeError):
            manifest.dump(unresolved, self.root / "output")
        self.assertFalse((self.root / "output").exists())
