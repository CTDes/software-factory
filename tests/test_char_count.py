import unittest
from pathlib import Path

import textkit
from textkit import char_count

ROOT = Path(__file__).resolve().parent.parent


class TestCharCount(unittest.TestCase):
    def test_empty_text_is_zero(self) -> None:
        self.assertEqual(char_count(""), 0)

    def test_only_ascii_whitespace_is_zero(self) -> None:
        self.assertEqual(char_count(" \t\n  \r\n"), 0)

    def test_whitespace_excluded_punctuation_and_digits_counted(self) -> None:
        self.assertEqual(char_count(" a b\tc\n1!"), 5)

    def test_unicode_spaces_do_not_count(self) -> None:
        self.assertEqual(char_count("a\u00a0b\u2003c"), 3)
        self.assertEqual(char_count("\u00a0\u2003"), 0)

    def test_precomposed_accent_is_one_character(self) -> None:
        self.assertEqual(char_count("árbol"), 5)

    def test_spanish_punctuation_counts(self) -> None:
        self.assertEqual(char_count("¡Hola!"), 6)

    def test_exported_and_sorted(self) -> None:
        self.assertIn("char_count", textkit.__all__)
        self.assertEqual(textkit.__all__, sorted(textkit.__all__))

    def test_returns_int(self) -> None:
        self.assertIs(type(char_count("abc")), int)

    def test_documented(self) -> None:
        arch = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("`char_count`", arch)
        self.assertIn("char_count(text) -> int", arch)
        glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn("| char count |", glossary)
