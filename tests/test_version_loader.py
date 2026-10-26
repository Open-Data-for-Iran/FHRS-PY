import json
import unittest
from uuid import uuid4

import fsspec

import fhrs
from fhrs import manifest, runtime


class VersionLoaderTests(unittest.TestCase):
    def setUp(self):
        self.root = f"/versions-{uuid4().hex}"
        self.fs = fsspec.filesystem("memory")
        self.addCleanup(self.fs.rm, self.root, recursive=True)
        self.write("manifest.json", {"name": "current"})

    def write(self, path, value):
        self.fs.pipe(f"{self.root}/{path}", json.dumps(value).encode())

    @property
    def path(self):
        return f"memory://{self.root}/manifest.json"

    def test_default_load_does_not_read_indexes_or_version_manifests(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {"missing": {"manifest": "missing.json"}},
                    "indexes": ["missing-index.json"],
                },
            },
        )
        self.assertEqual(manifest.load(self.path).name, "current")

    def test_combines_indexes_without_opening_version_manifests(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {"inline": {"manifest": "missing.json"}},
                    "indexes": ["indexes/a.json", "indexes/b.yaml"],
                },
            },
        )
        self.write("indexes/a.json", {"a": {"manifest": "../a.json"}})
        self.fs.pipe(f"{self.root}/indexes/b.yaml", b"b:\n  manifest: ../b.json\n")
        index = manifest.load_versions(self.path)
        self.assertEqual(set(index.root), {"inline", "a", "b"})
        self.assertEqual(index.root["a"].manifest, "../a.json")

    def test_selects_relative_version_and_preserves_its_source(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {"indexes": ["indexes/a.json"]},
            },
        )
        self.write(
            "indexes/a.json", {"1.0@001": {"manifest": "../release/manifest.json"}}
        )
        self.write(
            "release/manifest.json",
            {
                "name": "fixed",
                "collections": {"wave": {"manifest": "wave.json"}},
                "resources": {"rows": {"locations": [{"uri": "rows.txt"}]}},
                "versions": {"indexes": ["do-not-read.json"]},
            },
        )
        self.write("release/wave.json", {"title": "Fixed wave"})
        self.fs.pipe(f"{self.root}/release/rows.txt", b"fixed bytes")
        for loader in (manifest.load, runtime.load_manifest, fhrs.load):
            with self.subTest(loader=loader):
                fixed = loader(self.path, version="1.0@001")
                self.assertEqual(fixed.name, "fixed")
                if isinstance(fixed, runtime.Dataset):
                    with fixed.resource("rows").source().open() as stream:
                        self.assertEqual(stream.read(), b"fixed bytes")
                else:
                    self.assertEqual(fixed.collections["wave"].title, "Fixed wave")

    def test_duplicate_identifiers_are_rejected(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {"same": {"manifest": "one.json"}},
                    "indexes": ["index.json"],
                },
            },
        )
        self.write("index.json", {"same": {"manifest": "two.json"}})
        with self.assertRaisesRegex(ValueError, "Duplicate version.*same"):
            manifest.load_versions(self.path)

    def test_missing_index_and_missing_selected_manifest_raise(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {"indexes": ["missing.json"]},
            },
        )
        with self.assertRaises(FileNotFoundError):
            manifest.load_versions(self.path)
        self.write("missing.json", {"one": {"manifest": "absent.json"}})
        self.assertEqual(set(manifest.load_versions(self.path).root), {"one"})
        with self.assertRaises(FileNotFoundError):
            manifest.load(self.path, version="one")

    def test_inline_selection_and_duplicates_across_indexes(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {"one": {"manifest": "fixed.json"}},
                    "indexes": ["a.json", "b.json"],
                },
            },
        )
        self.write("a.json", {"two": {"manifest": "unselected.json"}})
        self.write("b.json", {})
        self.write("fixed.json", {"name": "fixed"})
        fixed = runtime.load_manifest(self.path, version="one", manage=True)
        self.assertIsInstance(fixed, runtime.ManagedDataset)
        self.assertEqual(fixed.name, "fixed")
        self.write("b.json", {"two": {"manifest": "another.json"}})
        with self.assertRaisesRegex(ValueError, "Duplicate version.*two"):
            manifest.load_versions(self.path)

    def test_missing_version_raises_key_error_and_no_versions_is_empty(self):
        self.assertEqual(manifest.load_versions(self.path).root, {})
        with self.assertRaises(KeyError):
            manifest.load(self.path, version="unknown")

    def test_reference_options_select_backend_and_preserve_connection(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {"indexes": ["indexes/a.json"]},
            },
        )
        self.write(
            "indexes/a.json",
            {
                "remote": {
                    "manifest": f"memory://{self.root}/remote.json",
                    "storage_options": {"marker": "remote"},
                },
                "explicit": {
                    "manifest": f"{self.root}/remote.json",
                    "storage_options": {"protocol": "memory", "marker": "explicit"},
                },
                "relative": {
                    "manifest": "../remote.json",
                    "storage_options": {"marker": "relative"},
                },
            },
        )
        self.write("remote.json", {"name": "remote"})
        for version in ("remote", "explicit", "relative"):
            loaded = manifest.load(
                self.path, version=version, storage_options={"marker": "main"}
            )
            self.assertEqual(loaded.name, "remote")
            expected = {"marker": version}
            if version == "explicit":
                expected["protocol"] = "memory"
            self.assertEqual(loaded._storage["storage_options"], expected)

    def test_absolute_reference_does_not_inherit_main_connection_options(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {
                        "remote": {"manifest": f"memory://{self.root}/remote.json"},
                    }
                },
            },
        )
        self.write("remote.json", {"name": "remote"})
        loaded = manifest.load(
            self.path, version="remote", storage_options={"marker": "main"}
        )
        self.assertEqual(loaded._storage["storage_options"], {})

    def test_relative_reference_inherits_options_unless_explicitly_replaced(self):
        self.write(
            "manifest.json",
            {
                "name": "current",
                "versions": {
                    "entries": {
                        "inherited": {"manifest": "fixed.json"},
                        "replaced": {"manifest": "fixed.json", "storage_options": {}},
                    }
                },
            },
        )
        self.write("fixed.json", {"name": "fixed"})
        inherited = manifest.load(
            self.path, version="inherited", storage_options={"marker": "main"}
        )
        replaced = manifest.load(
            self.path, version="replaced", storage_options={"marker": "main"}
        )
        self.assertEqual(inherited._storage["storage_options"], {"marker": "main"})
        self.assertEqual(replaced._storage["storage_options"], {})
