import unittest

from fhrs.manifest.loader import _relative_urlpath


class RelativeUrlpathTests(unittest.TestCase):
    def test_local_paths(self):
        for urlpath in ("C:/catalog/fhrs.yaml", r"C:\catalog\fhrs.yaml"):
            with self.subTest(urlpath=urlpath):
                self.assertEqual(
                    _relative_urlpath(urlpath, "waves/1403.yaml"),
                    "C:/catalog/waves/1403.yaml",
                )
        self.assertEqual(_relative_urlpath("fhrs.yaml", "child.yaml"), "child.yaml")

    def test_github_repository_and_revision_are_preserved(self):
        urlpath = "github://Sakoo-Foundation:CBI-HBS-Summary@main/.fhrs/manifest.yaml"
        self.assertEqual(
            _relative_urlpath(urlpath, "waves/1403.yaml"),
            "github://Sakoo-Foundation:CBI-HBS-Summary@main/.fhrs/waves/1403.yaml",
        )

    def test_remote_parent_paths(self):
        for root in ("s3://bucket", "memory:///catalog", "https://example.org/catalog"):
            with self.subTest(root=root):
                self.assertEqual(
                    _relative_urlpath(
                        f"{root}/waves/1403.yaml", "../shared/notes.json"
                    ),
                    f"{root}/shared/notes.json",
                )


if __name__ == "__main__":
    unittest.main()
