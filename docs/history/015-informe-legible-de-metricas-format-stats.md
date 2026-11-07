---
job: "015-informe-legible-de-metricas-format-stats"
kind: "ticket"
issue: 15
title: "Informe legible de métricas (format_stats)"
spec: "010-estadisticas-de-texto"
stage: "done"
risk: "medium"
surfaces: ["api"]
rounds: 2
created: "2026-11-02T11:58:36+01:00"
updated: "2026-11-02T12:18:19+01:00"
---

# #15 Informe legible de métricas (format_stats)

`015-informe-legible-de-metricas-format-stats` · ticket · stage done · risk medium · surfaces api · 2 rounds · spec [010-estadisticas-de-texto](010-estadisticas-de-texto.md)

## Issue

```text
### Cuerpo

Parent: #10
Blocked by: #14

## What to build

`format_stats(text)` devuelve un informe de cuatro líneas, calculado a partir de `text_stats`, con el formato fijo de la spec #10: `Palabras: <n>`, `Caracteres: <n>`, `Palabras únicas: <n>` y `Frases: <n>`, unidas por `\n` y sin salto de línea final.

## Acceptance criteria

- [ ] `format_stats("Hola hola. Adiós!")` devuelve exactamente `"Palabras: 3\nCaracteres: 15\nPalabras únicas: 2\nFrases: 2"`
- [ ] `format_stats("")` devuelve las cuatro líneas con valor 0
- [ ] La salida no termina en salto de línea
- [ ] `format_stats` está en `textkit.__all__`, y `docs/architecture.md` lo documenta
```

## Plan

**DECISION:** ACCEPT · **RISK:** medium · **SURFACES:** api

### Alcance

