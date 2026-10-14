import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fsspec

from fhrs.manifest import discover


class ManifestDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_file_is_returned_unchanged(self):
        path = self.root / "custom.yaml"
        path.touch()
        self.assertEqual(discover(path), str(path))

    def test_directory_layouts(self):
        for entry in ("fhrs", ".fhrs", "fhrs/manifest", ".fhrs/manifest"):
            for suffix in ("yaml", "yml", "json"):
                with self.subTest(entry=entry, suffix=suffix):
                    path = self.root / f"{entry}.{suffix}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                    self.assertEqual(Path(discover(self.root)), path)
                    if path.parent.name in ("fhrs", ".fhrs"):
                        self.assertEqual(Path(discover(path.parent)), path)
                    path.unlink()

    def test_missing_and_ambiguous_entries(self):
        with self.assertRaises(FileNotFoundError):
            discover(self.root / "missing")
        with self.assertRaises(FileNotFoundError):
            discover(self.root)
        (self.root / "fhrs.yaml").touch()
        (self.root / ".fhrs.json").touch()
        with self.assertRaisesRegex(ValueError, "Multiple"):
            discover(self.root)

    def test_does_not_search_child_datasets(self):
        child = self.root / "child"
        child.mkdir()
        (child / "fhrs.yaml").touch()
        with self.assertRaises(FileNotFoundError):
            discover(self.root)

    def test_remote_paths_and_storage_options(self):
        root = f"/discovery-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(f"{root}/.fhrs/manifest.json", b"{}")
        self.addCleanup(filesystem.rm, root, recursive=True)
        url = f"memory://{root}"
        path = discover(url)
        self.assertEqual(path, f"{url}/.fhrs/manifest.json")
        self.assertEqual(discover(path), path)
        self.assertEqual(
            discover(root, storage_options={"protocol": "memory"}),
            f"{root}/.fhrs/manifest.json",
        )


if __name__ == "__main__":
    unittest.main()
