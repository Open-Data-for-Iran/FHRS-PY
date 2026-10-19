import unittest
from pathlib import Path
from uuid import uuid4

import fsspec

from fhrs import runtime
from fhrs.manifest import Dataset as DatasetManifest
from fhrs.manifest import load as load_manifest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class RuntimeLoaderTests(unittest.TestCase):
    def test_dataset_builds_its_source(self):
        manifest = load_manifest(EXAMPLES / "basic")
        dataset = runtime.Dataset(manifest)
        self.assertEqual(Path(dataset.source.urlpath), EXAMPLES / "basic" / "fhrs.yaml")
        self.assertEqual(dataset.source.storage_options, {})
        source = dataset.source
        self.assertIs(dataset.source, source)
        override = runtime.Source("other.yaml")
        self.assertIs(runtime.Dataset(manifest, source=override).source, override)
        self.assertIsNone(runtime.Dataset(DatasetManifest(name="manual")).source)

    def test_local_file_and_directory(self):
        manifest_path = EXAMPLES / "basic" / "fhrs.yaml"
        for urlpath in (manifest_path, manifest_path.parent):
            with self.subTest(urlpath=urlpath):
                dataset = runtime.load_manifest(urlpath)
                self.assertIsInstance(dataset, runtime.Dataset)
                self.assertEqual(Path(dataset.source.urlpath), manifest_path)
                self.assertEqual(dataset.source.storage_options, {})
                self.assertTrue(dataset.source.exists())
                for table in dataset.tables.values():
                    self.assertIs(table.dataset, dataset)
                    self.assertIs(
                        table.resources[0], dataset.resources[table.manifest.resource]
                    )

    def test_resolves_manifest_pointers_into_runtime_collections(self):
        dataset = runtime.load_manifest(EXAMPLES / "manifest-pointers")
        waves = dataset.collection("waves")
        wave = waves.collection("1403")
        notes = wave.collection("notes")
        self.assertIsInstance(notes, runtime.Collection)
        self.assertEqual(notes.title, "Shared survey notes")
        self.assertIs(notes.dataset, dataset)
        self.assertIs(notes.parent, wave)
        self.assertIs(notes.resource("readme").parent, notes)
        self.assertIs(waves.source, dataset.source)
        self.assertEqual(
            Path(wave.source.urlpath),
            EXAMPLES / "manifest-pointers" / "waves" / "1403.yaml",
        )
        self.assertEqual(
            Path(notes.source.urlpath),
            EXAMPLES / "manifest-pointers" / "shared" / "notes.json",
        )
        self.assertTrue(wave.source.exists())
        self.assertTrue(notes.source.exists())

    def test_remote_storage_options_are_preserved(self):
        root = f"/runtime-loader-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(
            f"{root}/fhrs.yaml",
            b"name: remote\nstorages:\n  cache:\n    protocol: memory\n"
            b"collections:\n  wave:\n    manifest: sub/child.yaml\n",
        )
        filesystem.pipe(
            f"{root}/sub/child.yaml",
            b"title: Child\ncollections:\n  inline:\n    title: Inline\n",
        )
        self.addCleanup(filesystem.rm, root, recursive=True)
        options = {"protocol": "memory"}
        dataset = runtime.load_manifest(root, storage_options=options)
        options.clear()
        self.assertEqual(dataset.name, "remote")
        self.assertEqual(dataset.source.urlpath, f"{root}/fhrs.yaml")
        self.assertEqual(dataset.source.storage_options, {"protocol": "memory"})
        self.assertTrue(dataset.source.exists())
        self.assertIs(dataset.storage("cache").dataset, dataset)
        wave = dataset.collection("wave")
        self.assertEqual(wave.source.urlpath, f"{root}/sub/child.yaml")
        self.assertEqual(wave.source.storage_options, {"protocol": "memory"})
        self.assertTrue(wave.source.exists())
        self.assertIs(wave.collection("inline").source, dataset.source)


if __name__ == "__main__":
    unittest.main()
