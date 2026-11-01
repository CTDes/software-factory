import unittest

from textkit import initials, slugify, truncate, word_count


class SlugifyTest(unittest.TestCase):
    def test_lowercases_and_joins_words_with_hyphens(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_strips_accents(self) -> None:
        self.assertEqual(slugify("Canción de añoranza"), "cancion-de-anoranza")

    def test_collapses_punctuation_and_trims_edges(self) -> None:
        self.assertEqual(slugify("  --Hola, ¿qué tal?--  "), "hola-que-tal")

    def test_max_length_never_leaves_trailing_hyphen(self) -> None:
        self.assertEqual(slugify("reading time in posts", max_length=8), "reading")

    def test_negative_max_length_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            slugify("x", max_length=-1)

    def test_empty_text_gives_empty_slug(self) -> None:
        self.assertEqual(slugify("¿?!"), "")


class WordCountTest(unittest.TestCase):
    def test_counts_space_separated_words(self) -> None:
        self.assertEqual(word_count("uno dos  tres"), 3)

    def test_contractions_and_hyphenated_words_are_one_word(self) -> None:
        self.assertEqual(word_count("don't stop well-known"), 3)

    def test_ignores_punctuation(self) -> None:
        self.assertEqual(word_count("¡Hola! ... ¿Qué?"), 2)

    def test_empty_text_has_no_words(self) -> None:
        self.assertEqual(word_count(""), 0)


class TruncateTest(unittest.TestCase):
    def test_short_text_is_unchanged(self) -> None:
        self.assertEqual(truncate("hola", 10), "hola")

    def test_cuts_at_word_boundary(self) -> None:
        self.assertEqual(truncate("the quick brown fox", 12), "the quick…")

    def test_result_never_exceeds_limit(self) -> None:
        text = "palabras " * 20
        for limit in range(1, 40):
            self.assertLessEqual(len(truncate(text, limit)), limit)

    def test_single_long_word_is_cut_mid_word(self) -> None:
        self.assertEqual(truncate("supercalifragilistic", 6), "super…")

    def test_custom_suffix(self) -> None:
        self.assertEqual(truncate("the quick brown fox", 12, suffix="..."), "the quick...")

    def test_limit_smaller_than_suffix_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            truncate("abc", 2, suffix="...")


class InitialsTest(unittest.TestCase):
    def test_takes_first_letter_of_each_word(self) -> None:
        self.assertEqual(initials("ada lovelace"), "AL")

    def test_ignores_extra_spaces_and_punctuation(self) -> None:
        self.assertEqual(initials("  grace  -  hopper "), "GH")

    def test_keeps_accented_letters(self) -> None:
        self.assertEqual(initials("Álvaro Ñúñez"), "ÁÑ")


if __name__ == "__main__":
    unittest.main()
