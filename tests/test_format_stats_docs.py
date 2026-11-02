import unittest
from pathlib import Path

ARCHITECTURE = Path(__file__).resolve().parent.parent / "docs" / "architecture.md"


class FormatStatsDocsTest(unittest.TestCase):
    def test_architecture_mentions_format_stats(self) -> None:
        self.assertIn("format_stats", ARCHITECTURE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
