import unittest
from pathlib import Path

from fhrs.parse_source import parse, parse_github


class ParseGithubTests(unittest.TestCase):
    def test_converts_repository_branch_and_file_urls(self):
        cases = {
            "https://github.com/Open-Data-for-Iran/SCI_Dataset_List": "github://Open-Data-for-Iran:SCI_Dataset_List@",
            "https://github.com/owner/repo.git/": "github://owner:repo@",
            "https://github.com/Iran-Open-Data/BSSIR/tree/dev": "github://Iran-Open-Data:BSSIR@dev",
            "https://github.com/owner/repo/tree/dev/data/": "github://owner:repo@dev/data",
            "https://github.com/owner/repo/blob/dev/.fhrs/manifest.yaml?raw=true": "github://owner:repo@dev/.fhrs/manifest.yaml",
            "http://GITHUB.COM/owner/repo#readme": "github://owner:repo@",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(parse_github(source), expected)
                self.assertEqual(parse(source), expected)
                self.assertEqual(parse_github(expected), expected)

    def test_preserves_other_sources_and_unsupported_github_pages(self):
        for source in (
            "survey",
            "./.fhrs",
            r"C:\survey",
            "memory://survey/manifest.yaml",
            "https://example.org/owner/repo",
            "https://github.com.evil.org/owner/repo",
            "https://raw.githubusercontent.com/owner/repo/main/.fhrs/manifest.yaml",
            "https://github.com/owner",
            "https://github.com/owner/repo/issues",
            "https://github.com/owner/repo/tree",
            "https://github.com/owner//tree/dev",
        ):
            with self.subTest(source=source):
                self.assertEqual(parse_github(source), source)
                self.assertEqual(parse(source), source)

    def test_generic_parser_preserves_pathlike_sources(self):
        source = Path("survey")
        self.assertIs(parse(source), source)
