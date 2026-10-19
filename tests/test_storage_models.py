import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fsspec
from pydantic import ValidationError

from fhrs.manifest import Collection, Dataset
from fhrs.manifest.models.storage import (
    BaseStorage,
    EmbeddedStorage,
    HTTPStorage,
    S3Storage,
)


class StorageModelTests(unittest.TestCase):
    def test_working_storage_name_is_reserved(self):
        for declaration in (
            {"protocol": "memory"},
            {"type": "embedded", "path": "originals"},
        ):
            with (
                self.subTest(declaration=declaration),
                self.assertRaisesRegex(
                    ValidationError, "working.*reserved.*working_directory"
                ),
            ):
                Dataset(name="survey", storages={"working": declaration})
        dataset = Dataset(
            name="survey", storages={"working_copy": {"protocol": "memory"}}
        )
        self.assertIn("working_copy", dataset.storages)

    def test_original_defaults_to_false_and_requires_a_boolean_for_all_storages(self):
        for model, fields in (
            (BaseStorage, {"protocol": "memory"}),
            (EmbeddedStorage, {"path": "data/"}),
            (HTTPStorage, {"url": "https://example.org/"}),
            (S3Storage, {"bucket": "data"}),
        ):
            with self.subTest(model=model.__name__):
                storage = model(**fields)
                self.assertIs(storage.original, False)
                options = storage.to_fsspec()
                for original in (True, False):
                    storage = model(**fields, original=original)
                    self.assertIs(storage.model_dump()["original"], original)
                    self.assertEqual(storage.to_fsspec(), options)
                for original in (None, "true", "false", 0, 1):
                    with (
                        self.subTest(original=original),
                        self.assertRaises(ValidationError),
                    ):
                        model(**fields, original=original)

    def test_format_version_on_datasets_only(self):
        self.assertEqual(Dataset(name="survey").fhrs_version, "0.1")
        self.assertEqual(Dataset(name="survey", fhrs_version="0.1").fhrs_version, "0.1")
        with self.assertRaises(ValidationError):
            Dataset(name="survey", fhrs_version="9.9")
        collection = Collection(name="wave")
        self.assertNotIn("fhrs_version", collection.model_dump())
        with self.assertRaises(ValidationError):
            Collection(name="wave", fhrs_version="0.1")
        with self.assertRaises(ValidationError):
            Dataset(name="survey", collections={"wave": {"fhrs_version": "0.1"}})

    def test_storage_declarations_use_correct_models(self):
        dataset = Dataset.model_validate(
            {
                "name": "survey",
                "storages": {
                    "embedded": {"type": "embedded", "base_path": "../data/"},
                    "http": {"type": "http", "base_url": "https://example.org/data/"},
                    "s3": {"bucket": "survey"},
                    "memory": {"protocol": "memory"},
                },
            }
        )
        self.assertIsInstance(dataset.storages["embedded"], EmbeddedStorage)
        self.assertEqual(dataset.storages["embedded"].path, "../data/")
        self.assertIsInstance(dataset.storages["http"], HTTPStorage)
        self.assertEqual(
            dataset.storages["http"].base_path, "https://example.org/data/"
        )
        self.assertIsInstance(dataset.storages["s3"], S3Storage)
        self.assertEqual(dataset.storages["memory"].protocol, "memory")

    def test_embedded_storage_works_with_fsspec(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = EmbeddedStorage(
                path=directory, storage_options={"auto_mkdir": True}
            )
            filesystem = fsspec.filesystem(**storage.to_fsspec())
            path = Path(storage.base_path) / "nested" / "test.txt"
            with filesystem.open(path, "wt") as stream:
                stream.write("example")
            self.assertEqual(path.read_text(), "example")
            self.assertEqual(storage.protocol, "file")
            self.assertEqual(storage.model_dump()["path"], directory)

    def test_http_storage_works_with_fsspec(self):
        storage = HTTPStorage(
            protocol="https",
            url="https://example.org/data/",
            storage_options={"block_size": 0, "asynchronous": True},
        )
        filesystem = fsspec.filesystem(**storage.to_fsspec())
        self.assertEqual(type(filesystem).__name__, "HTTPFileSystem")
        self.assertEqual(
            storage.model_dump(mode="json")["url"], "https://example.org/data/"
        )
        self.assertEqual(
            storage.to_fsspec(),
            {"protocol": "https", "block_size": 0, "asynchronous": True},
        )

    def test_http_storage_requires_http_url(self):
        for url in ("../data/", "s3://bucket/data/"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                HTTPStorage(url=url)


if __name__ == "__main__":
    unittest.main()
