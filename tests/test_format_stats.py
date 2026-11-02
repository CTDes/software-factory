import unittest
from pathlib import Path

import textkit
from textkit import format_stats

ARCHITECTURE = Path(__file__).resolve().parent.parent / "docs" / "architecture.md"


class FormatStatsTest(unittest.TestCase):
    def test_formats_example_text(self) -> None:
        self.assertEqual(
            format_stats("Hola hola. Adiós!"),
            "Palabras: 3\nCaracteres: 15\nPalabras únicas: 2\nFrases: 2",
        )

    def test_empty_text_reports_zeros(self) -> None:
        self.assertEqual(
            format_stats(""),
            "Palabras: 0\nCaracteres: 0\nPalabras únicas: 0\nFrases: 0",
        )

    def test_always_four_lines_without_trailing_newline(self) -> None:
        for text in ["Hola mundo.\n", "   ", "a", "Uno. Dos!\n\n"]:
            out = format_stats(text)
            self.assertFalse(out.endswith("\n"), repr(text))
            self.assertEqual(len(out.split("\n")), 4, repr(text))

    def test_repeated_words_with_different_case(self) -> None:
        self.assertEqual(
            format_stats("Uno dos. DOS tres! ¿Tres?"),
            "Palabras: 5\nCaracteres: 21\nPalabras únicas: 3\nFrases: 3",
        )

    def test_exported_and_all_sorted(self) -> None:
        self.assertIn("format_stats", textkit.__all__)
        self.assertEqual(textkit.__all__, sorted(textkit.__all__))

    def test_architecture_mentions_format_stats(self) -> None:
        self.assertIn("format_stats", ARCHITECTURE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
