import unittest

import textkit
from textkit import sentence_count


class TestSentenceCount(unittest.TestCase):
    def test_empty_or_blank_text_is_zero(self) -> None:
        self.assertEqual(sentence_count(""), 0)
        self.assertEqual(sentence_count("   \n\t "), 0)

    def test_each_terminator_closes_a_sentence(self) -> None:
        self.assertEqual(sentence_count("Hola. Adiós! ¿Qué tal?"), 3)

    def test_run_of_terminators_counts_once(self) -> None:
        self.assertEqual(sentence_count("Espera... ¿En serio?! Sí!!!"), 3)

    def test_trailing_segment_without_terminator_counts_if_it_has_a_word(self) -> None:
        self.assertEqual(sentence_count("Hola. Qué tal"), 2)
        self.assertEqual(sentence_count("Hola"), 1)

    def test_trailing_whitespace_does_not_count(self) -> None:
        self.assertEqual(sentence_count("Hola.   "), 1)

    def test_segment_without_words_does_not_count(self) -> None:
        self.assertEqual(sentence_count("..."), 0)
        self.assertEqual(sentence_count("?!"), 0)
        self.assertEqual(sentence_count("Hola. . !"), 1)

    def test_is_exported_from_package(self) -> None:
        self.assertIn("sentence_count", textkit.__all__)
