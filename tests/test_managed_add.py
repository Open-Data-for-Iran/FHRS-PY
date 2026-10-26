import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fhrs import manifest, runtime


class ManagedAddTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.dataset = runtime.ManagedDataset(
            manifest.Dataset.model_validate(
                {
                    "name": "survey",
                    "resources": {"pages": {"type": "directory"}, "file": {}},
                    "collections": {
                        "wave": {"resources": {"pages": {"type": "directory"}}}
                    },
                }
            ),
            working_directory=self.root / "work",
        )
        self.pages = self.dataset.resource("pages")

    def test_add_accepts_paths_bytes_and_streams_and_preserves_other_files(self):
        source = self.root / "source.html"
        source.write_bytes(b"page")
        before = self.dataset.manifest.model_dump()
        for index, data in enumerate((source, str(source), b"page", BytesIO(b"page"))):
            result = self.pages.add(f"nested/{index}.html", data)
            self.assertEqual(result, self.root / f"work/pages/nested/{index}.html")
            self.assertEqual(result.read_bytes(), b"page")
        self.assertEqual(len(list((self.root / "work/pages/nested").iterdir())), 4)
        self.assertEqual(before, self.dataset.manifest.model_dump())
        result = self.dataset.resource("wave/pages").add("1.html", b"nested")
        self.assertEqual(result, self.root / "work/wave/pages/1.html")

    def test_add_requires_explicit_overwrite_and_preserves_stream_ownership(self):
        result = self.pages.add("1.html", b"original")
        stream = BytesIO(b"skip-replacement")
        stream.seek(5)
        with self.assertRaises(FileExistsError):
            self.pages.add("1.html", stream)
        self.assertEqual(stream.tell(), 5)
        self.assertEqual(result.read_bytes(), b"original")
        self.pages.add("1.html", stream, overwrite=True)
        self.assertFalse(stream.closed)
        self.assertEqual(result.read_bytes(), b"replacement")

    def test_add_rejects_file_resources_and_invalid_destination_paths(self):
        with self.assertRaises(TypeError):
            self.dataset.resource("file").add("1.html", b"page")
        for path in (
            "",
            ".",
            "..",
            "../escape",
            "a/../../escape",
            "/absolute",
            "C:/absolute",
            "C:relative",
            "a\\b",
            "*.html",
            "a?.html",
            "[ab].html",
            "a:stream",
            "a/../b",
            "a/",
            "a//b",
            "a/./b",
            "bad\0name",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.pages.add(path, b"page")
        self.assertFalse((self.root / "work").exists())

    def test_add_rejects_symlink_escape(self):
        outside = self.root / "outside"
        outside.mkdir()
        directory = self.root / "work/pages"
        directory.mkdir(parents=True)
        try:
            (directory / "linked").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaises(ValueError):
            self.pages.add("linked/escape.html", b"page")
        self.assertEqual(list(outside.iterdir()), [])

    def test_add_failed_write_preserves_existing_files(self):
        class FailingStream(BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("read failed")
                return super().read(2)

        result = self.pages.add("1.html", b"original")
        sibling = self.pages.add("2.html", b"keep")
        with self.assertRaisesRegex(OSError, "read failed"):
            self.pages.add("1.html", FailingStream(b"replacement"), overwrite=True)
        self.assertEqual(result.read_bytes(), b"original")
        self.assertEqual(sibling.read_bytes(), b"keep")
        self.assertEqual(set(result.parent.iterdir()), {result, sibling})

    def test_remove_deletes_only_the_named_file_and_preserves_manifest(self):
        target = self.pages.add("nested/1.html", b"remove")
        sibling = self.pages.add("nested/2.html", b"keep")
        before = self.dataset.manifest.model_dump()
        self.assertIsNone(self.pages.remove("nested/1.html"))
        self.assertFalse(target.exists())
        self.assertEqual(sibling.read_bytes(), b"keep")
        self.assertEqual(before, self.dataset.manifest.model_dump())
        nested = self.dataset.resource("wave/pages")
        target = nested.add("1.html", b"remove")
        nested.remove("1.html")
        self.assertFalse(target.exists())

    def test_remove_rejects_missing_files_directories_and_file_resources(self):
        with self.assertRaises(FileNotFoundError):
            self.pages.remove("missing.html")
        self.assertFalse((self.root / "work").exists())
        with self.assertRaises(TypeError):
            self.dataset.resource("file").remove("1.html")
        child = self.pages.add("nested/1.html", b"keep")
        with self.assertRaises(IsADirectoryError):
            self.pages.remove("nested")
        self.assertEqual(child.read_bytes(), b"keep")

    def test_remove_rejects_unsafe_paths(self):
        outside = self.root / "outside.html"
        outside.write_bytes(b"keep")
        for path in (
            "",
            ".",
            "..",
            "../outside.html",
            "/absolute",
            "C:/absolute",
            "C:relative",
            "a\\b",
            "*.html",
            "a?.html",
            "[ab].html",
            "a:stream",
            "a/../b",
            "a/",
            "a//b",
            "a/./b",
            "bad\0name",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.pages.remove(path)
        self.assertEqual(outside.read_bytes(), b"keep")

    def test_remove_rejects_symlink_escape_and_unlinks_internal_symlink(self):
        outside = self.root / "outside.html"
        outside.write_bytes(b"outside")
        target = self.pages.add("1.html", b"keep")
        link = target.parent / "link.html"
        escape = target.parent / "escape.html"
        try:
            link.symlink_to(target)
            escape.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaises(ValueError):
            self.pages.remove("escape.html")
        self.pages.remove("link.html")
        self.assertFalse(link.is_symlink())
        self.assertEqual(target.read_bytes(), b"keep")
        self.assertEqual(outside.read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()