Añadir la función pura `format_stats(text: str) -> str` en `src/textkit/text.py`, construida
únicamente a partir de `text_stats(text)` (ya existe en la base `spec/010-estadisticas-de-texto`,
ticket #14 resuelto). Devuelve exactamente cuatro líneas unidas por `\n`, sin salto de línea final,
en este orden y redacción:

```
Palabras: <words>
Caracteres: <chars>
Palabras únicas: <unique_words>
Frases: <sentences>
```

- Reexportarla desde `src/textkit/__init__.py` (import y `__all__`, manteniendo el orden alfabético).
- Actualizar `docs/architecture.md` (fila de la fachada `textkit` y fila de `textkit.text` con la
  firma `format_stats(text) -> str`).
- Opcional: entrada en `GLOSSARY.md` si se introduce un término nuevo (p. ej. "stats report").
- Tests en un fichero nuevo `tests/test_format_stats.py`.

Fuera de alcance: formatos localizados o configurables, impresión/E/S, cambios en funciones
existentes (incluida `text_stats`).

### Criterios de aceptación

- C1: `textkit.format_stats("Hola hola. Adiós!")` devuelve exactamente
  `"Palabras: 3\nCaracteres: 15\nPalabras únicas: 2\nFrases: 2"`.
- C2: `textkit.format_stats("")` devuelve exactamente
  `"Palabras: 0\nCaracteres: 0\nPalabras únicas: 0\nFrases: 0"`.
- C3: Para varios textos de ejemplo (incluido uno que termina en `\n` y uno solo con espacios),
  la salida no termina en `\n` y `salida.split("\n")` tiene exactamente 4 elementos.
- C4: Para un texto con varias frases y palabras repetidas en distinta capitalización
  (p. ej. `"Uno dos. DOS tres! ¿Tres?"`), la salida es exactamente
  `"Palabras: 5\nCaracteres: 21\nPalabras únicas: 3\nFrases: 3"` (valores literales, coherentes
  con `text_stats`).
- C5: `"format_stats" in textkit.__all__` y `textkit.__all__` sigue ordenado alfabéticamente.
- C6: `docs/architecture.md` menciona `format_stats` (comprobable por búsqueda de texto en el fichero).
- C7: `factory/checks.sh` pasa (ruff, ruff format, mypy --strict, unittest, build).

### Seams

- Fachada pública `textkit` (`from textkit import format_stats`); los tests nunca importan de
  `textkit.text`.
- Tests en el fichero nuevo `tests/test_format_stats.py`, un único `TestCase`
  (`FormatStatsTest`) con métodos `test_<behaviour>`. No se modifica ningún fichero existente
  de `tests/`.

### Notas

- Dependencia #14 (`text_stats`) ya presente en la base: `text_stats("Hola hola. Adiós!")` ->
  `{"words": 3, "chars": 15, "unique_words": 2, "sentences": 2}`, coherente con C1.
- C4 verificado a mano: palabras Uno, dos, DOS, tres, Tres = 5; únicas {uno, dos, tres} = 3;
  frases "Uno dos." "DOS tres!" "¿Tres?" = 3; caracteres no blancos: Uno(3)+dos.(4)+DOS(3)+
  tres!(5)+¿Tres?(6) = 21. El implementador puede sustituir este ejemplo por otro equivalente
  siempre que el valor esperado sea literal y no recalculado.
- Implementación sugerida: construir las líneas desde el dict de `text_stats` y unir con `"\n"`;
  la etiqueta "Palabras únicas" lleva tilde (UTF-8 en el fuente).
- Cambia la interfaz pública (nueva función en `__all__`), de ahí RISK medium.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_format_stats.py::test_formats_example_text — salida exacta para "Hola hola. Adiós!"
- C2: tests/test_format_stats.py::test_empty_text_reports_zeros — texto vacío da ceros
- C3: tests/test_format_stats.py::test_always_four_lines_without_trailing_newline — 4 líneas y sin \n final
- C4: tests/test_format_stats.py::test_repeated_words_with_different_case — valores literales con capitalización mixta
- C5: tests/test_format_stats.py::test_exported_and_all_sorted — exportada y __all__ ordenado
- C6: docs/architecture.md menciona format_stats (filas de fachada y textkit.text)
- C7: factory/checks.sh en verde

### Gate

**GATE:** FAIL · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 4

## Round 2

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_format_stats.py::test_formats_example_text — salida exacta para "Hola hola. Adiós!"
- C2: tests/test_format_stats.py::test_empty_text_reports_zeros — texto vacío da ceros
- C3: tests/test_format_stats.py::test_always_four_lines_without_trailing_newline — 4 líneas y sin \n final
- C4: tests/test_format_stats.py::test_repeated_words_with_different_case — valores literales con capitalización mixta
- C5: tests/test_format_stats.py::test_exported_and_all_sorted — exportada y __all__ ordenado
- C6: tests/test_format_stats_docs.py::test_architecture_mentions_format_stats — docs/architecture.md menciona format_stats
- C7: tests/test_format_stats.py::test_formats_example_text — la suite completa corre dentro de factory/checks.sh, que pasa en verde

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares
- tests/test_format_stats_docs.py: segundo fichero de tests con un TestCase que solo busca texto en architecture.md; es frágil y poco habitual, pero cumple las convenciones (unittest, `test_<behaviour>`, fichero nuevo, no toca tests existentes). [no bloquea]
- src/textkit/text.py:118-133: función pura, con tipos y docstring, sin smells relevantes.

#### Spec
- C1-C5: cubiertos por tests/test_format_stats.py con valores literales; la implementación coincide con el formato pedido (cuatro líneas, orden y etiquetas exactos, sin `\n` final). `__all__` sigue ordenado.
- C6: docs/architecture.md menciona `format_stats` en la fila de la fachada y en la de `textkit.text`.
- C7: el gate está en verde, según el prompt.
- tests/test_format_stats_docs.py: los Seams piden un único TestCase en `tests/test_format_stats.py`, y este fichero extra no se pidió. Es solo un test que comprueba C6, sin código de producción añadido, así que no lo trato como alcance de más. [no bloquea]

#### Arquitectura
Sin hallazgos. La interfaz pública nueva (`format_stats`) está documentada en docs/architecture.md dentro del mismo diff. No hay dependencias nuevas y el módulo solo usa `text_stats`.

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T11:58:36+01:00 | (new) | intake | created from #15 for spec 010-estadisticas-de-texto |
| 2026-11-02T12:16:08+01:00 | intake | build | ACCEPT risk=medium surfaces=api |
| 2026-11-02T12:16:50+01:00 | build | gate | READY |
| 2026-11-02T12:16:57+01:00 | gate | build | GATE FAIL round 1 |
| 2026-11-02T12:17:27+01:00 | build | gate | READY |
| 2026-11-02T12:17:35+01:00 | gate | review | GATE PASS |
| 2026-11-02T12:18:02+01:00 | review | merging | PASS |
| 2026-11-02T12:18:19+01:00 | merging | done | merged into spec/010-estadisticas-de-texto |
