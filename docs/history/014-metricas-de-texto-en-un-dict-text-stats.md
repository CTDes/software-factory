---
job: "014-metricas-de-texto-en-un-dict-text-stats"
kind: "ticket"
issue: 14
title: "Métricas de texto en un dict (text_stats)"
spec: "010-estadisticas-de-texto"
stage: "done"
risk: "medium"
surfaces: ["api", "docs"]
rounds: 2
created: "2026-11-02T11:58:35+01:00"
updated: "2026-11-02T12:15:23+01:00"
---

# #14 Métricas de texto en un dict (text_stats)

`014-metricas-de-texto-en-un-dict-text-stats` · ticket · stage done · risk medium · surfaces api, docs · 2 rounds · spec [010-estadisticas-de-texto](010-estadisticas-de-texto.md)

## Issue

```text
### Cuerpo

Parent: #10
Blocked by: #11, #12

## What to build

`text_stats(text)` devuelve un dict con exactamente las claves `words`, `chars`, `unique_words` y `sentences`, cuyos valores son los de `word_count`, `char_count`, `unique_words` y `sentence_count` del texto. Ver la spec #10.

## Acceptance criteria

- [ ] `text_stats("")` devuelve `{"words": 0, "chars": 0, "unique_words": 0, "sentences": 0}`
- [ ] `text_stats("Hola hola. Adiós!")` devuelve `{"words": 3, "chars": 15, "unique_words": 2, "sentences": 2}`
- [ ] El dict tiene exactamente esas cuatro claves, ni más ni menos
- [ ] `text_stats` está en `textkit.__all__`, y `docs/architecture.md` y `GLOSSARY.md` lo documentan
```

## Plan

**DECISION:** ACCEPT · **RISK:** medium · **SURFACES:** api, docs

