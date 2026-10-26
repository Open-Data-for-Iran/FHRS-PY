import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import fhrs
from fhrs import runtime


class PackageLoaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.package_name = f"dataset_{uuid4().hex}"
        self.package = self.root / self.package_name
        self.package.mkdir()
        (self.package / "__init__.py").write_text("", encoding="utf-8")
        sys.path.insert(0, str(self.root))
        self.addCleanup(sys.path.remove, str(self.root))
        self.addCleanup(self.clear_modules)

    def clear_modules(self):
        for name in list(sys.modules):
            if name == self.package_name or name.startswith(self.package_name + "."):
                del sys.modules[name]

    def write_setup(self, code):
        (self.package / "fhrs_setup.py").write_text(code, encoding="utf-8")
        importlib.invalidate_caches()

    def test_loads_package_and_binds_relative_resources_and_collections(self):
        self.write_setup(
            "from fhrs.manifest.models import Dataset, Resource, Location, ManifestReference\n"
            "dataset = Dataset(name='survey', resources={\n"
            "    'xml': Resource(suffix='.xml', locations=[Location(uri='original.xml')])\n"
            "}, collections={'wave': ManifestReference(manifest='wave.yaml')})\n"
        )
        (self.package / "original.xml").write_bytes(b"<dataset/>")
        (self.package / "wave.yaml").write_text("title: Wave\n", encoding="utf-8")

        dataset = fhrs.load(self.package_name, working_directory=self.root / "work")

        self.assertIsInstance(dataset, runtime.Dataset)
        self.assertEqual(dataset.name, "survey")
        self.assertEqual(dataset.working_directory, self.root / "work")
        self.assertEqual(dataset.collection("wave").title, "Wave")
        self.assertIs(dataset.resource("xml").dataset, dataset)
        with dataset.resource("xml").sources[0].open() as stream:
            self.assertEqual(stream.read(), b"<dataset/>")
        setup = importlib.import_module(f"{self.package_name}.fhrs_setup")
        self.assertIsNot(dataset.manifest, setup.dataset)
        self.assertFalse(hasattr(setup.dataset, "_storage"))
        self.assertEqual(fhrs.load(self.package_name.replace("_", "-")).name, "survey")

    def test_requires_a_manifest_dataset(self):
        for code, error in (("dataset = {}\n", TypeError), ("", AttributeError)):
            with self.subTest(code=code):
                self.clear_modules()
                self.write_setup(code)
                with self.assertRaises(error):
                    fhrs.load(self.package_name)

    def test_selects_package_version_without_modifying_declaration(self):
        self.write_setup(
            "from fhrs.manifest.models import Dataset\n"
            "dataset = Dataset(name='current', versions={'indexes': ['versions.json']})\n"
        )
        (self.package / "versions.json").write_text(
            '{"one": {"manifest": "fixed.json"}}', encoding="utf-8"
        )
        (self.package / "fixed.json").write_text('{"name": "fixed"}', encoding="utf-8")
        for loader in (fhrs.load, runtime.load_package):
            with self.subTest(loader=loader):
                fixed = loader(self.package_name, version="one", manage=True)
                self.assertIsInstance(fixed, runtime.ManagedDataset)
                self.assertEqual(fixed.name, "fixed")
                self.assertEqual(
                    Path(fixed.source.urlpath), self.package / "fixed.json"
                )
        setup = importlib.import_module(f"{self.package_name}.fhrs_setup")
        self.assertEqual(setup.dataset.name, "current")
        self.assertFalse(hasattr(setup.dataset, "_storage"))

    def test_runtime_load_package_uses_default_setup_module(self):
        from fhrs.runtime.loader import load_package

        self.write_setup(
            "from fhrs.manifest.models import Dataset\ndataset = Dataset(name='survey')\n"
        )
        dataset = load_package(self.package_name)
        self.assertIsInstance(dataset, runtime.Dataset)
        self.assertEqual(dataset.name, "survey")
        self.assertEqual(runtime.load_package(self.package_name).name, "survey")

    def test_custom_setup_module(self):
        (self.package / "custom_setup.py").write_text(
            "from fhrs.manifest.models import Dataset\ndataset = Dataset(name='custom')\n",
            encoding="utf-8",
        )
        for load in (fhrs.load, runtime.load_package):
            with self.subTest(loader=load):
                dataset = load(
                    self.package_name,
                    setup_module="custom_setup",
                    working_directory=self.root / "custom-work",
                )
                self.assertEqual(dataset.name, "custom")
                self.assertEqual(dataset.working_directory, self.root / "custom-work")
                self.assertEqual(
                    Path(dataset.source.urlpath), self.package / "custom_setup.py"
                )

    def test_missing_package_and_dependency_errors_are_preserved(self):
        missing = f"missing_{uuid4().hex}"
        with self.assertRaises(ModuleNotFoundError) as caught:
            fhrs.load(missing)
        self.assertEqual(caught.exception.name, missing)
        self.write_setup(f"import {missing}\n")
        with self.assertRaises(ModuleNotFoundError) as caught:
            fhrs.load(self.package_name)
        self.assertEqual(caught.exception.name, missing)

    def test_setup_module_requires_a_file_location(self):
        for declaration in ("__file__ = None", "del __file__"):
            with self.subTest(declaration=declaration):
                self.clear_modules()
                self.write_setup(
                    "from fhrs.manifest.models import Dataset\n"
                    "dataset = Dataset(name='survey')\n"
                    f"{declaration}\n"
                )
                with self.assertRaisesRegex(ValueError, "has no file location"):
                    runtime.load_package(self.package_name)


if __name__ == "__main__":
    unittest.main()
