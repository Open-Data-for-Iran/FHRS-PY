import unittest
from dataclasses import FrozenInstanceError
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import fsspec

from fhrs import runtime
from fhrs.manifest import Dataset as DatasetManifest


class ResourceMemberTests(unittest.TestCase):
    def test_absent_manifest_members_bind_to_an_empty_runtime_mapping(self):
        for resource_type in ("file", "directory"):
            for fields in ({}, {"members": None}):
                with self.subTest(type=resource_type, fields=fields):
                    dataset = runtime.Dataset(
                        DatasetManifest(
                            name="survey",
                            resources={"data": {"type": resource_type, **fields}},
                        )
                    )
                    resource = dataset.resource("data")
                    self.assertIsNone(resource.manifest.members)
                    self.assertEqual(resource.members, {})
                    with self.assertRaises(KeyError):
                        resource.member("missing")

    def test_members_without_locations_list_working_files(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        dataset = runtime.Dataset(
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "directory": {
                            "type": "directory",
                            "members": {"rows": "*.csv"},
                        }
                    },
                }
            ),
            working_directory=directory.name,
        )
        member = dataset.resource("directory#rows")
        self.assertEqual(member.sources, ())
        self.assertEqual(member.files(), ())
        with self.assertRaises(KeyError):
            member.files(source="missing")

    def make_resource(self, uri="memory://member-data", pattern="[UR]*.csv"):
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "storages": {
                    "backup": {
                        "protocol": "memory",
                        "storage_options": {"auto_mkdir": True},
                    }
                },
                "resources": {
                    "directory": {
                        "type": "directory",
                        "locations": [
                            {"name": "primary", "uri": uri},
                            {"name": "backup", "uri": "memory://named-backup/data/"},
                            {"storage": "backup", "uri": "stored-backup/data/"},
                        ],
                        "members": {"households": pattern},
                    },
                    "file": {"locations": [{"uri": "memory://data.csv"}]},
                },
            }
        )
        return runtime.Dataset(manifest).resource("directory")

    def test_members_bind_without_filesystem_access_and_keep_mirrors_separate(self):
        with patch("fsspec.url_to_fs", side_effect=AssertionError("unexpected I/O")):
            resource = self.make_resource()
            member = resource.member("households")
            self.assertIsInstance(member, runtime.ResourceMember)
            self.assertIsInstance(member, runtime.BaseRuntime)
            self.assertIs(member, resource.members["households"])
            self.assertIs(member.resource, resource)
            self.assertEqual((member.name, member.pattern), ("households", "[UR]*.csv"))
            self.assertEqual(
                [source.urlpath for source in member.sources],
                [
                    "memory://member-data/[UR]*.csv",
                    "memory://named-backup/data/[UR]*.csv",
                    "memory://stored-backup/data/[UR]*.csv",
                ],
            )
            self.assertEqual(member.sources[2].storage_options, {"auto_mkdir": True})
            self.assertIs(member.source("primary"), member.sources[0])
            self.assertIs(member.source("backup"), member.sources[1])
            with self.assertRaises(KeyError):
                member.source("missing")
            with self.assertRaises(KeyError):
                resource.member("missing")
            with self.assertRaises(TypeError):
                resource.members["new"] = member
            with self.assertRaises(FrozenInstanceError):
                member.pattern = "*.json"
            self.assertFalse(hasattr(member, "__dict__"))
            resource.manifest.members["later"] = "*.json"
            self.assertNotIn("later", resource.members)
            file = resource.dataset.resource("file")
            self.assertEqual(file.members, {})
            with self.assertRaises(ValueError):
                runtime.ResourceMember("invalid", "*.csv", file)

    def test_patterns_expand_inside_directory_with_or_without_trailing_slash(self):
        root = f"/members-{uuid4().hex}"
        fs = fsspec.filesystem("memory")
        fs.pipe(f"{root}/data/nested/U1403.csv", b"urban")
        fs.pipe(f"{root}/data/nested/R1403.csv", b"rural")
        fs.pipe(f"{root}/outside.csv", b"outside")
        self.addCleanup(fs.rm, root, recursive=True)
        for suffix in ("", "/"):
            with self.subTest(suffix=suffix):
                resource = self.make_resource(
                    f"memory://{root}/data{suffix}", "**/*.csv"
                )
                source = resource.member("households").source("primary")
                matches = source.glob()
                self.assertEqual(
                    [match.path for match in matches],
                    [f"{root}/data/nested/R1403.csv", f"{root}/data/nested/U1403.csv"],
                )
                contents = []
                for match in matches:
                    with match.open() as stream:
                        contents.append(stream.read())
                self.assertEqual(contents, [b"rural", b"urban"])
                fs.rm(f"{root}/data/nested/R1403.csv")
                fs.rm(f"{root}/data/nested/U1403.csv")
                self.assertEqual(source.glob(), ())
                fs.pipe(f"{root}/data/nested/U1403.csv", b"urban")
                fs.pipe(f"{root}/data/nested/R1403.csv", b"rural")

    def test_member_patterns_cannot_escape_the_directory(self):
        for pattern in (
            "../*.csv",
            "nested/../../*.csv",
            "/absolute/*.csv",
            "s3://other/*",
            "..\\*.csv",
        ):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                self.make_resource(pattern=pattern)

    def test_member_sources_preserve_backend_roots_and_glob_syntax(self):
        for uri, expected in (
            ("memory://", "memory://part?.csv"),
            ("file:///", "file:///part?.csv"),
            ("https://example.org/data/", "https://example.org/data/part?.csv"),
            ("s3://bucket/data", "s3://bucket/data/part?.csv"),
            ("github://org:repo@main/data", "github://org:repo@main/data/part?.csv"),
        ):
            with self.subTest(uri=uri):
                member = self.make_resource(uri, "part?.csv").member("households")
                self.assertEqual(member.source("primary").urlpath, expected)

    def test_inline_members_bind_lazily_without_changing_declarations(self):
        resource = self.make_resource()
        original = resource.manifest.model_dump()
        with patch("fsspec.url_to_fs", side_effect=AssertionError("unexpected I/O")):
            for pattern in ("*.csv", "nested/01.csv", "**/part?.csv"):
                with self.subTest(pattern=pattern):
                    member = resource.member(f"member:{pattern}")
                    self.assertIs(member.resource, resource)
                    self.assertEqual(member.pattern, pattern)
                    self.assertEqual(
                        member.source("primary").urlpath,
                        f"memory://member-data/{pattern}",
                    )
                    self.assertEqual(
                        member.sources[2].storage_options, {"auto_mkdir": True}
                    )
        self.assertEqual(set(resource.members), {"households"})
        self.assertEqual(resource.manifest.model_dump(), original)
        self.assertIs(resource.member("households"), resource.members["households"])
        with self.assertRaises(KeyError):
            resource.member("typo")

    def test_inline_members_expand_globs_and_exact_paths(self):
        root = f"/inline-members-{uuid4().hex}"
        fs = fsspec.filesystem("memory")
        fs.pipe(f"{root}/nested/01.csv", b"data")
        self.addCleanup(fs.rm, root, recursive=True)
        resource = self.make_resource(f"memory://{root}")
        for selector in ("member:**/*.csv", "member:nested/01.csv"):
            with self.subTest(selector=selector):
                matches = resource.member(selector).files(source="primary")
                self.assertEqual(
                    [match.path for match in matches], [f"{root}/nested/01.csv"]
                )
                with matches[0].open() as stream:
                    self.assertEqual(stream.read(), b"data")

    def test_files_selects_one_mirror_and_refreshes_matches(self):
        token = uuid4().hex
        root = f"/member-files-{token}"
        backup = f"/named-backup/data/{token}-backup.csv"
        fs = fsspec.filesystem("memory")
        fs.pipe(f"{root}/{token}-b.csv", b"second")
        fs.pipe(f"{root}/{token}-a.csv", b"first")
        fs.makedirs(f"{root}/{token}-directory.csv")
        fs.pipe(backup, b"mirror")
        self.addCleanup(fs.rm, root, recursive=True)
        self.addCleanup(fs.rm, backup)
        member = self.make_resource(f"memory://{root}", f"{token}-*.csv").member(
            "households"
        )
        matches = member.files()
        self.assertIsInstance(matches, tuple)
        self.assertEqual(
            [match.path for match in matches],
            [f"{root}/{token}-a.csv", f"{root}/{token}-b.csv"],
        )
        self.assertEqual(
            [match.path for match in member.files(source="backup")], [backup]
        )
        with self.assertRaises(KeyError):
            member.files(source="missing")
        fs.rm(f"{root}/{token}-a.csv")
        fs.rm(f"{root}/{token}-b.csv")
        self.assertEqual(member.files(), ())

    def test_inline_members_reject_empty_or_escaping_patterns_and_file_resources(self):
        resource = self.make_resource()
        for pattern in ("", "../*.csv", "/absolute.csv", "s3://other/*", "..\\*.csv"):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                resource.member(f"member:{pattern}")
        with self.assertRaises(ValueError):
            resource.dataset.resource("file").member("member:*.csv")


if __name__ == "__main__":
    unittest.main()
