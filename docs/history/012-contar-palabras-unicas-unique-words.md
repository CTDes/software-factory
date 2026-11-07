---
job: "012-contar-palabras-unicas-unique-words"
kind: "ticket"
issue: 12
title: "Contar palabras únicas (unique_words)"
spec: "010-estadisticas-de-texto"
stage: "done"
risk: "medium"
surfaces: ["api", "docs"]
rounds: 3
created: "2026-11-02T11:58:34+01:00"
updated: "2026-11-02T12:04:31+01:00"
---

# #12 Contar palabras únicas (unique_words)

`012-contar-palabras-unicas-unique-words` · ticket · stage done · risk medium · surfaces api, docs · 3 rounds · spec [010-estadisticas-de-texto](010-estadisticas-de-texto.md)

## Issue

```text
### Cuerpo

Parent: #10

## What to build

`unique_words(text)` devuelve el número de palabras distintas del texto sin distinguir mayúsculas, con la misma definición de palabra que `word_count`. Ver la spec #10.

## Acceptance criteria

- [ ] `unique_words("")` devuelve 0
- [ ] No distingue mayúsculas: `unique_words("Hola hola HOLA")` devuelve 1, y también `unique_words("ÁRBOL árbol")`
- [ ] Contracciones y palabras con guion cuentan como una palabra, como en `word_count`: `unique_words("don't stop don't well-known")` devuelve 3
- [ ] `unique_words` está en `textkit.__all__`, y `docs/architecture.md` y `GLOSSARY.md` lo documentan
```

## Plan

**DECISION:** ACCEPT · **RISK:** medium · **SURFACES:** api, docs

### Alcance

Añadir la función pura `unique_words(text: str) -> int` a `src/textkit/text.py` y reexportarla
desde la fachada `textkit` (`src/textkit/__init__.py`, en `__all__`, que sigue en orden
alfabético). Devuelve cuántas palabras distintas tiene el texto después de aplicar
`str.casefold()` a cada una. Usa la misma definición de palabra que `word_count`: reutiliza
`_WORD_RE` y no añade ninguna regex nueva.

En el mismo diff:
- `docs/architecture.md`: añadir `unique_words` a las filas de `textkit` y `textkit.text`, con la
  firma `unique_words(text) -> int`.
- `GLOSSARY.md`: añadir el término "unique words" (número de palabras distintas tras casefold,
  con la misma definición de *word*).
- Tests nuevos en `tests/test_unique_words.py`.

