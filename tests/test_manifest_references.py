import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec

from fhrs.manifest import Collection, ManifestReference, load
from fhrs.manifest.loader import (
    _load_internal_collection,
    _resolve_collection,
    _resolve_collection_child,
)


class ManifestReferenceTests(unittest.TestCase):
    def load_collection(self, urlpath, *, storage_options=None):
        collection = _load_internal_collection(
            str(urlpath), storage_options=storage_options
        )
        return _resolve_collection(collection)

    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, path, text):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_load_immediate_children_only(self):
        path = self.write(
            "fhrs.yaml",
            "collections:\n  inline:\n    collections:\n"
            "      grandchild:\n        manifest: missing.yaml\n"
            "  external:\n    manifest: sub/child.yaml\n",
        )
        child_path = self.write(
            "sub/child.yaml",
            "title: Child\ncollections:\n  grandchild:\n    manifest: missing.yaml\n",
        )
        parent = _load_internal_collection(str(path), storage_options=None)
        children = _resolve_collection_child(parent).collections
        self.assertEqual(set(children), {"inline", "external"})
        self.assertEqual(children["external"].title, "Child")
        self.assertEqual(Path(children["external"]._storage["urlpath"]), child_path)
        self.assertEqual(Path(children["inline"]._storage["urlpath"]), path)
        for child in children.values():
            self.assertIsInstance(child.collections["grandchild"], ManifestReference)
        self.assertIs(parent.collections["external"], children["external"])
        self.assertEqual(_resolve_collection_child(Collection()).collections, {})

    def test_load_immediate_children_uses_stored_options(self):
        root = f"/immediate-{uuid4().hex}"
        fs = fsspec.filesystem("memory")
        fs.pipe(f"{root}/child.yaml", b"title: Remote child\n")
        self.addCleanup(fs.rm, root, recursive=True)
        parent = Collection(collections={"child": {"manifest": "child.yaml"}})
        parent._storage = {
            "urlpath": f"{root}/fhrs.yaml",
            "storage_options": {"protocol": "memory"},
        }
        child = _resolve_collection_child(parent).collections["child"]
        self.assertEqual(child.title, "Remote child")
        self.assertEqual(child._storage["storage_options"], {"protocol": "memory"})

    def test_nested_and_inline_references(self):
        root = self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  inline:\n    collections:\n"
            "      wave:\n        manifest: waves/wave.json\n",
        )
        wave = self.write(
            "waves/wave.json",
            '{"title": "Wave", "collections": {"child": {"manifest": "../child.yaml"}}}',
        )
        child = self.write("child.yaml", "title: Child\n")
        for loader in (load, self.load_collection):
            with self.subTest(loader=loader.__name__):
                result = loader(root)
                inline = result.collections["inline"]
                self.assertEqual(Path(inline._storage["urlpath"]), root)
                loaded_wave = inline.collections["wave"]
                self.assertIsInstance(loaded_wave, Collection)
                self.assertEqual(Path(loaded_wave._storage["urlpath"]), wave)
                loaded_child = loaded_wave.collections["child"]
                self.assertEqual(loaded_child.title, "Child")
                self.assertEqual(Path(loaded_child._storage["urlpath"]), child)

    def test_rejects_self_and_indirect_loops(self):
        root = self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  self:\n    manifest: ./fhrs.yaml\n",
        )
        for loader in (load, self.load_collection):
            with (
                self.subTest(loader=loader.__name__),
                self.assertRaisesRegex(ValueError, "[Ll]oop"),
            ):
                loader(root)
        self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  child:\n    manifest: sub/child.yaml\n",
        )
        self.write(
            "sub/child.yaml",
            "collections:\n  inline:\n    collections:\n      back:\n        manifest: ../fhrs.yaml\n",
        )
        with self.assertRaisesRegex(ValueError, "[Ll]oop"):
            load(root)

    def test_shared_file_is_not_a_loop(self):
        root = self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  a:\n    manifest: shared.yaml\n"
            "  b:\n    manifest: shared.yaml\n",
        )
        self.write("shared.yaml", "title: Shared\n")
        result = load(root)
        self.assertEqual(result.collections["a"].title, "Shared")
        self.assertEqual(result.collections["b"].title, "Shared")

    def test_missing_child_is_rejected(self):
        root = self.write(
            "fhrs.yaml",
            "name: survey\ncollections:\n  child:\n    manifest: missing.yaml\n",
        )
        with self.assertRaises(FileNotFoundError):
            load(root)

    def test_remote_references_and_loops(self):
        root = f"/reference-{uuid4().hex}"
        fs = fsspec.filesystem("memory")
        fs.pipe(
            f"{root}/fhrs.yaml",
            b"name: survey\ncollections:\n  child:\n    manifest: sub/child.yaml\n",
        )
        fs.pipe(f"{root}/sub/child.yaml", b"title: Remote child\n")
        self.addCleanup(fs.rm, root, recursive=True)
        for urlpath, options in (
            (f"memory://{root}", {}),
            (root, {"protocol": "memory"}),
        ):
            with self.subTest(urlpath=urlpath):
                child = load(urlpath, storage_options=options).collections["child"]
                self.assertEqual(child.title, "Remote child")
                self.assertTrue(child._storage["urlpath"].endswith("/sub/child.yaml"))
                self.assertEqual(child._storage["storage_options"], options)
        options = {"protocol": "memory"}
        declaration = _load_internal_collection(
            f"{root}/fhrs.yaml", storage_options=options
        )
        options.clear()
        child = _resolve_collection(declaration).collections["child"]
        self.assertEqual(child.title, "Remote child")
        self.assertEqual(child._storage["storage_options"], {"protocol": "memory"})
        fs.pipe(
            f"{root}/sub/child.yaml",
            b"collections:\n  back:\n    manifest: ../fhrs.yaml\n",
        )
        with self.assertRaisesRegex(ValueError, "[Ll]oop"):
            load(f"memory://{root}")


if __name__ == "__main__":
    unittest.main()
