---
job: "013-palabra-mas-larga-longest-word"
kind: "ticket"
issue: 13
title: "Palabra más larga (longest_word)"
spec: "010-estadisticas-de-texto"
stage: "done"
risk: "medium"
surfaces: ["api"]
rounds: 2
created: "2026-11-02T11:58:35+01:00"
updated: "2026-11-02T12:13:15+01:00"
---

# #13 Palabra más larga (longest_word)

`013-palabra-mas-larga-longest-word` · ticket · stage done · risk medium · surfaces api · 2 rounds · spec [010-estadisticas-de-texto](010-estadisticas-de-texto.md)

## Issue

```text
### Cuerpo

Parent: #10

## What to build

`longest_word(text)` devuelve la palabra más larga del texto tal como aparece escrita; si hay empate, la primera; cadena vacía si no hay palabras. Ver la spec #10.

## Acceptance criteria

- [ ] `longest_word("")` y `longest_word("¡¿...?!")` devuelven `""`
- [ ] Devuelve la palabra sin la puntuación de alrededor: `longest_word("¡Extraordinario!")` devuelve `"Extraordinario"`
- [ ] Con empate gana la primera: `longest_word("gato perro sapo")` devuelve `"perro"` y `longest_word("uno dos")` devuelve `"uno"`
- [ ] `longest_word` está en `textkit.__all__`, y `docs/architecture.md` y `GLOSSARY.md` lo documentan
```

## Plan

**DECISION:** ACCEPT · **RISK:** medium · **SURFACES:** api

### Alcance

Añadir la función pura `longest_word(text: str) -> str` en `src/textkit/text.py` y
reexportarla desde la fachada `textkit` (`__all__`, que se mantiene en orden alfabético).

- Usa la definición de palabra (*word*) que ya existe detrás de `word_count` (`_WORD_RE`): letras
  y dígitos, y los apóstrofos (`'`, `’`) o guiones interiores mantienen una sola palabra. No se
  añade ninguna regex de palabra nueva.
- Devuelve la palabra más larga medida con `len` (puntos de código), tal como aparece en el texto
  (misma capitalización y sin la puntuación de alrededor).
- Si hay empate, devuelve la primera en orden de lectura. Si no hay palabras, devuelve `""`. No
  lanza excepciones ni devuelve `None`.
- En el mismo diff: `docs/architecture.md` (fila de la fachada y fila de `textkit.text` con la
  firma) y `GLOSSARY.md` (término "longest word").
- Fuera de alcance: cambiar funciones existentes y las demás piezas de la spec #10 (`unique_words`,
  `text_stats`, `format_stats`).

### Criterios de aceptación
- C1: `longest_word("")` devuelve `""`.
- C2: `longest_word("¡¿...?!")` devuelve `""`, y un texto que solo tiene espacios en blanco (`"  \t\n"`) también devuelve `""`.
- C3: `longest_word("¡Extraordinario!")` devuelve `"Extraordinario"` (sin la puntuación de alrededor y con la capitalización original).
- C4: `longest_word("gato perro sapo")` devuelve `"perro"`.
- C5: si hay empate, gana la primera: `longest_word("uno dos")` devuelve `"uno"`.
- C6: usa la misma definición de palabra que `word_count`: `longest_word("a don't")` devuelve `"don't"` y `longest_word("es well-known")` devuelve `"well-known"`.
- C7: las letras con tilde cuentan como un carácter y se conservan: `longest_word("sol árbol")` devuelve `"árbol"`.
- C8: el tipo del resultado es siempre `str` (también cuando el texto no tiene palabras).
- C9: `"longest_word"` está en `textkit.__all__`, `__all__` sigue en orden alfabético y `from textkit import longest_word` funciona.
- C10: `docs/architecture.md` menciona `longest_word` y `GLOSSARY.md` contiene el término "longest word" (se puede comprobar con un test que lee los ficheros, o en la revisión del diff).

### Seams

- Seam único: la fachada `textkit` (`from textkit import longest_word`). Los tests no importan
  de `textkit.text`.
- Los tests van en un fichero nuevo, `tests/test_longest_word.py`, con un `TestCase`
  (`TestLongestWord`) y métodos `test_<behaviour>`. Ejemplos a seguir: `tests/test_char_count.py`
  y `tests/test_sentence_count.py`. No se tocan los ficheros que ya existen en `tests/`.

### Notas

- El ejemplo de la issue `"gato perro sapo"` no es en realidad un empate ("perro" tiene 5 letras
  y las otras dos tienen 4). El empate de verdad lo comprueba `"uno dos"` (C5).
- Al usar `max(words, key=len, default="")` o un recorrido equivalente, gana la primera en caso de
  empate, porque `max` devuelve el primer máximo.
- Pieza independiente dentro de la spec #10: no depende de `char_count`, `unique_words` ni
  `text_stats`. Los conflictos posibles con tickets hermanos se limitan a líneas vecinas en
  `__init__.py`, `architecture.md` y `GLOSSARY.md`.
