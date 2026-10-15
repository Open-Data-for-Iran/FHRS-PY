import unittest
from pathlib import Path

from fhrs.manifest import Collection, load

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "manifest-pointers"


class ManifestPointerExampleTests(unittest.TestCase):
    def test_loads_nested_pointers_and_shared_manifest(self):
        dataset = load(EXAMPLE)
        self.assertEqual(dataset.name, "manifest-pointers")
        waves = dataset.collections["waves"]
        self.assertEqual(Path(waves._storage["urlpath"]), EXAMPLE / "fhrs.yaml")
        shared = []
        for year in ("1402", "1403"):
            with self.subTest(year=year):
                wave = waves.collections[year]
                self.assertIsInstance(wave, Collection)
                self.assertEqual(wave.title, f"Survey wave {year}")
                self.assertEqual(
                    Path(wave._storage["urlpath"]), EXAMPLE / "waves" / f"{year}.yaml"
                )
                notes = wave.collections["notes"]
                self.assertIsInstance(notes, Collection)
                self.assertEqual(notes.title, "Shared survey notes")
                self.assertEqual(
                    Path(notes._storage["urlpath"]), EXAMPLE / "shared" / "notes.json"
                )
                self.assertEqual(notes._storage["storage_options"], {})
                resource = notes.resources["readme"]
                readme = (
                    Path(dataset._storage["urlpath"]).parent / resource.locations[0].uri
                )
                self.assertTrue(readme.is_file())
                shared.append(notes)
        self.assertIsNot(shared[0], shared[1])

    def test_rejects_circular_pointer_example(self):
        with self.assertRaisesRegex(ValueError, "Collection manifest loop") as error:
            load(EXAMPLE / "cycle")
        self.assertIn("child.yaml", str(error.exception))
        self.assertIn("fhrs.yaml", str(error.exception))


if __name__ == "__main__":
    unittest.main()
