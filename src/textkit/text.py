"""Small text utilities used as the playground for the software factory."""

from __future__ import annotations

import math
import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+(?:['\u2019-][^\W_]+)*", re.UNICODE)
_SENTENCE_END_RE = re.compile(r"[.!?]+")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int | None = None) -> str:
    """Return a lowercase ASCII slug: words joined by single hyphens.

    Accents are stripped (``"Canción"`` -> ``"cancion"``). If ``max_length`` is
    given, the slug is cut to at most that many characters without leaving a
    trailing hyphen.
    """
    if max_length is not None and max_length < 0:
        raise ValueError("max_length must be >= 0")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG_RE.sub("-", ascii_text.lower()).strip("-")
    if max_length is not None:
        slug = slug[:max_length].rstrip("-")
    return slug


def word_count(text: str) -> int:
    """Count words. Contractions and hyphenated words count as one word."""
    return len(_WORD_RE.findall(text))


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Shorten ``text`` to at most ``limit`` characters, suffix included.

    Cuts at the last word boundary that fits (any whitespace character). Text that already fits is
    returned unchanged.
    """
    if limit < len(suffix):
        raise ValueError("limit must be at least len(suffix)")
    if len(text) <= limit:
        return text
    room = limit - len(suffix)
    cut = text[:room]
    if room < len(text) and not text[room].isspace():
        last = max((i for i, ch in enumerate(cut) if ch.isspace()), default=-1)
        if last >= 0:
            cut = cut[:last]
    return cut.rstrip() + suffix


def initials(name: str) -> str:
    """Return the uppercase initials of a name: ``"ada lovelace"`` -> ``"AL"``."""
    return "".join(word[0].upper() for word in _WORD_RE.findall(name))


def reading_time(text: str, wpm: int = 200) -> int:
    """Estimated reading minutes, rounded up; 0 for text without words."""
    if wpm <= 0:
        raise ValueError("wpm must be > 0")
    return math.ceil(word_count(text) / wpm)


def normalize(text: str) -> str:
    """Return ``text`` in Unicode NFKC form, with no other transformation."""
    return unicodedata.normalize("NFKC", text)


def sentence_count(text: str) -> int:
    """Count sentences: segments ending in a run of ``.``, ``!`` or ``?``.

    A segment only counts if it contains a word; the unterminated tail counts
    under the same rule.

    Example: ``sentence_count("Hola. ¿Qué tal?! Bien")`` -> ``3``.
    """
    return sum(1 for segment in _SENTENCE_END_RE.split(text) if _WORD_RE.search(segment))