### Alcance
Añadir `text_stats(text: str) -> dict[str, int]` en `src/textkit/text.py` y reexportarla desde la
fachada `textkit` (`__all__` en orden alfabético). Devuelve un dict normal con exactamente las claves
`words`, `chars`, `unique_words` y `sentences`, cuyos valores son `word_count(text)`,
`char_count(text)`, `unique_words(text)` y `sentence_count(text)`. Las dependencias de la spec
(#11 `char_count`, #12 `unique_words`) ya están en la base `origin/spec/010-estadisticas-de-texto`.
Actualizar `docs/architecture.md` (fachada y fila de `textkit.text`) y añadir el término
"text stats" a `GLOSSARY.md`. No se cambia el comportamiento de ninguna función existente.

### Criterios de aceptación
- C1: `textkit.text_stats("")` es igual a `{"words": 0, "chars": 0, "unique_words": 0, "sentences": 0}`.
- C2: `textkit.text_stats("Hola hola. Adiós!")` es igual a `{"words": 3, "chars": 15, "unique_words": 2, "sentences": 2}`.
- C3: Para varios textos de ejemplo, el conjunto de claves de `text_stats(text)` es exactamente `{"words", "chars", "unique_words", "sentences"}`.
- C4: El resultado de `text_stats` es una instancia de `dict` (exactamente `type(...) is dict`) y todos sus valores son `int`.
- C5: Para un texto de solo espacios en blanco (p. ej. `" \t\n "`) el resultado son todo ceros.
- C6: Para un texto con varias frases, mayúsculas mezcladas, contracciones y guiones (p. ej. `"Don't stop. DON'T stop! well-known?"`), el dict coincide con un valor literal esperado calculado a mano (words 5, chars 31, unique_words 3, sentences 3).
- C7: `"text_stats"` está en `textkit.__all__` y `textkit.__all__` sigue ordenado alfabéticamente.
- C8: `docs/architecture.md` menciona `text_stats` y `GLOSSARY.md` contiene la entrada "text stats" (comprobable con búsqueda de texto en un test o por el revisor).
- C9: `factory/checks.sh` pasa (ruff, ruff format, mypy --strict, unittest, build).

### Seams
- Seam único: la fachada `textkit` (`from textkit import text_stats`), nunca `textkit.text`.
- Tests en un fichero nuevo `tests/test_text_stats.py` con un único `TestCase` (`TextStatsTest`) y métodos `test_<comportamiento>`, comparando el dict completo con literales independientes. No se modifican ficheros existentes de `tests/`.

### Notas
- Verificación manual de C6: palabras `Don't`, `stop`, `DON'T`, `stop`, `well-known` = 5; distintas tras casefold `don't`, `stop`, `well-known` = 3; frases 3; caracteres no-espacio: "Don't"5 + "stop."5 + "DON'T"5 + "stop!"5 + "well-known?"11 = 31. El implementador debe confirmar el literal; si discrepa, el valor correcto es el que sale de aplicar las definiciones del GLOSSARY, no el de la implementación.
- C2: "Hola"(4) + "hola."(5) + "Adiós!"(6) = 15 caracteres; la "ó" precompuesta cuenta como uno.
- Implementación trivial: componer las cuatro funciones existentes; no duplicar regex.
- Cambia la interfaz pública: actualizar `docs/architecture.md` en el mismo diff (CLAUDE.md).
- `format_stats` (otro ticket de la spec) dependerá de esta firma y de los nombres de clave exactos.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_text_stats.py::test_empty_text_is_all_zeros — texto vacío da todo ceros
- C2: tests/test_text_stats.py::test_simple_example — "Hola hola. Adiós!" da 3/15/2/2
- C3: tests/test_text_stats.py::test_keys_are_exactly_the_four_metrics — claves exactas
- C4: tests/test_text_stats.py::test_result_is_plain_dict_of_ints — type is dict y valores int
- C5: tests/test_text_stats.py::test_whitespace_only_is_all_zeros — solo espacios da ceros
- C6: tests/test_text_stats.py::test_mixed_case_contractions_and_hyphens — literal 5/31/3/3
- C7: tests/test_text_stats.py::test_exported_and_all_sorted — en __all__ y ordenado
- C8: tests/test_text_stats.py::test_documented_in_architecture_and_glossary — docs y glosario
- C9: tests/test_text_stats.py::test_simple_example — factory/checks.sh en verde (ruff, format, mypy, unittest, build)

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. `text_stats` compone las cuatro funciones existentes sin duplicar lógica. Tiene type hints y docstring con ejemplo. Los tests usan `unittest`, un `TestCase` y nombres `test_<comportamiento>`, en un fichero nuevo.

#### Spec
Sin hallazgos. C1 y C2 están en `tests/test_text_stats.py` (`test_empty_text_is_all_zeros`, `test_simple_example`). C3 y C4 también, y la implementación devuelve un `dict` literal con las cuatro claves. C5 lo cubre `test_whitespace_only_is_all_zeros` y C6 `test_mixed_case_contractions_and_hyphens`, con los literales del plan. C7 está en `__init__.py`, que mantiene `__all__` ordenado, y en `test_exported_and_all_sorted`. C8 se cumple con la entrada de `GLOSSARY.md`, los cambios de `docs/architecture.md` y el test que los comprueba. C9 lo da por verde el gate. No hay alcance de más.

#### Arquitectura
Sin hallazgos. `text.py` no importa la fachada y solo usa la biblioteca estándar. Los tests importan desde `textkit`. `docs/architecture.md` se actualiza en el mismo diff, tanto la fachada como la fila de `textkit.text`.

### Merge

**MERGE:** CONFLICT

#### Conflictos

Al integrar origin/spec/010-estadisticas-de-texto en factory/014-metricas-de-texto-en-un-dict-text-stats:

- GLOSSARY.md
- docs/architecture.md
- src/textkit/text.py

## Round 2

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_text_stats.py::test_empty_text_is_all_zeros — texto vacío da todo ceros
- C2: tests/test_text_stats.py::test_simple_example — "Hola hola. Adiós!" da 3/15/2/2
- C3: tests/test_text_stats.py::test_keys_are_exactly_the_four_metrics — claves exactas
- C4: tests/test_text_stats.py::test_result_is_plain_dict_of_ints — type is dict y valores int
- C5: tests/test_text_stats.py::test_whitespace_only_is_all_zeros — solo espacios da ceros
- C6: tests/test_text_stats.py::test_mixed_case_contractions_and_hyphens — literal 5/31/3/3
- C7: tests/test_text_stats.py::test_exported_and_all_sorted — en __all__ y ordenado
- C8: tests/test_text_stats.py::test_documented_in_architecture_and_glossary — docs y glosario
- C9: tests/test_text_stats.py::test_simple_example — factory/checks.sh en verde (ruff, format, mypy, unittest, build)

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. `text_stats` compone las funciones existentes sin duplicar lógica, con type hints completos. Los tests están en un fichero nuevo, con un único `TestCase` y métodos `test_<comportamiento>`. No se tocan ficheros existentes de `tests/`.

#### Spec
Sin hallazgos. C1 a C8 están cubiertos por tests y por el diff, y C9 lo confirma el gate. No hay alcance de más: el diff solo toca `text.py`, `__init__.py`, `architecture.md`, `GLOSSARY.md` y el test nuevo.

#### Arquitectura
Sin hallazgos. La interfaz pública cambia y `docs/architecture.md` se actualiza en el mismo diff, tanto en la fachada como en la fila de `textkit.text`. No hay dependencias nuevas.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:35+01:00 | (new) | intake | created from #14 for spec 010-estadisticas-de-texto |
| 2026-11-02T12:12:01+01:00 | intake | build | ACCEPT risk=medium surfaces=api,docs |
| 2026-11-02T12:12:50+01:00 | build | gate | READY |
| 2026-11-02T12:13:10+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:13:39+01:00 | review | merging | PASS |
| 2026-11-02T12:13:43+01:00 | merging | build | merge conflict |
| 2026-11-02T12:14:35+01:00 | build | gate | READY |
| 2026-11-02T12:14:41+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:15:06+01:00 | review | merging | PASS |
| 2026-11-02T12:15:23+01:00 | merging | done | merged into spec/010-estadisticas-de-texto |
