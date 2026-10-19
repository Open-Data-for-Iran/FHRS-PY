import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import fsspec
from fsspec.implementations.github import GithubFileSystem
from pydantic import ValidationError

from fhrs import runtime
from fhrs.manifest import Dataset as DatasetManifest
from fhrs.manifest import Location
from fhrs.manifest import Resource as ResourceManifest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ResourceLocationTests(unittest.TestCase):
    def test_working_location_name_is_reserved(self):
        with self.assertRaisesRegex(ValidationError, "working.*reserved"):
            Location(uri="memory://data", name="working")
        for name in (None, "primary", "working_copy"):
            with self.subTest(name=name):
                self.assertEqual(Location(uri="memory://data", name=name).name, name)
        with self.assertRaisesRegex(ValidationError, "working.*reserved"):
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "collections": {
                        "wave": {
                            "resources": {
                                "data": {
                                    "locations": [
                                        {"name": "working", "uri": "memory://data"}
                                    ]
                                }
                            }
                        }
                    },
                }
            )

    def test_file_suffix_is_optional_and_exposed_without_changing_sources(self):
        for suffix in (None, ".pdf", ".tar.gz"):
            with self.subTest(suffix=suffix):
                declaration = ResourceManifest(
                    suffix=suffix,
                    locations=[{"uri": "https://example.org/download?id=1"}],
                )
                dataset = runtime.Dataset(
                    DatasetManifest(name="survey", resources={"report": declaration})
                )
                resource = dataset.resource("report")
                self.assertEqual(resource.suffix, suffix)
                self.assertEqual(declaration.model_dump()["suffix"], suffix)
                self.assertEqual(
                    resource.key + (resource.suffix or ""), "report" + (suffix or "")
                )
                self.assertEqual(
                    resource.sources[0].urlpath, "https://example.org/download?id=1"
                )
        self.assertIsNone(ResourceManifest().suffix)
        self.assertIsNone(ResourceManifest(type="directory").suffix)

    def test_invalid_suffixes_and_directory_suffixes_are_rejected(self):
        for suffix in (
            "",
            "pdf",
            ".",
            "..",
            ".tar..gz",
            ".pdf/other",
            ".pdf\\other",
            ".pdf:other",
            ".pdf\n",
            1,
        ):
            with self.subTest(suffix=suffix), self.assertRaises(ValidationError):
                ResourceManifest(suffix=suffix)
        with self.assertRaises(ValidationError):
            ResourceManifest(type="directory", suffix=".csv")

    def test_location_original_defaults_to_false_and_requires_a_boolean(self):
        for fields, expected in (
            ({}, False),
            ({"original": True}, True),
            ({"original": False}, False),
        ):
            with self.subTest(fields=fields):
                dataset = runtime.Dataset(
                    DatasetManifest.model_validate(
                        {
                            "name": "survey",
                            "resources": {
                                "data": {
                                    "locations": [
                                        {
                                            "uri": "https://example.org/data.csv",
                                            **fields,
                                        }
                                    ]
                                }
                            },
                        }
                    )
                )
                resource = dataset.resource("data")
                self.assertIs(resource.locations[0].original, expected)
                self.assertIs(
                    resource.manifest.model_dump()["locations"][0]["original"], expected
                )
                self.assertEqual(
                    resource.sources[0].urlpath, "https://example.org/data.csv"
                )
        for original in (None, "true", "false", 0, 1):
            with self.subTest(original=original), self.assertRaises(ValidationError):
                ResourceManifest(locations=[{"uri": "data.csv", "original": original}])

    def test_manifest_members_preserve_named_globs_and_validate_strings(self):
        members = {"households": "[UR]1403P3S01.csv", "nested": "**/*.csv"}
        resource = ResourceManifest(
            type="directory", locations=[{"uri": "data/"}], members=members
        )
        self.assertEqual(resource.members, members)
        self.assertEqual(resource.model_dump()["members"], members)
        self.assertIsNone(ResourceManifest(locations=[{"uri": "data.csv"}]).members)
        for invalid in (
            [],
            {"": "*.csv"},
            {"data": ""},
            {"data": 1},
            {1: "*.csv"},
        ):
            with self.subTest(members=invalid), self.assertRaises(ValidationError):
                ResourceManifest(
                    type="directory", locations=[{"uri": "data/"}], members=invalid
                )

    def test_manifest_members_default_to_none_and_omit_from_serialization(self):
        for resource_type in ("file", "directory"):
            for fields in ({}, {"members": None}):
                with self.subTest(type=resource_type, fields=fields):
                    declaration = ResourceManifest(type=resource_type, **fields)
                    self.assertIsNone(declaration.members)
                    data = declaration.model_dump(exclude_none=True)
                    self.assertNotIn("members", data)
                    self.assertEqual(ResourceManifest.model_validate(data), declaration)

    def test_file_resources_reject_explicit_members_even_when_empty(self):
        for fields in ({}, {"type": "file"}):
            for members in ({}, {"data": "*.csv"}):
                with (
                    self.subTest(fields=fields, members=members),
                    self.assertRaises(ValidationError),
                ):
                    ResourceManifest(
                        **fields, locations=[{"uri": "data.csv"}], members=members
                    )
        self.assertEqual(
            ResourceManifest(
                type="directory", locations=[{"uri": "data/"}], members={}
            ).members,
            {},
        )

    def test_file_size_is_optional_nonnegative_bytes_and_exposed_at_runtime(self):
        for size in (0, 123456, None):
            with self.subTest(size=size):
                resource = {"locations": [{"uri": "https://example.org/data.csv"}]}
                if size is not None:
                    resource["size"] = size
                dataset = runtime.Dataset(
                    DatasetManifest.model_validate(
                        {"name": "survey", "resources": {"data": resource}}
                    )
                )
                self.assertEqual(dataset.resource("data").size, size)
                self.assertEqual(dataset.manifest.resources["data"].size, size)
        for size in (-1, 1.5, True, "123", None):
            with self.subTest(size=size), self.assertRaises(ValidationError):
                DatasetManifest.model_validate(
                    {
                        "name": "survey",
                        "resources": {
                            "data": {"locations": [{"uri": "data.csv"}], "size": size}
                        },
                    }
                )
        with self.assertRaises(ValidationError):
            DatasetManifest.model_validate(
                {
                    "name": "survey",
                    "resources": {
                        "data": {
                            "type": "directory",
                            "locations": [{"uri": "data/"}],
                            "size": 0,
                        }
                    },
                }
            )

    def test_source_lookup_prefers_names_then_first_matching_storage(self):
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "storages": {"web": {"type": "http", "url": "https://example.org/"}},
                "resources": {
                    "data": {
                        "locations": [
                            {"name": "primary", "storage": "web", "uri": "first.csv"},
                            {"name": "web", "uri": "https://mirror.org/data.csv"},
                            {"storage": "web", "uri": "last.csv"},
                        ]
                    },
                    "fallback": {
                        "locations": [
                            {"storage": "web", "uri": "first.csv"},
                            {"storage": "web", "uri": "last.csv"},
                        ]
                    },
                },
            }
        )
        dataset = runtime.Dataset(manifest)
        resource = dataset.resource("data")
        self.assertIs(resource.source("primary"), resource.sources[0])
        self.assertIs(resource.source("web"), resource.sources[1])
        fallback = dataset.resource("fallback")
        self.assertIs(fallback.source("web"), fallback.sources[0])
        with self.assertRaises(KeyError) as error:
            resource.source("missing")
        self.assertEqual(error.exception.args, ("missing",))

    def test_sources_are_bound_once_without_reading_resource_contents(self):
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "resources": {
                    "data": {"locations": [{"uri": "https://example.org/missing.csv"}]}
                },
            }
        )
        dataset = runtime.Dataset(manifest)
        resource = dataset.resource("data")
        self.assertEqual(
            resource.sources, (runtime.Source("https://example.org/missing.csv"),)
        )
        manifest.resources["data"].locations[0].uri = "https://example.org/changed.csv"
        self.assertEqual(resource.sources[0].urlpath, "https://example.org/missing.csv")

    def test_relative_locations_use_the_dataset_manifest(self):
        dataset = runtime.load_manifest(EXAMPLES / "basic")
        (address,) = dataset.resource("data").sources
        with fsspec.open(**address.to_fsspec(), mode="rt") as stream:
            self.assertEqual(stream.readline().strip(), "year,value")
        dataset = runtime.load_manifest(EXAMPLES / "manifest-pointers")
        notes = dataset.collection("waves").collection("1403").collection("notes")
        (address,) = notes.resource("readme").sources
        with fsspec.open(**address.to_fsspec(), mode="rb") as stream:
            self.assertEqual(
                stream.read(),
                (EXAMPLES / "manifest-pointers" / "README.md").read_bytes(),
            )

    def test_embedded_storage_stays_on_the_manifest_filesystem(self):
        root = f"/locations-{uuid4().hex}"
        fs = fsspec.filesystem("memory")
        fs.pipe(
            f"{root}/.fhrs/manifest.yaml",
            b"name: survey\nstorages:\n  embedded:\n    type: embedded\n    path: ../data/\n"
            b"collections:\n  wave:\n    manifest: waves/1403.yaml\n",
        )
        fs.pipe(
            f"{root}/.fhrs/waves/1403.yaml",
            b"resources:\n  data:\n    locations:\n      - storage: embedded\n"
            b"        uri: report%20one.csv\n      - uri: nearby.csv\n",
        )
        fs.pipe(f"{root}/data/report one.csv", b"stored data")
        fs.pipe(f"{root}/.fhrs/nearby.csv", b"nearby data")
        self.addCleanup(fs.rm, root, recursive=True)
        dataset = runtime.load_manifest(
            f"{root}/.fhrs", storage_options={"protocol": "memory"}
        )
        locations = dataset.collection("wave").resource("data").sources
        for address, content in zip(
            locations, (b"stored data", b"nearby data"), strict=True
        ):
            self.assertEqual(address.storage_options["protocol"], "memory")
            with fsspec.open(**address.to_fsspec()) as stream:
                self.assertEqual(stream.read(), content)
        self.assertEqual(dataset.storage("embedded").protocol, "memory")
        self.assertIs(dataset.storage("embedded").filesystem(), fs)

    def test_github_embedded_paths_preserve_repository_revision_and_options(self):
        for urlpath, options in (
            ("github://org:repo@main/.fhrs/manifest.yaml", {"asynchronous": True}),
            (
                "github://.fhrs/manifest.yaml",
                {"org": "org", "repo": "repo", "sha": "main", "asynchronous": True},
            ),
        ):
            with self.subTest(urlpath=urlpath):
                manifest = DatasetManifest.model_validate(
                    {
                        "name": "survey",
                        "storages": {
                            "embedded": {"type": "embedded", "path": "../data/"}
                        },
                        "resources": {
                            "data": {
                                "locations": [
                                    {"storage": "embedded", "uri": "report.csv"},
                                    {"uri": "nearby.csv"},
                                ]
                            }
                        },
                    }
                )
                dataset = runtime.Dataset(
                    manifest, source=runtime.Source(urlpath, options)
                )
                address, nearby = dataset.resource("data").sources
                with patch.object(GithubFileSystem, "ls", return_value=[]):
                    fs, path = fsspec.url_to_fs(
                        address.urlpath, **address.storage_options
                    )
                    storage_fs = dataset.storage("embedded").filesystem()
                    nearby_fs, nearby_path = fsspec.url_to_fs(
                        nearby.urlpath, **nearby.storage_options
                    )
                self.assertEqual((fs.org, fs.repo, fs.root), ("org", "repo", "main"))
                self.assertEqual(path, "data/report.csv")
                self.assertEqual(nearby_path, ".fhrs/nearby.csv")
                self.assertEqual(
                    (nearby_fs.org, nearby_fs.repo, nearby_fs.root),
                    ("org", "repo", "main"),
                )
                self.assertEqual(storage_fs.protocol, "github")
                self.assertEqual(dataset.storage("embedded").protocol, "github")

    def test_explicit_storages_and_absolute_urls(self):
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "storages": {
                    "web": {
                        "type": "http",
                        "url": "https://example.org/data/",
                        "storage_options": {"headers": {"X-Example": "value"}},
                    },
                    "s3": {
                        "type": "s3",
                        "bucket": "datasets",
                        "prefix": "survey/",
                        "endpoint": "https://objects.example.org",
                        "region": "example-1",
                    },
                },
                "resources": {
                    "data": {
                        "locations": [
                            {"storage": "web", "uri": "report%20one.csv"},
                            {"storage": "s3", "uri": "report%20one.csv"},
                            {"uri": "https://other.example.org/report.csv?version=2"},
                        ]
                    }
                },
            }
        )
        dataset = runtime.Dataset(manifest)
        web, s3, direct = dataset.resource("data").sources
        self.assertEqual(web.urlpath, "https://example.org/data/report%20one.csv")
        self.assertEqual(web.storage_options, {"headers": {"X-Example": "value"}})
        self.assertEqual(s3.urlpath, "s3://datasets/survey/report one.csv")
        self.assertEqual(
            s3.storage_options["endpoint_url"], "https://objects.example.org/"
        )
        self.assertEqual(
            s3.storage_options["client_kwargs"]["region_name"], "example-1"
        )
        self.assertEqual(
            direct.urlpath, "https://other.example.org/report.csv?version=2"
        )
        self.assertEqual(direct.storage_options, {})

    def test_invalid_scope_paths_and_missing_context(self):
        for uri in (
            "../escape",
            "/absolute",
            "https://other.org/file",
            "safe/%2e%2e/file",
            "safe%2ffile",
            "bad%ZZ",
        ):
            with self.subTest(uri=uri):
                manifest = DatasetManifest.model_validate(
                    {
                        "name": "survey",
                        "storages": {"embedded": {"type": "embedded", "path": "data/"}},
                        "resources": {
                            "data": {"locations": [{"storage": "embedded", "uri": uri}]}
                        },
                    }
                )
                with self.assertRaises(ValueError):
                    runtime.Dataset(
                        manifest, source=runtime.Source("catalog/fhrs.yaml")
                    )
        manifest = DatasetManifest.model_validate(
            {
                "name": "survey",
                "resources": {"data": {"locations": [{"uri": "relative.csv"}]}},
            }
        )
        with self.assertRaisesRegex(ValueError, "source"):
            runtime.Dataset(manifest)
        manifest.resources["data"].locations[0].storage = "missing"
        with self.assertRaisesRegex(KeyError, "missing"):
            runtime.Dataset(manifest)


if __name__ == "__main__":
    unittest.main()
