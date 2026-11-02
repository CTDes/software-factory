import unittest

from textkit import reading_time


class ReadingTimeTest(unittest.TestCase):
    def test_empty_text_is_zero_minutes(self) -> None:
        self.assertEqual(reading_time(""), 0)

    def test_up_to_wpm_words_is_one_minute(self) -> None:
        self.assertEqual(reading_time("palabra"), 1)
        self.assertEqual(reading_time("palabra " * 200), 1)

    def test_rounds_up(self) -> None:
        self.assertEqual(reading_time("palabra " * 201), 2)

    def test_non_positive_wpm_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reading_time("hola", wpm=0)


if __name__ == "__main__":
    unittest.main()
