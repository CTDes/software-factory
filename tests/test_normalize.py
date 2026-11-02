import unittest

import textkit
from textkit import normalize


class NormalizeTest(unittest.TestCase):
    def test_exported_in_all(self) -> None:
        self.assertIn("normalize", textkit.__all__)

    def test_composes_canonical_equivalents(self) -> None:
        self.assertEqual(normalize("é"), "é")

    def test_applies_compatibility_equivalents(self) -> None:
        self.assertEqual(normalize("ﬁ"), "fi")
        self.assertEqual(normalize("\uff12"), "2")
        self.assertEqual(normalize("①"), "1")

    def test_keeps_case(self) -> None:
        self.assertEqual(normalize("Hola MUNDO"), "Hola MUNDO")
        self.assertEqual(normalize("Straße"), "Straße")

    def test_keeps_precomposed_accents(self) -> None:
        self.assertEqual(normalize("Árbol canción"), "Árbol canción")

    def test_keeps_whitespace_and_punctuation(self) -> None:
        self.assertEqual(normalize("  a,  b!\t\n"), "  a,  b!\t\n")

    def test_empty_string(self) -> None:
        self.assertEqual(normalize(""), "")

    def test_idempotent(self) -> None:
        samples = [
            "é",
            "ﬁ",
            "\uff12",
            "①",
            "Hola MUNDO",
            "Straße",
            "Árbol canción",
            "  a,  b!\t\n",
            "",
        ]
        for s in samples:
            with self.subTest(s=s):
                self.assertEqual(normalize(normalize(s)), normalize(s))

    def test_equivalent_texts_give_same_result(self) -> None:
        self.assertEqual(normalize("\uff21́"), normalize("Á"))


if __name__ == "__main__":
    unittest.main()
