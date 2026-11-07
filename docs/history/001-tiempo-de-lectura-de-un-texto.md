---
job: "001-tiempo-de-lectura-de-un-texto"
kind: "ticket"
issue: 1
title: "Tiempo de lectura de un texto"
pr: 2
stage: "done"
risk: "low"
surfaces: []
rounds: 1
created: "2026-11-02T09:18:49+01:00"
updated: "2026-11-02T10:17:16+01:00"
---

# #1 Tiempo de lectura de un texto

`001-tiempo-de-lectura-de-un-texto` · ticket · stage done · risk low · surfaces none · 1 round · PR #2

## Issue

```text
### Cuerpo

Queremos una función `reading_time(text, wpm=200)` que devuelva los minutos de lectura estimados, redondeando hacia arriba, con un mínimo de 1 minuto para cualquier texto con al menos una palabra y 0 para un texto vacío.

Usa la misma definición de palabra que `word_count`.
```

## Plan

**DECISION:** ACCEPT · **RISK:** low · **SURFACES:** none

### Alcance

Nueva función pública `textkit.reading_time(text, wpm=200) -> int` en `src/textkit/text.py`,
exportada en `textkit.__all__`. Reutiliza `word_count`.

### Criterios de aceptación

- C1: `reading_time("")` devuelve 0
- C2: un texto de 1 a 200 palabras devuelve 1 con wpm por defecto
- C3: 201 palabras devuelven 2 (redondeo hacia arriba)
- C4: `wpm` <= 0 lanza `ValueError`

### Seams

`textkit.reading_time` (fachada pública). Tests nuevos en `tests/test_reading_time.py`.

### Notas

Actualizar `docs/architecture.md` y `GLOSSARY.md` porque cambia la interfaz pública.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_reading_time.py::test_empty_text_is_zero_minutes — texto vacío da 0
- C2: tests/test_reading_time.py::test_up_to_wpm_words_is_one_minute — 1 y 200 palabras dan 1
- C3: tests/test_reading_time.py::test_rounds_up — 201 palabras dan 2
- C4: tests/test_reading_time.py::test_non_positive_wpm_is_rejected — wpm=0 lanza ValueError

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares

- Sin hallazgos. Función pura, tipada, docstring.

#### Spec

- C1–C4 cubiertos por tests nuevos; no sobra nada.

#### Arquitectura

- `docs/architecture.md` actualizado con la nueva interfaz pública; solo stdlib (`math`).

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T09:18:49+01:00 | (new) | intake | created from #1 |
| 2026-11-02T09:19:05+01:00 | intake | build | ACCEPT risk=low surfaces=none |
| 2026-11-02T09:19:40+01:00 | build | gate | READY |
| 2026-11-02T09:19:50+01:00 | gate | review | GATE PASS |
| 2026-11-02T09:20:04+01:00 | review | ready | PASS |
| 2026-11-02T10:17:16+01:00 | ready | done | PR #2 merged |
