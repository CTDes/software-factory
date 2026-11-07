---
job: "010-estadisticas-de-texto"
kind: "spec"
issue: 10
title: "Estadísticas de texto"
pr: 16
stage: "done"
surfaces: []
rounds: 2
created: "2026-11-02T11:58:26+01:00"
updated: "2026-11-02T12:58:42+01:00"
---

# #10 Estadísticas de texto

`010-estadisticas-de-texto` · spec · stage done · surfaces none · 2 rounds · PR #16

## Tickets

- [#11 Contar caracteres visibles (char_count)](011-contar-caracteres-visibles-char-count.md) · done · 1 rounds
- [#12 Contar palabras únicas (unique_words)](012-contar-palabras-unicas-unique-words.md) · done · 3 rounds
- [#13 Palabra más larga (longest_word)](013-palabra-mas-larga-longest-word.md) · done · 2 rounds
- [#14 Métricas de texto en un dict (text_stats)](014-metricas-de-texto-en-un-dict-text-stats.md) · done · 2 rounds
- [#15 Informe legible de métricas (format_stats)](015-informe-legible-de-metricas-format-stats.md) · done · 2 rounds

## Issue

````text
### Cuerpo

## Problem Statement

Quien usa textkit para analizar textos (por ejemplo, para mostrar métricas de un post o validar un formulario) tiene que combinar a mano varias funciones (`word_count`, `sentence_count`…) y no tiene forma de saber cuántos caracteres visibles tiene un texto, cuántas palabras distintas usa o cuál es su palabra más larga. Tampoco hay una forma única de obtener todas las métricas a la vez ni de mostrarlas de forma legible.

## Solution

textkit ofrece cinco funciones puras nuevas en su API pública:

- `char_count(text)`: número de caracteres que no son espacio en blanco.
- `unique_words(text)`: número de palabras distintas, sin distinguir mayúsculas, con la misma definición de palabra (*word*) que `word_count`.
- `longest_word(text)`: la palabra más larga; si hay empate, la primera que aparece; cadena vacía si el texto no tiene palabras.
- `text_stats(text)`: un dict con las métricas `words`, `chars`, `unique_words` y `sentences` de un texto.
- `format_stats(text)`: un informe de varias líneas, legible por una persona, construido a partir de `text_stats`.

## User Stories

1. As a textkit user, I want to count the non-whitespace characters of a text, so that I can measure its visible length independently of spacing and line breaks.
2. As a textkit user, I want `char_count("")` and a whitespace-only text to return 0, so that empty input needs no special handling.
3. As a textkit user, I want tabs, newlines and other Unicode whitespace to be ignored by `char_count`, so that formatting does not change the count.
4. As a textkit user, I want punctuation and digits to count as characters in `char_count`, so that the count reflects everything a reader sees.
5. As a textkit user, I want accented letters to count as one character each, so that Spanish text is measured correctly.
6. As a textkit user, I want to know how many distinct words a text uses, so that I can estimate its vocabulary richness.
7. As a textkit user, I want `unique_words` to ignore case ("Hola hola HOLA" is one word), so that capitalisation at the start of a sentence does not inflate the count.
8. As a textkit user, I want `unique_words` to use exactly the same notion of word as `word_count`, so that `unique_words(t) <= word_count(t)` always holds and contractions or hyphenated words count as one.
9. As a textkit user, I want `unique_words` of a text without words to be 0, so that empty input needs no special handling.
10. As a textkit user, I want case-folding in `unique_words` to handle non-ASCII letters (e.g. "ÁRBOL" and "árbol" are the same word), so that it works for Spanish.
11. As a textkit user, I want to get the longest word of a text, so that I can spot unusually long terms.
12. As a textkit user, I want ties in `longest_word` to return the first longest word in reading order, so that the result is deterministic.
13. As a textkit user, I want `longest_word` to return the word exactly as written in the text (original case), so that I can show it to users.
14. As a textkit user, I want `longest_word` of a text without words to return an empty string, so that I never get an exception or `None`.
15. As a textkit user, I want `longest_word` to never include surrounding punctuation, so that "¡extraordinario!" yields "extraordinario".
16. As a textkit user, I want one call that returns all the basic metrics of a text, so that I do not have to call four functions.
17. As a textkit user, I want `text_stats` to return a plain dict with exactly the keys `words`, `chars`, `unique_words` and `sentences`, so that I can serialise it (e.g. to JSON) directly.
18. As a textkit user, I want each value of `text_stats` to equal the result of the corresponding public function (`word_count`, `char_count`, `unique_words`, `sentence_count`), so that the numbers are consistent across the API.
19. As a textkit user, I want `text_stats("")` to return all zeros, so that empty input needs no special handling.
20. As a textkit user, I want a ready-made human-readable report of the metrics, so that I can print it in a CLI or a log.
21. As a textkit user, I want `format_stats` to produce exactly four lines in a fixed order and wording, so that its output is stable and testable.
22. As a textkit user, I want `format_stats` to be computed from `text_stats`, so that the report and the dict can never disagree.
23. As a textkit user, I want `format_stats("")` to report zeros rather than fail, so that empty input needs no special handling.
24. As a textkit user, I want all new functions to be importable from `textkit`, so that I use the same import path as the rest of the library.
25. As a maintainer, I want all new functions to be pure and standard-library only, so that textkit keeps its architecture and ADR 0001.
26. As a maintainer, I want `docs/architecture.md` and `GLOSSARY.md` to document the new interface and terms, so that future contributors and agents use the same vocabulary.

## Implementation Decisions

- All five functions live in the existing pure-functions module of textkit and are re-exported by the `textkit` facade in `__all__` (kept alphabetically ordered).
- Word definition: reuse the existing word definition behind `word_count` (letters/digits, inner apostrophes and hyphens keep one word). No new word regex.
- `unique_words(text) -> int`: number of distinct words after `str.casefold()`.
- `char_count(text) -> int`: number of characters `ch` for which `ch.isspace()` is false.
- `longest_word(text) -> str`: longest word by `len`; first one wins on ties; returned in its original form; `""` if there are no words.
- `text_stats(text) -> dict[str, int]`: exactly the keys `words`, `chars`, `unique_words`, `sentences`, whose values are `word_count`, `char_count`, `unique_words` and the existing `sentence_count` of the text.
- `format_stats(text) -> str`: built only from `text_stats(text)`, exactly four lines joined by `\n`, no trailing newline, in this order and wording (agreed with the user):

  ```
  Palabras: <words>
  Caracteres: <chars>
  Palabras únicas: <unique_words>
  Frases: <sentences>
  ```

- Dependencies between the pieces: `text_stats` needs `char_count` and `unique_words`; `format_stats` needs `text_stats`; `longest_word` is independent.
- Every change to the public interface updates `docs/architecture.md` in the same diff; new terms ("unique words", "longest word", "text stats") go to `GLOSSARY.md`.
- Standard library only (ADR 0001), no I/O, full type hints (mypy strict).

## Testing Decisions

- A good test checks external behaviour through the public interface with independent expected values (literal examples), never by recomputing the result the way the code does.
- Single seam: the `textkit` facade. Tests import from `textkit`, never from the internal module.
- Each function gets its own new test file under `tests/` with one `TestCase` and methods named `test_<behaviour>`; existing test files are protected and must not be modified.
- `text_stats` is tested by comparing the whole dict on sample texts (including the empty text), so any change to the key set breaks the test on purpose.
- `format_stats` is tested by comparing the full output string for a concrete text and for the empty text.
- Prior art: `tests/test_sentence_count.py`, `tests/test_reading_time.py`, `tests/test_normalize.py`.

## Out of Scope

- Language-aware tokenisation, stemming or stop-word removal in `unique_words`.
- Grapheme-cluster counting in `char_count` (combining characters count as code points).
- Localised or configurable report formats in `format_stats` (only the fixed Spanish format above).
- Any CLI, file reading or printing.
- Changing the behaviour of existing functions.

## Further Notes

- Suggested ticket graph for `/to-tickets`: `char_count` and `unique_words` independent; `text_stats` blocked by both; `format_stats` blocked by `text_stats`; `longest_word` independent.
- This spec is the first one built end to end by the software factory (`factory/DESIGN.md`, phase 5).
````

## Round 1

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** CHANGES

#### Estándares
- tests/test_format_stats_docs.py:7 — `FormatStatsDocsTest` es un segundo `TestCase` (y un segundo fichero) para `format_stats`, además de `FormatStatsTest` en tests/test_format_stats.py:7. Incumple la convención documentada en CLAUDE.md ("one `TestCase` per public function") y la decisión de testing de la issue ("Each function gets its own new test file under `tests/` with one `TestCase`"). El resto de funciones (`char_count`, `longest_word`, `text_stats`, `unique_words`) comprueba la documentación dentro de su único `TestCase`; basta con mover `test_architecture_mentions_format_stats` a `FormatStatsTest` y borrar el fichero nuevo (no está protegido porque no existe en la base). **[bloquea]**
- docs/architecture.md:7 — la lista de re-exportaciones de la fachada no sigue ningún orden (`char_count` primero, y después las antiguas y las nuevas en orden de llegada), mientras que `__all__` sí está ordenado alfabéticamente. Es solo cosmético. **[no bloquea]**
- src/textkit/text.py:35 — `unique_words` va entre `word_count` y `truncate`, pero las otras funciones nuevas van al final del módulo. La colocación no es coherente; es solo cosmético. **[no bloquea]**
- tests/test_*.py nuevos — la comprobación "`__all__` está ordenado" se repite en los cinco ficheros nuevos (Duplicated Code). Es una cuestión de criterio, menor. **[no bloquea]**

#### Spec
Se cumplen todos los criterios funcionales de la issue #10:
- `char_count` (historias 1-5, decisión `ch.isspace()`): src/textkit/text.py:87.
- `unique_words` (historias 6-10, casefold y la misma `_WORD_RE`): src/textkit/text.py:35.
- `longest_word` (historias 11-15, `max(..., key=len, default="")`, que se queda con el primero en caso de empate): src/textkit/text.py:111.
- `text_stats` (historias 16-19, dict con exactamente las cuatro claves y los valores de las funciones públicas): src/textkit/text.py:95.
- `format_stats` (historias 20-23, cuatro líneas con la redacción exacta y sin salto final, construido desde `text_stats`): src/textkit/text.py:119.
- Exportación desde la fachada con `__all__` ordenado (historia 24) y documentación en architecture.md y GLOSSARY.md (historia 26).
- No hay alcance de más: ni CLI, ni I/O, ni cambios en funciones existentes.
- El incumplimiento de la decisión de testing ("one `TestCase`" por función) ya aparece en Estándares.

#### Arquitectura
Sin hallazgos. Solo se usa la biblioteca estándar, no hay I/O y `textkit.text` no importa la fachada. Los tests importan desde `textkit`. La interfaz pública cambia y `docs/architecture.md` se actualiza en el mismo diff con las firmas nuevas.

## Round 2

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_char_count.py::test_whitespace_excluded_punctuation_and_digits_counted — cuenta los caracteres que no son espacio (historia 1)
- C2: tests/test_char_count.py::test_only_ascii_whitespace_is_zero — un texto solo de espacios da 0; test_empty_text_is_zero cubre "" (historia 2)
- C3: tests/test_char_count.py::test_unicode_spaces_do_not_count — tabuladores, saltos de línea y espacios Unicode no cuentan (historia 3)
- C4: tests/test_char_count.py::test_spanish_punctuation_counts — la puntuación y los dígitos cuentan (historia 4)
- C5: tests/test_char_count.py::test_precomposed_accent_is_one_character — una letra acentuada cuenta como un carácter (historia 5)
- C6: tests/test_unique_words.py::test_different_words_counted_separately — cuenta las palabras distintas (historia 6)
- C7: tests/test_unique_words.py::test_case_insensitive — "Hola hola HOLA" cuenta como 1 (historia 7)
- C8: tests/test_unique_words.py::test_never_more_than_word_count — misma definición de palabra que word_count y unique_words <= word_count (historia 8)
- C9: tests/test_unique_words.py::test_text_without_words_is_zero — un texto sin palabras da 0 (historia 9)
- C10: tests/test_unique_words.py::test_casefold_non_ascii — "ÁRBOL" y "árbol" son la misma palabra (historia 10)
- C11: tests/test_longest_word.py::test_returns_longest — devuelve la palabra más larga (historia 11)
- C12: tests/test_longest_word.py::test_tie_returns_first — si hay empate, gana la primera (historia 12)
- C13: tests/test_longest_word.py::test_surrounding_punctuation_stripped_and_case_kept — conserva las mayúsculas originales (historia 13)
- C14: tests/test_longest_word.py::test_empty_text_is_empty_string — sin palabras devuelve "" (historia 14)
- C15: tests/test_longest_word.py::test_surrounding_punctuation_stripped_and_case_kept — "¡extraordinario!" da "extraordinario" (historia 15)
- C16: tests/test_text_stats.py::test_simple_example — una sola llamada devuelve las cuatro métricas (historia 16)
- C17: tests/test_text_stats.py::test_keys_are_exactly_the_four_metrics — dict normal con exactamente las claves words, chars, unique_words y sentences (historia 17)
- C18: tests/test_text_stats.py::test_mixed_case_contractions_and_hyphens — los valores coinciden con las funciones públicas (historia 18)
- C19: tests/test_text_stats.py::test_empty_text_is_all_zeros — text_stats("") devuelve todo ceros (historia 19)
- C20: tests/test_format_stats.py::test_formats_example_text — informe legible con la salida exacta (historia 20)
- C21: tests/test_format_stats.py::test_always_four_lines_without_trailing_newline — siempre cuatro líneas, sin salto de línea final (historia 21)
- C22: tests/test_format_stats.py::test_repeated_words_with_different_case — las cifras del informe coinciden con text_stats en un texto con mayúsculas mezcladas (historia 22)
- C23: tests/test_format_stats.py::test_empty_text_reports_zeros — format_stats("") informa ceros (historia 23)
- C24: tests/test_format_stats.py::test_exported_and_all_sorted — las funciones se exportan desde textkit y __all__ está ordenado; las otras cuatro tienen su equivalente en sus ficheros de test (historia 24)
- C25: tests/test_text_stats.py::test_result_is_plain_dict_of_ints — devuelve tipos puros de la biblioteca estándar; mypy --strict y ruff de factory/checks.sh pasan en verde (historia 25)
- C26: tests/test_format_stats.py::test_architecture_mentions_format_stats — architecture.md documenta la interfaz; test_documented_in_architecture_and_glossary en test_text_stats.py y test_longest_word.py cubre GLOSSARY.md (historia 26)

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares

- tests/test_char_count.py:10, tests/test_longest_word.py:10, tests/test_text_stats.py:11, tests/test_unique_words.py:10, tests/test_format_stats.py:10 — los nombres de las clases de test no siguen un mismo patrón (`TestCharCount`/`TestLongestWord` frente a `TextStatsTest`/`UniqueWordsTest`/`FormatStatsTest`). CLAUDE.md solo exige un `TestCase` por función pública con métodos `test_<behaviour>`, y eso se cumple. Smell menor de nombres (Mysterious Name / falta de consistencia). [no bloquea]
- tests/test_*.py (los cinco ficheros nuevos) — la comprobación "exportado y `__all__` ordenado" y la lectura de `architecture.md`/`GLOSSARY.md` con su constante `ROOT` se repiten en cada fichero (Duplicated Code). Es aceptable porque la spec pide un fichero de test independiente por función. [no bloquea]
- src/textkit/text.py — las funciones nuevas son puras, usan solo la biblioteca estándar, llevan tipos completos y reutilizan `_WORD_RE` sin añadir una regex de palabra nueva. Cumple CLAUDE.md y ADR 0001.

#### Spec

- Historias 1-5 (`char_count`): src/textkit/text.py:87 usa `not ch.isspace()`, como pide la decisión de implementación. Tests en tests/test_char_count.py. Se cumplen.
- Historias 6-10 (`unique_words`): src/textkit/text.py:35 combina `casefold()` con `_WORD_RE`. Se cumplen.
- Historias 11-15 (`longest_word`): src/textkit/text.py:111 usa `max(..., key=len, default="")`. Si hay empate, `max` devuelve el primero; conserva la forma original y no incluye puntuación. Se cumplen.
- Historias 16-19 (`text_stats`): src/textkit/text.py:95 devuelve un dict con exactamente las cuatro claves, y cada valor sale de la función pública correspondiente. Los tests comparan el dict entero, incluido el del texto vacío, como pide "Testing Decisions". Se cumplen.
- Historias 20-23 (`format_stats`): src/textkit/text.py:119 construye el informe solo a partir de `text_stats`, con las cuatro líneas en el orden y la redacción acordados y sin salto de línea final. Los tests comparan la cadena completa para un texto concreto y para el texto vacío. Se cumplen.
- Historia 24: src/textkit/__init__.py exporta las cinco funciones y `__all__` sigue en orden alfabético. Se cumple.
- Historia 25: funciones puras, solo biblioteca estándar, sin I/O. Se cumple.
- Historia 26: `docs/architecture.md` y `GLOSSARY.md` documentan la interfaz y los términos "unique words", "longest word" y "text stats". Se cumple.
- GLOSSARY.md:13 — añade además el término "char count", que la spec no menciona de forma explícita entre los términos nuevos. Es coherente con la regla de documentar el vocabulario nuevo y no añade comportamiento, así que no lo considero alcance de más. [no bloquea]
- No hay alcance de más en el código: no hay CLI, no hay I/O y no cambia ninguna función existente.

#### Arquitectura

Sin hallazgos.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:33+01:00 | (new) | building | spec created from #10 with 5 tickets |
| 2026-11-02T12:18:21+01:00 | building | final-review | all 5 tickets done |
| 2026-11-02T12:18:37+01:00 | final-review | final-review | final gate PASS round 1 |
| 2026-11-02T12:19:23+01:00 | final-review | final-build | FINAL CHANGES round 1 |
| 2026-11-02T12:20:26+01:00 | final-build | final-review | READY |
| 2026-11-02T12:20:33+01:00 | final-review | final-review | final gate PASS round 2 |
| 2026-11-02T12:21:19+01:00 | final-review | ready | FINAL PASS |
| 2026-11-02T12:58:42+01:00 | ready | done | PR #16 merged |
