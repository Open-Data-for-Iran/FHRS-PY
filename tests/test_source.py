import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import fsspec

from fhrs.runtime import Source


class SourceTests(unittest.TestCase):
    def test_glob_expands_files_in_order_and_preserves_connection_options(self):
        root = f"/source-glob-{uuid4().hex}"
        filesystem = fsspec.filesystem("memory")
        filesystem.pipe(f"{root}/U1403.csv", b"urban")
        filesystem.pipe(f"{root}/R1403.csv", b"rural")
        filesystem.pipe(f"{root}/other.csv", b"other")
        filesystem.makedirs(f"{root}/Ufolder.csv")
        self.addCleanup(filesystem.rm, root, recursive=True)
        source = Source(f"{root}/[UR]*.csv", {"protocol": "memory"})
        matches = source.glob()
        self.assertIsInstance(matches, tuple)
        self.assertEqual(
            [match.path for match in matches],
            [f"{root}/R1403.csv", f"{root}/U1403.csv"],
        )
        for match, content in zip(matches, (b"rural", b"urban"), strict=True):
            self.assertEqual(match.storage_options, {"protocol": "memory"})
            with match.open() as stream:
                self.assertEqual(stream.read(), content)
        self.assertEqual(
            Source(f"{root}/missing*.csv", {"protocol": "memory"}).glob(), ()
        )
        self.assertEqual(
            len(Source(f"{root}/other.csv", {"protocol": "memory"}).glob()), 1
        )

    def test_filesystem_and_path_are_initialized_lazily_and_reused(self):
        urlpath = f"memory://source-cache-{uuid4().hex}/missing.csv"
        with patch("fsspec.url_to_fs", wraps=fsspec.url_to_fs) as create:
            source = Source(urlpath)
            equivalent = Source(urlpath)
            self.assertEqual(source.protocol, "memory")
            self.assertEqual(source.to_fsspec(), {"urlpath": urlpath})
            create.assert_not_called()
            self.assertEqual(source.path, "/" + urlpath.removeprefix("memory://"))
            self.assertIs(source.filesystem, fsspec.filesystem("memory"))
            self.assertFalse(source.exists())
            self.assertFalse(source.exists())
            create.assert_called_once_with(urlpath)
            self.assertEqual(source, equivalent)

    def test_local_manifest_exists(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "manifest.yaml"
            source = Source(str(path))
            self.assertFalse(source.exists())
            path.write_text("name: survey", encoding="utf-8")
            self.assertTrue(source.exists())
            path.unlink()
            self.assertFalse(source.exists())

    def test_storage_options_select_filesystem(self):
        path = f"source-check-{uuid4().hex}/manifest.yaml"
        filesystem = fsspec.filesystem("memory")
        source = Source(path, storage_options={"protocol": "memory"})
        self.assertFalse(source.exists())
        filesystem.pipe(path, b"name: survey")
        try:
            self.assertTrue(source.exists())
            self.assertTrue(Source(f"memory://{path}").exists())
        finally:
            filesystem.rm(path)
        self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
