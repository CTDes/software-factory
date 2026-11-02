import unittest
from pathlib import Path

import textkit
from textkit import longest_word

ROOT = Path(__file__).resolve().parent.parent


class TestLongestWord(unittest.TestCase):
    def test_empty_text_is_empty_string(self) -> None:
        self.assertEqual(longest_word(""), "")

    def test_only_punctuation_or_whitespace_is_empty_string(self) -> None:
        self.assertEqual(longest_word("¡¿...?!"), "")
        self.assertEqual(longest_word("  \t\n"), "")

    def test_surrounding_punctuation_stripped_and_case_kept(self) -> None:
        self.assertEqual(longest_word("¡Extraordinario!"), "Extraordinario")

    def test_returns_longest(self) -> None:
        self.assertEqual(longest_word("gato perro sapo"), "perro")

    def test_tie_returns_first(self) -> None:
        self.assertEqual(longest_word("uno dos"), "uno")

    def test_same_word_definition_as_word_count(self) -> None:
        self.assertEqual(longest_word("a don't"), "don't")
        self.assertEqual(longest_word("es well-known"), "well-known")

    def test_accented_letters_count_as_one_and_are_kept(self) -> None:
        self.assertEqual(longest_word("sol árbol"), "árbol")

    def test_result_is_always_str(self) -> None:
        self.assertIsInstance(longest_word("hola"), str)
        self.assertIsInstance(longest_word("!!!"), str)

    def test_exported_in_sorted_all(self) -> None:
        self.assertIn("longest_word", textkit.__all__)
        self.assertEqual(textkit.__all__, sorted(textkit.__all__))

    def test_documented_in_architecture_and_glossary(self) -> None:
        architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn("longest_word", architecture)
        self.assertIn("longest word", glossary)
