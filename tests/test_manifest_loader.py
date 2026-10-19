import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec
from pydantic import ValidationError
from ruamel.yaml.constructor import DuplicateKeyError

from fhrs.manifest import Collection, Dataset, load
from fhrs.manifest.loader import _load_internal_collection, _resolve_collection


class ManifestLoaderTests(unittest.TestCase):
    def test_dataset_names_reject_path_components(self):
        for name in ("survey/2026", "survey\\2026", "/survey", "\\survey", ".", ".."):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    Dataset(name=name)
                with self.assertRaises(ValidationError):
                    load(self.write("invalid-name.json", json.dumps({"name": name})))

    def test_dataset_names_preserve_ordinary_dots_and_unicode(self):
        for name in ("survey.v2", "survey-2026", "survey_2026", "گزارش"):
            with self.subTest(name=name):
                self.assertEqual(Dataset(name=name).name, name)

    def load_collection(self, urlpath, *, storage_options=None):
        collection = _load_internal_collection(
            str(urlpath), storage_options=storage_options
        )
        return _resolve_collection(collection)

    def test_fhrs_version(self):
        self.assertEqual(load(self.write("default.yaml")).fhrs_version, "0.1")
        path = self.write("versioned.yaml", 'fhrs_version: "0.1"\nname: survey\n')
        manifest = load(path)
        self.assertEqual(manifest.fhrs_version, "0.1")
        self.assertEqual(manifest.model_dump()["fhrs_version"], "0.1")
        with self.assertRaises(ValidationError):
            load(self.write("unsupported.yaml", 'fhrs_version: "9.9"\nname: survey\n'))

    def test_private_storage(self):
        path = self.write("fhrs.yaml")
        for declaration in (load(path), load(self.root), self.load_collection(path)):
            with self.subTest(declaration=type(declaration).__name__):
                self.assertEqual(Path(declaration._storage["urlpath"]), path)
                self.assertEqual(declaration._storage["storage_options"], {})
                self.assertFalse(hasattr(declaration, "_urlpath"))
                self.assertNotIn("_storage", declaration.model_dump())
                self.assertNotIn("_storage", declaration.model_dump_json())
                self.assertNotIn(
                    "_storage", json.dumps(declaration.model_json_schema())
                )

    def test_load_collection_declaration(self):
        self.write(".fhrs/child/.fhrs.yaml", "title: Child\n")
        path = self.write(
            ".fhrs/manifest.yaml",
            "title: Wave 1403\n"
            "resources:\n  data:\n    locations:\n      - uri: data.csv\n"
            "tables:\n  rows:\n    resource: data\n    reader: csv\n"
            "collections:\n  child:\n    manifest: child/.fhrs.yaml\n",
        )
        collection = self.load_collection(path)
        self.assertIsInstance(collection, Collection)
        self.assertNotIsInstance(collection, Dataset)
        self.assertEqual(collection.title, "Wave 1403")
        self.assertEqual(collection.tables["rows"].resource, "data")
        self.assertNotIn("fhrs_version", collection.model_dump())
        self.assertIsInstance(collection.collections["child"], Collection)
        self.assertEqual(collection.collections["child"].title, "Child")

    def test_internal_collection_rejects_format_version(self):
        self.write("wave.yaml", 'fhrs_version: "0.1"\nname: wave\n')
        path = self.write(
            "fhrs.yaml",
            'fhrs_version: "0.1"\nname: survey\n'
            "collections:\n  wave:\n    manifest: wave.yaml\n",
        )
        with self.assertRaises(ValidationError):
            load(path)

    def test_load_collection_uses_collection_validation(self):
        collection = self.load_collection(self.write("fhrs.yaml", "name: wave\n"))
        self.assertEqual(collection.name, "wave")
        self.assertIsNone(self.load_collection(self.write("unnamed.yaml", "{}\n")).name)
        self.assertIsNone(
            self.load_collection(self.write("null.yaml", "name: null\n")).name
        )
        with self.assertRaises(ValidationError):
            self.load_collection(self.write("empty-name.yaml", 'name: ""\n'))
        with self.assertRaises(ValidationError):
            self.load_collection(
                self.write(
                    "invalid.yaml",
                    "tables:\n  rows:\n    resource: missing\n    reader: csv\n",
                )
            )

    def test_load_collection_fsspec_options(self):
        path = f"/collection-loader-{uuid4().hex}/.fhrs.yaml"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(path, b"title: Remote wave\n")
        try:
            collection = self.load_collection(
                path, storage_options={"protocol": "memory"}
            )
            self.assertEqual(collection.title, "Remote wave")
            self.assertEqual(collection._storage["urlpath"], path)
            self.assertEqual(
                collection._storage["storage_options"], {"protocol": "memory"}
            )
        finally:
            filesystem.rm(path)

    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative_path, content="name: survey\n"):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_explicit_manifest_file(self):
        self.write("waves/1403/.fhrs.yaml", "title: Wave\n")
        path = self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  wave:\n    manifest: waves/1403/.fhrs.yaml\n",
        )
        manifest = load(path)
        self.assertIsInstance(manifest, Dataset)
        self.assertEqual(manifest.name, "survey")
        self.assertIsInstance(manifest.collections["wave"], Collection)
        self.assertEqual(manifest.collections["wave"].title, "Wave")

    def test_explicit_files_in_all_layouts(self):
        for index, entry in enumerate(
            ("fhrs.yaml", ".fhrs.yaml", "fhrs/manifest.yaml", ".fhrs/manifest.yaml")
        ):
            with self.subTest(entry=entry):
                path = self.write(f"layout-{index}/{entry}")
                self.assertEqual(load(path).name, "survey")
                self.assertEqual(
                    load(urlpath=self.root / f"layout-{index}").name, "survey"
                )

    def test_directory_is_discovered_and_ambiguity_rejected(self):
        self.write("fhrs.yaml")
        self.assertEqual(load(urlpath=self.root).name, "survey")
        self.write(".fhrs/manifest.yaml", "title: Wave\n")
        with self.assertRaisesRegex(ValueError, "Multiple"):
            load(self.root)
        with self.assertRaises(OSError):
            self.load_collection(urlpath=self.root / ".fhrs")

    def test_explicit_file_selects_declaration(self):
        first = self.write("fhrs.yaml")
        second = self.write(".fhrs/manifest.yaml", "name: other\n")
        self.assertEqual(load(first).name, "survey")
        self.assertEqual(load(second).name, "other")

    def test_missing_or_empty_file_address(self):
        with self.assertRaises(FileNotFoundError):
            load(self.root / "missing.yaml")
        with self.assertRaises(ValueError):
            load("")

    def test_validation_and_duplicate_keys(self):
        with self.assertRaises(ValidationError):
            load(self.write("invalid.yaml", "title: Missing dataset name\n"))
        with self.assertRaises(DuplicateKeyError):
            load(self.write("duplicate.yaml", "name: first\nname: second\n"))
        with self.assertRaises(ValidationError):
            load(self.write("empty.yaml", ""))

    def test_json_manifest(self):
        path = self.write("dataset.json", '{"name": "survey"}')
        self.assertEqual(load(path).name, "survey")

    def test_json_collection(self):
        self.write("child.json", '{"title": "Child"}')
        path = self.write(
            "collection.JSON",
            '{"title": "Wave", "collections": {"child": {"manifest": "child.json"}}}',
        )
        collection = self.load_collection(path)
        self.assertEqual(collection.title, "Wave")
        self.assertIsInstance(collection.collections["child"], Collection)
        self.assertEqual(collection.collections["child"].title, "Child")

    def test_json_rejects_yaml_syntax(self):
        with self.assertRaises(json.JSONDecodeError):
            load(self.write("dataset.json", "name: survey\n"))
        with self.assertRaises(json.JSONDecodeError):
            self.load_collection(self.write("collection.json", "title: Wave\n"))

    def test_json_rejects_duplicate_keys(self):
        for content in (
            '{"name": "first", "name": "second"}',
            '{"name": "survey", "collections": {"child": {"title": "a", "title": "b"}}}',
        ):
            with (
                self.subTest(content=content),
                self.assertRaisesRegex(ValueError, "Duplicate JSON key"),
            ):
                load(self.write("dataset.json", content))

    def test_remote_json_manifest(self):
        path = f"/json-loader-{uuid4().hex}/fhrs.json"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(path, b'{"name": "remote"}')
        try:
            self.assertEqual(load(f"memory://{path}").name, "remote")
        finally:
            filesystem.rm(path)

    def test_fsspec_url_and_options(self):
        root = f"/manifest-loader-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.makedirs(root)
        filesystem.pipe(f"{root}/fhrs.yaml", b"name: remote\n")
        try:
            self.assertEqual(load(f"memory://{root}/fhrs.yaml").name, "remote")
            self.assertEqual(
                load(f"memory://{root}")._storage["urlpath"],
                f"memory://{root}/fhrs.yaml",
            )
            self.assertEqual(load(urlpath=f"memory://{root}").name, "remote")
            self.assertEqual(
                load(urlpath=root, storage_options={"protocol": "memory"}).name,
                "remote",
            )
            self.assertEqual(
                load(f"{root}/fhrs.yaml", storage_options={"protocol": "memory"}).name,
                "remote",
            )
        finally:
            filesystem.rm(f"{root}/fhrs.yaml")
            filesystem.rmdir(root)


if __name__ == "__main__":
    unittest.main()
