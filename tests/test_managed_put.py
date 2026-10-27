import os
import shutil
import stat
import unittest
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fhrs import manifest, runtime


class ManagedPutTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.local = self.root / "local"
        self.work = self.local / "workspace"
        self.dataset = runtime.ManagedDataset(
            manifest.models.Dataset.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "report": {
                            "suffix": ".csv",
                            "locations": [{"name": "primary", "uri": "memory://other"}],
                        },
                        "raw": {},
                        "parts": {"type": "directory"},
                    },
                    "collections": {
                        "wave": {"resources": {"archive": {"suffix": ".tar.gz"}}}
                    },
                }
            ),
            local_directory=self.local,
        )
        self.resource = self.dataset.resource("report")
        self.destination = self.work / "report.csv"

    def test_accepts_local_paths_bytes_and_binary_streams(self):
        content = b"id,value\n1,10\n\x00\xff"
        path = self.root / "input.bin"
        path.write_bytes(content)
        before = self.dataset.manifest.model_dump()
        sources = self.resource.sources
        for data in (path, str(path), content, BytesIO(content)):
            with self.subTest(input_type=type(data).__name__):
                result = self.resource.put(data)
                self.assertEqual(result, self.destination)
                self.assertEqual(result.read_bytes(), content)
                result.unlink()
        self.assertEqual(self.dataset.manifest.model_dump(), before)
        self.assertIs(self.resource.sources, sources)
        self.assertEqual(self.resource.source("primary").urlpath, "memory://other")
        self.assertEqual(Path(self.resource.source("local").urlpath), self.destination)

    def test_nested_paths_use_declared_suffix_and_create_parent_directories(self):
        resource = self.dataset.resource("wave/archive")
        destination = resource.put(b"archive")
        self.assertEqual(destination, self.work / "wave/archive.tar.gz")
        self.assertEqual(destination.read_bytes(), b"archive")
        self.assertEqual(self.dataset.resource("raw").put(b""), self.work / "raw")
        self.assertEqual((self.work / "raw").read_bytes(), b"")

    def test_caller_streams_stay_open_and_read_from_current_position(self):
        path = self.root / "input.bin"
        path.write_bytes(b"skip-content")
        with path.open("rb") as file_stream:
            for stream in (BytesIO(b"skip-content"), file_stream):
                stream.seek(5)
                self.resource.put(stream, overwrite=True)
                self.assertFalse(stream.closed)
                self.assertEqual(stream.tell(), len(b"skip-content"))
                self.assertEqual(self.destination.read_bytes(), b"content")

    def test_overwrite_is_explicit_and_rejection_does_not_consume_input(self):
        self.resource.put(b"original")
        stream = BytesIO(b"replacement")
        with self.assertRaises(FileExistsError):
            self.resource.put(stream)
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(self.destination.read_bytes(), b"original")
        self.assertEqual(list(self.work.iterdir()), [self.destination])
        self.resource.put(stream, overwrite=True)
        self.assertEqual(self.destination.read_bytes(), b"replacement")

    def test_read_failure_preserves_destination_and_removes_temporary_file(self):
        class FailingStream(BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("read failed")
                return super().read(3)

        for exists in (False, True):
            with self.subTest(existing_destination=exists):
                if exists:
                    self.resource.put(b"original")
                stream = FailingStream(b"replacement")
                with self.assertRaisesRegex(OSError, "read failed"):
                    self.resource.put(stream, overwrite=True)
                self.assertFalse(stream.closed)
                expected = [self.destination] if exists else []
                self.assertEqual(list(self.work.iterdir()), expected)
                if exists:
                    self.assertEqual(self.destination.read_bytes(), b"original")

    def test_publish_failure_preserves_destination_and_cleans_up(self):
        self.resource.put(b"original")
        with (
            patch("fhrs._utils.put.os.replace", side_effect=OSError("publish failed")),
            self.assertRaisesRegex(OSError, "publish failed"),
        ):
            self.resource.put(b"replacement", overwrite=True)
        self.assertEqual(self.destination.read_bytes(), b"original")
        self.assertEqual(list(self.work.iterdir()), [self.destination])

    def test_destination_created_during_copy_is_not_overwritten(self):
        copy = shutil.copyfileobj

        def copy_and_create_destination(source, target):
            copy(source, target)
            self.destination.write_bytes(b"created concurrently")

        with (
            patch("fhrs._utils.put.shutil.copyfileobj", copy_and_create_destination),
            self.assertRaises(FileExistsError),
        ):
            self.resource.put(b"replacement")
        self.assertEqual(self.destination.read_bytes(), b"created concurrently")
        self.assertEqual(list(self.work.iterdir()), [self.destination])

    def test_invalid_inputs_do_not_leave_files(self):
        for data, error in (
            (self.root / "missing", FileNotFoundError),
            (self.root, IsADirectoryError),
            (123, TypeError),
            (StringIO("text"), TypeError),
        ):
            with self.subTest(data=data), self.assertRaises(error):
                self.resource.put(data)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.work.iterdir()), [])
        with self.assertRaises(TypeError):
            self.dataset.resource("parts").put(b"directory")
        self.assertFalse((self.work / "parts").exists())

    def test_rejects_destination_outside_local_storage(self):
        dataset = runtime.ManagedDataset(
            manifest.models.Dataset(name="survey", resources={"../outside": {}}),
            local_directory=self.local,
        )
        with self.assertRaises(ValueError):
            dataset.resources["../outside"].put(b"content")
        self.assertFalse((self.root / "outside").exists())
        self.assertFalse(self.work.exists())

    def test_can_copy_from_destination_itself_without_truncating_it(self):
        self.resource.put(b"original")
        self.resource.put(self.destination, overwrite=True)
        self.assertEqual(self.destination.read_bytes(), b"original")
        self.assertEqual(list(self.work.iterdir()), [self.destination])

    def make_directory(self):
        source = self.root / "downloaded"
        (source / "nested").mkdir(parents=True)
        (source / "empty").mkdir()
        (source / "a.csv").write_bytes(b"first")
        (source / "nested/b.csv").write_bytes(b"second")
        return source

    def test_directory_copies_contents_and_preserves_nested_and_empty_directories(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        before = self.dataset.manifest.model_dump()
        for data in (source, str(source)):
            with self.subTest(input_type=type(data).__name__):
                destination = resource.put(data, overwrite=True)
                self.assertEqual(destination, self.work / "parts")
                self.assertEqual((destination / "a.csv").read_bytes(), b"first")
                self.assertEqual((destination / "nested/b.csv").read_bytes(), b"second")
                self.assertTrue((destination / "empty").is_dir())
                self.assertFalse((destination / source.name).exists())
                self.assertEqual((source / "a.csv").read_bytes(), b"first")
        self.assertEqual(self.dataset.manifest.model_dump(), before)
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_overwrite_replaces_contents_instead_of_merging(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        (destination / "stale").mkdir()
        (destination / "stale/old.csv").write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            resource.put(source)
        self.assertTrue((destination / "stale/old.csv").exists())
        resource.put(source, overwrite=True)
        self.assertFalse((destination / "stale").exists())
        self.assertEqual((destination / "nested/b.csv").read_bytes(), b"second")
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_rejects_non_directory_inputs(self):
        file = self.root / "input.zip"
        file.write_bytes(b"archive")
        resource = self.dataset.resource("parts")
        stream = BytesIO(b"content")
        for data, error in (
            (file, NotADirectoryError),
            (self.root / "missing", FileNotFoundError),
            (b"content", TypeError),
            (stream, TypeError),
        ):
            with self.subTest(data=data), self.assertRaises(error):
                resource.put(data)
        self.assertFalse(stream.closed)
        self.assertEqual(stream.tell(), 0)
        self.assertFalse(self.work.exists())

    def test_directory_copy_failure_preserves_destination_and_cleans_up(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")

        def fail_copy(source, destination):
            destination.mkdir()
            (destination / "partial").write_bytes(b"partial")
            raise OSError("copy failed")

        for exists in (False, True):
            with self.subTest(existing_destination=exists):
                if exists:
                    resource.put(source)
                with (
                    patch("fhrs._utils.put.shutil.copytree", fail_copy),
                    self.assertRaisesRegex(OSError, "copy failed"),
                ):
                    resource.put(source, overwrite=True)
                destination = self.work / "parts"
                self.assertEqual(
                    list(self.work.iterdir()), [destination] if exists else []
                )
                if exists:
                    self.assertEqual((destination / "a.csv").read_bytes(), b"first")

    def test_directory_publish_failure_restores_original_directory(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        (destination / "original").write_bytes(b"keep")
        rename = os.rename
        calls = 0

        def fail_publication(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("publish failed")
            return rename(src, dst)

        with (
            patch("fhrs._utils.put.os.rename", fail_publication),
            self.assertRaisesRegex(OSError, "publish failed"),
        ):
            resource.put(source, overwrite=True)
        self.assertEqual((destination / "original").read_bytes(), b"keep")
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_rejects_destination_inside_source_but_allows_self_copy(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        resource.put(destination, overwrite=True)
        self.assertEqual((destination / "a.csv").read_bytes(), b"first")
        with self.assertRaises(ValueError):
            resource.put(self.work, overwrite=True)
        self.assertEqual((destination / "a.csv").read_bytes(), b"first")
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_created_during_copy_is_not_overwritten(self):
        source = self.root / "downloaded"
        source.mkdir()
        (source / "a.csv").write_bytes(b"content")
        destination = self.work / "parts"
        copy = shutil.copytree

        def copy_and_create_destination(src, dst):
            result = copy(src, dst)
            destination.mkdir()
            return result

        with (
            patch("fhrs._utils.put.shutil.copytree", copy_and_create_destination),
            self.assertRaises(FileExistsError),
        ):
            self.dataset.resource("parts").put(source)
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_restore_failure_preserves_backup_for_recovery(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        (destination / "original").write_bytes(b"keep")
        rename = os.rename
        calls = 0

        def fail_after_backup(src, dst):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("rename failed")
            return rename(src, dst)

        with (
            patch("fhrs._utils.put.os.rename", fail_after_backup),
            self.assertRaisesRegex(OSError, "preserved at ") as failure,
        ):
            resource.put(source, overwrite=True)
        backup = Path(str(failure.exception).split("preserved at ", 1)[1])
        self.assertTrue(backup.is_relative_to(self.work))
        self.assertEqual((backup / "original").read_bytes(), b"keep")
        self.assertFalse(destination.exists())

    def test_directory_does_not_replace_a_file_destination(self):
        source = self.make_directory()
        self.work.mkdir(parents=True)
        destination = self.work / "parts"
        destination.write_bytes(b"keep")
        with self.assertRaises(NotADirectoryError):
            self.dataset.resource("parts").put(source, overwrite=True)
        self.assertEqual(destination.read_bytes(), b"keep")
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_directory_overwrite_cleans_up_read_only_backup_files(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        (destination / "a.csv").chmod(stat.S_IREAD)
        (source / "a.csv").write_bytes(b"replacement")
        self.assertEqual(resource.put(source, overwrite=True), destination)
        self.assertEqual((destination / "a.csv").read_bytes(), b"replacement")
        self.assertEqual(list(self.work.iterdir()), [destination])

    def test_cleanup_failure_warns_and_keeps_successful_replacement(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        destination = resource.put(source)
        (source / "a.csv").write_bytes(b"replacement")
        unlink = os.unlink
        attempts = []

        def locked_unlink(path, *args, **kwargs):
            if Path(path).name == "a.csv":
                attempts.append(path)
                raise PermissionError("file is locked")
            return unlink(path, *args, **kwargs)

        with (
            patch("fhrs._utils.put.os.unlink", locked_unlink),
            self.assertWarnsRegex(RuntimeWarning, "cleanup failed") as warning,
        ):
            self.assertEqual(resource.put(source, overwrite=True), destination)
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual((destination / "a.csv").read_bytes(), b"replacement")
        remaining = [path for path in self.work.iterdir() if path != destination]
        self.assertEqual(len(remaining), 1)
        self.assertIn(str(remaining[0]), str(warning.warning))
        self.assertEqual((remaining[0] / "previous/a.csv").read_bytes(), b"first")

    def test_cleanup_failure_does_not_mask_copy_failure(self):
        source = self.make_directory()
        resource = self.dataset.resource("parts")
        with (
            patch(
                "fhrs._utils.put.shutil.copytree", side_effect=OSError("copy failed")
            ),
            patch(
                "fhrs._utils.put.shutil.rmtree", side_effect=PermissionError("locked")
            ),
            self.assertWarnsRegex(RuntimeWarning, "cleanup failed"),
            self.assertRaisesRegex(OSError, "copy failed"),
        ):
            resource.put(source)
        self.assertFalse((self.work / "parts").exists())


if __name__ == "__main__":
    unittest.main()
