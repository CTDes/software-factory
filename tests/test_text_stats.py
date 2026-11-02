import unittest
from pathlib import Path

import textkit
from textkit import text_stats

ROOT = Path(__file__).resolve().parent.parent
KEYS = {"words", "chars", "unique_words", "sentences"}


class TextStatsTest(unittest.TestCase):
    def test_empty_text_is_all_zeros(self) -> None:
        self.assertEqual(
            text_stats(""), {"words": 0, "chars": 0, "unique_words": 0, "sentences": 0}
        )

    def test_simple_example(self) -> None:
        self.assertEqual(
            text_stats("Hola hola. Adiós!"),
            {"words": 3, "chars": 15, "unique_words": 2, "sentences": 2},
        )

    def test_keys_are_exactly_the_four_metrics(self) -> None:
        for text in ["", "a", "Hola hola. Adiós!", " \t\n "]:
            self.assertEqual(set(text_stats(text)), KEYS)

    def test_result_is_plain_dict_of_ints(self) -> None:
        result = text_stats("Hola hola. Adiós!")
        self.assertIs(type(result), dict)
        for value in result.values():
            self.assertIs(type(value), int)

    def test_whitespace_only_is_all_zeros(self) -> None:
        self.assertEqual(
            text_stats(" \t\n "), {"words": 0, "chars": 0, "unique_words": 0, "sentences": 0}
        )

    def test_mixed_case_contractions_and_hyphens(self) -> None:
        self.assertEqual(
            text_stats("Don't stop. DON'T stop! well-known?"),
            {"words": 5, "chars": 31, "unique_words": 3, "sentences": 3},
        )

    def test_exported_and_all_sorted(self) -> None:
        self.assertIn("text_stats", textkit.__all__)
        self.assertEqual(textkit.__all__, sorted(textkit.__all__))

    def test_documented_in_architecture_and_glossary(self) -> None:
        self.assertIn("text_stats", (ROOT / "docs" / "architecture.md").read_text("utf-8"))
        self.assertIn("| text stats |", (ROOT / "GLOSSARY.md").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
