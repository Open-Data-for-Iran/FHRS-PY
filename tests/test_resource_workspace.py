import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fhrs import manifest, runtime


class ResourceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.dataset = runtime.ManagedDataset(
            manifest.models.Dataset(
                name="survey",
                resources={"rows": {"suffix": ".csv"}, "parts": {"type": "directory"}},
            ),
            local_directory=self.root,
        )

    def test_put_add_and_remove_use_workspace_and_preserve_objects(self):
        objects = self.root / "objects"
        objects.mkdir()
        sentinel = objects / "keep"
        sentinel.write_bytes(b"immutable")
        rows = self.dataset.resource("rows")
        self.assertEqual(rows.put(b"id\n1\n"), self.root / "workspace/rows.csv")
        self.assertEqual(rows.workspace_path.read_bytes(), b"id\n1\n")
        self.assertEqual(Path(rows.source().urlpath), rows.workspace_path)
        parts = self.dataset.resource("parts")
        added = parts.add("nested/a.csv", b"id\n2\n")
        self.assertEqual(added, self.root / "workspace/parts/nested/a.csv")
        self.assertEqual(
            [
                Path(source.urlpath)
                for source in parts.member("member:**/*.csv").files()
            ],
            [added],
        )
        parts.remove("nested/a.csv")
        self.assertFalse(added.exists())
        self.assertEqual(sentinel.read_bytes(), b"immutable")
        self.assertEqual(set(self.root.iterdir()), {objects, self.root / "workspace"})

    def test_workspace_path_is_lazy_and_local_storage_still_resolves_from_root(self):
        resource = self.dataset.resource("rows")
        self.assertEqual(resource.workspace_path, self.root / "workspace/rows.csv")
        local = self.dataset.storage("local")
        self.assertEqual(
            Path(local.resolve("objects/blob").urlpath), self.root / "objects/blob"
        )
        self.assertFalse((self.root / "workspace").exists())

    def test_resource_paths_cannot_escape_workspace_into_object_store(self):
        dataset = runtime.ManagedDataset(
            manifest.models.Dataset(name="survey", resources={"../objects/blob": {}}),
            local_directory=self.root,
        )
        with self.assertRaises(ValueError):
            dataset.resources["../objects/blob"].put(b"overwrite")
        self.assertFalse((self.root / "objects").exists())

    def test_resource_symlink_cannot_escape_workspace_into_object_store(self):
        objects = self.root / "objects"
        objects.mkdir()
        (self.root / "workspace").mkdir()
        try:
            (self.root / "workspace/parts").symlink_to(
                objects, target_is_directory=True
            )
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaises(ValueError):
            self.dataset.resource("parts").add("blob", b"overwrite")
        self.assertEqual(list(objects.iterdir()), [])

    def test_redirected_workspace_root_rejects_operations_and_preserves_objects(self):
        objects = self.root / "objects"
        (objects / "parts").mkdir(parents=True)
        rows = objects / "rows.csv"
        member = objects / "parts/a.csv"
        rows.write_bytes(b"original rows")
        member.write_bytes(b"original member")
        try:
            (self.root / "workspace").symlink_to(objects, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")

        resource = self.dataset.resource("rows")
        parts = self.dataset.resource("parts")
        operations = {
            "put": lambda: resource.put(b"changed", overwrite=True),
            "add": lambda: parts.add("a.csv", b"changed", overwrite=True),
            "remove": lambda: parts.remove("a.csv"),
            "source": lambda: resource.source("local"),
            "workspace_path": lambda: resource.workspace_path,
        }
        for name, operation in operations.items():
            with self.subTest(operation=name):
                with self.assertRaisesRegex(ValueError, "Workspace root"):
                    operation()
                self.assertEqual(rows.read_bytes(), b"original rows")
                self.assertEqual(member.read_bytes(), b"original member")
