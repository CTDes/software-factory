import unittest

from textkit import truncate


class TruncateWhitespaceTest(unittest.TestCase):
    def test_tab_is_word_boundary(self) -> None:
        self.assertEqual(truncate("uno\tdos tres", 6), "uno…")

    def test_newline_is_word_boundary(self) -> None:
        self.assertEqual(truncate("uno\ndos tres", 6), "uno…")

    def test_crlf_leaves_no_whitespace_before_suffix(self) -> None:
        self.assertEqual(truncate("uno\r\ndos tres", 7), "uno…")

    def test_mixed_separators_cut_at_last_whitespace(self) -> None:
        self.assertEqual(truncate("uno dos\ttres", 10), "uno dos…")

    def test_consecutive_whitespace_is_stripped(self) -> None:
        self.assertEqual(truncate("uno\t\tdos", 7), "uno…")

    def test_previous_behaviour_unchanged(self) -> None:
        self.assertEqual(truncate("uno dos tres", 6), "uno…")
        self.assertEqual(truncate("supercalifragilistic", 6), "super…")
        self.assertEqual(truncate("hola", 10), "hola")

    def test_result_never_exceeds_limit(self) -> None:
        for text in ("uno\tdos tres\ncuatro", "a\r\nb\tc\n\nd e"):
            for limit in range(1, len(text) + 1):
                self.assertLessEqual(len(truncate(text, limit)), limit)


if __name__ == "__main__":
    unittest.main()