Fuera de alcance: `char_count`, `longest_word`, `text_stats` y `format_stats` (son otros
tickets de la spec #10), tokenización según idioma, stemming, stop-words y cualquier cambio
en el comportamiento de las funciones que ya existen.

### Criterios de aceptación

- C1: `unique_words("")` devuelve `0`.
- C2: Un texto sin palabras (solo espacios o puntuación, p. ej. `"  ... ¡! "`) devuelve `0`.
- C3: `unique_words("Hola hola HOLA")` devuelve `1`.
- C4: `unique_words("ÁRBOL árbol")` devuelve `1` (el casefold cubre letras no ASCII).
- C5: `unique_words("don't stop don't well-known")` devuelve `3` (contracciones y palabras con
  guion cuentan como una sola palabra, igual que en `word_count`).
- C6: La puntuación de alrededor no crea palabras distintas: `unique_words("Hola, hola. ¡Hola!")`
  devuelve `1`.
- C7: Palabras diferentes cuentan por separado: `unique_words("el gato y el perro")` devuelve `4`.
- C8: `unique_words` se puede importar desde `textkit` y está en `textkit.__all__`.
- C9: `textkit.__all__` sigue en orden alfabético (`sorted(__all__) == __all__`).
- C10: Para varios textos de ejemplo literales, `unique_words(t) <= word_count(t)`.
- C11: `docs/architecture.md` contiene `unique_words` y `GLOSSARY.md` contiene el término
  "unique words" (o "unique_words"), comprobado leyendo los ficheros.
- C12: `factory/checks.sh` pasa (ruff, ruff format, mypy --strict, unittest, build).

### Seams

- Fachada pública `textkit` (`from textkit import unique_words, word_count`, `textkit.__all__`).
  Los tests nunca importan de `textkit.text`.
- Los tests van en el fichero nuevo `tests/test_unique_words.py`, con un `TestCase`
  (`UniqueWordsTest`) y métodos `test_<behaviour>`. Para C11, el test lee
  `docs/architecture.md` y `GLOSSARY.md` con rutas relativas a la raíz del repo, calculadas a
  partir de `__file__`.
- No se tocan los ficheros de `tests/` que ya existen (están protegidos).

### Notas

- Implementación prevista: `len({w.casefold() for w in _WORD_RE.findall(text)})`. Es una pista
  orientativa, no forma parte de los criterios.
- La base es la rama `spec/010-estadisticas-de-texto`. Hay tickets hermanos (`char_count`,
  `longest_word`) que también editan `__init__.py`, `docs/architecture.md` y `GLOSSARY.md`, así
  que puede haber conflictos de merge triviales. Hay que mantener el orden alfabético de
  `__all__` al resolverlos.
- `text_stats` (otro ticket) dependerá de esta función con la firma exacta
  `unique_words(text: str) -> int`. No hay que cambiarla.
- Los valores esperados de los tests son literales e independientes. No se recalculan como lo
  hace el código (decisión de testing de la spec).
- ADR 0001: solo biblioteca estándar, sin I/O en `src/`.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_unique_words.py::test_empty_text_is_zero — texto vacío da 0
- C2: tests/test_unique_words.py::test_text_without_words_is_zero — solo espacios/puntuación da 0
- C3: tests/test_unique_words.py::test_case_insensitive — "Hola hola HOLA" da 1
- C4: tests/test_unique_words.py::test_casefold_non_ascii — "ÁRBOL árbol" da 1
- C5: tests/test_unique_words.py::test_contractions_and_hyphens_are_single_words — da 3
- C6: tests/test_unique_words.py::test_surrounding_punctuation_ignored — da 1
- C7: tests/test_unique_words.py::test_different_words_counted_separately — da 4
- C8: tests/test_unique_words.py::test_exported_from_facade — está en __all__ e importable
- C9: tests/test_unique_words.py::test_all_is_sorted — __all__ ordenado
- C10: tests/test_unique_words.py::test_never_more_than_word_count — unique_words <= word_count
- C11: tests/test_unique_words.py::test_documented — architecture.md y GLOSSARY.md lo mencionan
- C12: factory/checks.sh en verde (ruff, format, mypy, unittest, build)

### Gate

**GATE:** FAIL · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 2

## Round 2

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_unique_words.py::test_empty_text_is_zero — texto vacío da 0
- C2: tests/test_unique_words.py::test_text_without_words_is_zero — solo espacios/puntuación da 0
- C3: tests/test_unique_words.py::test_case_insensitive — "Hola hola HOLA" da 1
- C4: tests/test_unique_words.py::test_casefold_non_ascii — "ÁRBOL árbol" da 1
- C5: tests/test_unique_words.py::test_contractions_and_hyphens_are_single_words — da 3
- C6: tests/test_unique_words.py::test_surrounding_punctuation_ignored — da 1
- C7: tests/test_unique_words.py::test_different_words_counted_separately — da 4
- C8: tests/test_unique_words.py::test_exported_from_facade — está en __all__ e importable
- C9: tests/test_unique_words.py::test_all_is_sorted — __all__ ordenado
- C10: tests/test_unique_words.py::test_never_more_than_word_count — unique_words <= word_count
- C11: tests/test_unique_words.py::test_documented — architecture.md y GLOSSARY.md lo mencionan
- C12: tests/test_unique_words.py::test_documented — la suite corre dentro de factory/checks.sh, que pasa en verde

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. `unique_words` reutiliza `_WORD_RE` (sin duplicar la regex), es pura y está tipada. Los tests siguen `unittest`, un `TestCase` y nombres `test_<behaviour>`, en un fichero nuevo, sin tocar los existentes.

#### Spec
Sin hallazgos. C1-C7 están cubiertos por tests con valores literales. C8 y C9 se cumplen: `unique_words` está en `__all__`, que sigue ordenado. C10 se cumple con el test de `<= word_count`. C11 se cumple: `architecture.md` y `GLOSSARY.md` lo mencionan. C12 lo confirma el gate en verde. No hay alcance de más: no se añadió `char_count`, `longest_word` ni nada parecido.

#### Arquitectura
Sin hallazgos. Se añade a la interfaz pública y `docs/architecture.md` se actualiza en el mismo diff, en las filas de `textkit` y `textkit.text`. Los tests importan solo desde la fachada `textkit`. No hay dependencias nuevas.

### Merge

**MERGE:** CONFLICT

#### Conflictos

Al integrar origin/spec/010-estadisticas-de-texto en factory/012-contar-palabras-unicas-unique-words:

- GLOSSARY.md
- docs/architecture.md

## Round 3

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_unique_words.py::test_empty_text_is_zero — texto vacío da 0
- C2: tests/test_unique_words.py::test_text_without_words_is_zero — solo espacios/puntuación da 0
- C3: tests/test_unique_words.py::test_case_insensitive — "Hola hola HOLA" da 1
- C4: tests/test_unique_words.py::test_casefold_non_ascii — "ÁRBOL árbol" da 1
- C5: tests/test_unique_words.py::test_contractions_and_hyphens_are_single_words — da 3
- C6: tests/test_unique_words.py::test_surrounding_punctuation_ignored — da 1
- C7: tests/test_unique_words.py::test_different_words_counted_separately — da 4
- C8: tests/test_unique_words.py::test_exported_from_facade — está en __all__ e importable
- C9: tests/test_unique_words.py::test_all_is_sorted — __all__ ordenado
- C10: tests/test_unique_words.py::test_never_more_than_word_count — unique_words <= word_count
- C11: tests/test_unique_words.py::test_documented — architecture.md y GLOSSARY.md lo mencionan
- C12: tests/test_unique_words.py::test_documented — la suite corre dentro de factory/checks.sh, que pasa en verde

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. Función pura, con type hints, stdlib; tests con `unittest`, un `TestCase`, nombres `test_<behaviour>`, fichero nuevo (no toca tests protegidos).

#### Spec
Sin hallazgos. C1-C11 cubiertos por tests con valores literales (`tests/test_unique_words.py`); `unique_words` reutiliza `_WORD_RE` sin regex nueva; `__all__` sigue ordenado (C9); `architecture.md` y `GLOSSARY.md` actualizados (C11). C12 lo da el gate en verde. No hay alcance de más.

#### Arquitectura
Sin hallazgos. La interfaz pública nueva está en `docs/architecture.md` en el mismo diff, en las filas de `textkit` y `textkit.text`. Sin dependencias nuevas y los tests importan solo desde la fachada.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:34+01:00 | (new) | intake | created from #12 for spec 010-estadisticas-de-texto |
| 2026-11-02T11:59:38+01:00 | intake | build | ACCEPT risk=medium surfaces=api,docs |
| 2026-11-02T12:00:25+01:00 | build | gate | READY |
| 2026-11-02T12:00:48+01:00 | gate | build | GATE FAIL round 1 |
| 2026-11-02T12:01:33+01:00 | build | gate | READY |
| 2026-11-02T12:01:54+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:02:24+01:00 | review | merging | PASS |
| 2026-11-02T12:02:41+01:00 | merging | build | merge conflict |
| 2026-11-02T12:03:23+01:00 | build | gate | READY |
| 2026-11-02T12:03:35+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:04:14+01:00 | review | merging | PASS |
| 2026-11-02T12:04:31+01:00 | merging | done | merged into spec/010-estadisticas-de-texto |
