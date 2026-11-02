import pathlib
import unittest

import textkit
from textkit import unique_words, word_count

ROOT = pathlib.Path(__file__).resolve().parent.parent


class UniqueWordsTest(unittest.TestCase):
    def test_empty_text_is_zero(self) -> None:
        self.assertEqual(unique_words(""), 0)

    def test_text_without_words_is_zero(self) -> None:
        self.assertEqual(unique_words("  ... ¡! "), 0)

    def test_case_insensitive(self) -> None:
        self.assertEqual(unique_words("Hola hola HOLA"), 1)

    def test_casefold_non_ascii(self) -> None:
        self.assertEqual(unique_words("ÁRBOL árbol"), 1)

    def test_contractions_and_hyphens_are_single_words(self) -> None:
        self.assertEqual(unique_words("don't stop don't well-known"), 3)

    def test_surrounding_punctuation_ignored(self) -> None:
        self.assertEqual(unique_words("Hola, hola. ¡Hola!"), 1)

    def test_different_words_counted_separately(self) -> None:
        self.assertEqual(unique_words("el gato y el perro"), 4)

    def test_exported_from_facade(self) -> None:
        self.assertIn("unique_words", textkit.__all__)

    def test_all_is_sorted(self) -> None:
        self.assertEqual(sorted(textkit.__all__), textkit.__all__)

    def test_never_more_than_word_count(self) -> None:
        for t in ["", "a a a", "el gato y el perro", "Hola, hola. ¡Hola!", "x-y x-y z"]:
            self.assertLessEqual(unique_words(t), word_count(t))

    def test_documented(self) -> None:
        arch = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn("unique_words", arch)
        self.assertTrue("unique words" in glossary or "unique_words" in glossary)


if __name__ == "__main__":
    unittest.main()
