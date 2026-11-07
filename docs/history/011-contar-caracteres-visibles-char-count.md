---
job: "011-contar-caracteres-visibles-char-count"
kind: "ticket"
issue: 11
title: "Contar caracteres visibles (char_count)"
spec: "010-estadisticas-de-texto"
stage: "done"
risk: "medium"
surfaces: ["api", "docs"]
rounds: 1
created: "2026-11-02T11:58:34+01:00"
updated: "2026-11-02T12:01:33+01:00"
---

# #11 Contar caracteres visibles (char_count)

`011-contar-caracteres-visibles-char-count` · ticket · stage done · risk medium · surfaces api, docs · 1 round · spec [010-estadisticas-de-texto](010-estadisticas-de-texto.md)

## Issue

```text
### Cuerpo

Parent: #10

## What to build

`char_count(text)` devuelve el número de caracteres que no son espacio en blanco del texto, importable desde `textkit`. Ver la spec #10.

## Acceptance criteria

- [ ] `char_count("")` y un texto solo con espacios, tabuladores y saltos de línea devuelven 0
- [ ] Espacios, tabuladores y saltos de línea no cuentan; puntuación y dígitos sí (`char_count(" a b\tc\n1!")` devuelve 5)
- [ ] Una letra acentuada cuenta como un carácter (`char_count("árbol")` devuelve 5)
- [ ] `char_count` está en `textkit.__all__`, y `docs/architecture.md` y `GLOSSARY.md` lo documentan
```

## Plan

**DECISION:** ACCEPT · **RISK:** medium · **SURFACES:** api, docs

### Alcance
Añadir la función pura `char_count(text: str) -> int` en `src/textkit/text.py`, que devuelve el
número de caracteres (puntos de código) `ch` del texto para los que `ch.isspace()` es falso.
Reexportarla desde `src/textkit/__init__.py` (import y `__all__`, en orden alfabético).
Documentarla en `docs/architecture.md` (tabla de módulos: facade y `textkit.text`) y añadir el
término "char count" a `GLOSSARY.md`. Tests en un fichero nuevo `tests/test_char_count.py`.
Solo biblioteca estándar, tipado completo (mypy strict), sin I/O.

Fuera de alcance: `unique_words`, `longest_word`, `text_stats`, `format_stats` (otros tickets de
la spec #10); conteo por clústeres de grafemas (los caracteres combinantes cuentan como puntos de
código); cambios en funciones existentes.

### Criterios de aceptación
- C1: `char_count("")` devuelve 0.
- C2: Un texto formado solo por espacios, tabuladores y saltos de línea (p. ej. `" \t\n  \r\n"`) devuelve 0.
- C3: `char_count(" a b\tc\n1!")` devuelve 5 (espacios, tabuladores y saltos de línea no cuentan; puntuación y dígitos sí).
- C4: Otros espacios Unicode tampoco cuentan: `char_count("a b c")` devuelve 3 y `char_count("  ")` devuelve 0.
- C5: Una letra acentuada precompuesta cuenta como un carácter: `char_count("árbol")` devuelve 5.
- C6: Puntuación española cuenta: `char_count("¡Hola!")` devuelve 6.
- C7: `char_count` es importable con `from textkit import char_count`, figura en `textkit.__all__`, y `__all__` sigue en orden alfabético.
- C8: El valor devuelto es de tipo `int`.
- C9: `docs/architecture.md` menciona `char_count` en la fila del facade y su firma `char_count(text) -> int` en la fila de `textkit.text`; `GLOSSARY.md` contiene una entrada para el término (comprobable por búsqueda de texto).
- C10: `factory/checks.sh` pasa (ruff, ruff format, mypy --strict, unittest, build) sin modificar ningún fichero existente bajo `tests/`.

### Seams
- Seam único: el facade `textkit` (`from textkit import char_count`); los tests nunca importan de `textkit.text`.
- Tests en el fichero nuevo `tests/test_char_count.py`, con un único `TestCase` (`CharCountTest` o similar) y métodos `test_<behaviour>`, siguiendo como prior art `tests/test_sentence_count.py` y `tests/test_normalize.py`. Valores esperados literales, sin recalcular con `isspace`.
- C9 puede verificarse leyendo `docs/architecture.md` y `GLOSSARY.md` desde el test relativo a la raíz del repo, o quedar para revisión; C10 lo verifica `factory/checks.sh`.

### Notas
- Riesgo medium porque añade interfaz pública (`__all__`), aunque el cambio es local y aditivo.
- Pieza independiente dentro de la spec #10; `text_stats` dependerá de ella con la firma `char_count(text: str) -> int`, que no debe variar.
- Otros tickets de la spec tocarán las mismas líneas de `__init__.py`, `docs/architecture.md` y `GLOSSARY.md`; mantener el orden alfabético facilita resolver conflictos de merge.
- La issue no contiene instrucciones dirigidas al agente; nada sospechoso.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_char_count.py::test_empty_text_is_zero — texto vacío devuelve 0
- C2: tests/test_char_count.py::test_only_ascii_whitespace_is_zero — solo espacios, tabs y saltos devuelve 0
- C3: tests/test_char_count.py::test_whitespace_excluded_punctuation_and_digits_counted — " a b\tc\n1!" devuelve 5
- C4: tests/test_char_count.py::test_unicode_spaces_do_not_count — espacios Unicode no cuentan
- C5: tests/test_char_count.py::test_precomposed_accent_is_one_character — "árbol" devuelve 5
- C6: tests/test_char_count.py::test_spanish_punctuation_counts — "¡Hola!" devuelve 6
- C7: tests/test_char_count.py::test_exported_and_sorted — exportada en __all__ y orden alfabético
- C8: tests/test_char_count.py::test_returns_int — tipo int
- C9: tests/test_char_count.py::test_documented — architecture.md y GLOSSARY.md mencionan el término
- C10: tests/test_char_count.py::test_documented — checks.sh en verde sin tocar tests existentes (verificado ejecutando factory/checks.sh)

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
Sin hallazgos. Función pura, stdlib, tipada; un TestCase por función pública con métodos `test_<behaviour>`; tests nuevos en fichero nuevo, sin tocar los existentes.

#### Spec
Sin hallazgos. C1 a C9 cubiertos por la implementación y por `tests/test_char_count.py` (C4 con espacios Unicode   y  , C9 con comprobación de texto en architecture.md y GLOSSARY.md). C10 lo verifica el gate. No hay alcance de más: solo `char_count`, reexport, docs y glosario.

#### Arquitectura
Sin hallazgos. `text.py` no importa del facade; `architecture.md` actualizado en el mismo diff (fila del facade y firma en `textkit.text`); tests importan desde `textkit`.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:34+01:00 | (new) | intake | created from #11 for spec 010-estadisticas-de-texto |
| 2026-11-02T11:59:29+01:00 | intake | build | ACCEPT risk=medium surfaces=api,docs |
| 2026-11-02T12:00:34+01:00 | build | gate | READY |
| 2026-11-02T12:00:48+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:01:15+01:00 | review | merging | PASS |
| 2026-11-02T12:01:33+01:00 | merging | done | merged into spec/010-estadisticas-de-texto |