- Todo debe pasar `factory/checks.sh` (ruff, ruff format, mypy --strict, unittest, build).

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_longest_word.py::test_empty_text_is_empty_string — texto vacío devuelve ""
- C2: tests/test_longest_word.py::test_only_punctuation_or_whitespace_is_empty_string — puntuación o espacios devuelven ""
- C3: tests/test_longest_word.py::test_surrounding_punctuation_stripped_and_case_kept — "Extraordinario" sin puntuación y con mayúscula
- C4: tests/test_longest_word.py::test_returns_longest — "perro"
- C5: tests/test_longest_word.py::test_tie_returns_first — empate gana "uno"
- C6: tests/test_longest_word.py::test_same_word_definition_as_word_count — "don't" y "well-known"
- C7: tests/test_longest_word.py::test_accented_letters_count_as_one_and_are_kept — "árbol"
- C8: tests/test_longest_word.py::test_result_is_always_str — resultado str también sin palabras
- C9: tests/test_longest_word.py::test_exported_in_sorted_all — en __all__, ordenado
- C10: tests/test_longest_word.py::test_documented_in_architecture_and_glossary — architecture.md y GLOSSARY.md

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. Función pura, con tipos, reutiliza `_WORD_RE` (sin duplicar). Los tests están en un fichero nuevo, con un `TestCase` y métodos `test_<behaviour>`. Los ficheros de `tests/` que ya existían no se tocan.

#### Spec
Sin hallazgos. C1 a C10 están cubiertos en `src/textkit/text.py` y `tests/test_longest_word.py`. C9: la entrada está en `__init__.py` y `__all__` sigue ordenado. C10: `architecture.md` y `GLOSSARY.md` se actualizan. No hay alcance de más.

#### Arquitectura
Sin hallazgos. `docs/architecture.md` se actualiza en el mismo diff, tanto la fila de la fachada como la firma de `textkit.text`. No hay dependencias nuevas. Los tests importan solo de la fachada `textkit`.

### Merge

**MERGE:** CONFLICT

#### Conflictos

Al integrar origin/spec/010-estadisticas-de-texto en factory/013-palabra-mas-larga-longest-word:

- GLOSSARY.md
- docs/architecture.md

## Round 2

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_longest_word.py::test_empty_text_is_empty_string — texto vacío devuelve ""
- C2: tests/test_longest_word.py::test_only_punctuation_or_whitespace_is_empty_string — puntuación o espacios devuelven ""
- C3: tests/test_longest_word.py::test_surrounding_punctuation_stripped_and_case_kept — "Extraordinario" sin puntuación y con mayúscula
- C4: tests/test_longest_word.py::test_returns_longest — "perro"
- C5: tests/test_longest_word.py::test_tie_returns_first — empate gana "uno"
- C6: tests/test_longest_word.py::test_same_word_definition_as_word_count — "don't" y "well-known"
- C7: tests/test_longest_word.py::test_accented_letters_count_as_one_and_are_kept — "árbol"
- C8: tests/test_longest_word.py::test_result_is_always_str — resultado str también sin palabras
- C9: tests/test_longest_word.py::test_exported_in_sorted_all — en __all__, ordenado
- C10: tests/test_longest_word.py::test_documented_in_architecture_and_glossary — architecture.md y GLOSSARY.md

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. Función pura, con type hints, que reutiliza `_WORD_RE`. Los tests están en un fichero nuevo, con un TestCase y métodos `test_<behaviour>`.

#### Spec
Sin hallazgos. C1 a C10 están cubiertos por `tests/test_longest_word.py` y por la implementación (`max(..., key=len, default="")`, que devuelve la primera palabra en caso de empate). No hay alcance de más: `GLOSSARY.md` y `architecture.md` los pide el plan.

#### Arquitectura
Sin hallazgos. La interfaz pública nueva (`longest_word`) está en `__all__`, en orden alfabético, y `docs/architecture.md` se actualiza en el mismo diff, tanto en la fila de la fachada como en la de `textkit.text`. No hay dependencias nuevas.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:35+01:00 | (new) | intake | created from #13 for spec 010-estadisticas-de-texto |
| 2026-11-02T12:02:17+01:00 | intake | build | ACCEPT risk=medium surfaces=api |
| 2026-11-02T12:03:15+01:00 | build | gate | READY |
| 2026-11-02T12:03:41+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:04:08+01:00 | review | merging | PASS |
| 2026-11-02T12:11:20+01:00 | merging | merging | recover: released claim merge |
| 2026-11-02T12:11:27+01:00 | merging | build | merge conflict |
| 2026-11-02T12:12:21+01:00 | build | gate | READY |
| 2026-11-02T12:12:29+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:12:56+01:00 | review | merging | PASS |
| 2026-11-02T12:13:15+01:00 | merging | done | merged into spec/010-estadisticas-de-texto |
