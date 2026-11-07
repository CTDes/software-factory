---
job: "004-truncate-corta-a-mitad-de-palabra-si-el"
kind: "ticket"
issue: 4
title: "truncate corta a mitad de palabra si el separador es un tabulador o un salto de línea"
pr: 7
stage: "done"
risk: "low"
surfaces: []
rounds: 1
created: "2026-11-02T10:52:43+01:00"
updated: "2026-11-02T11:20:14+01:00"
---

# #4 truncate corta a mitad de palabra si el separador es un tabulador o un salto de línea

`004-truncate-corta-a-mitad-de-palabra-si-el` · ticket · stage done · risk low · surfaces none · 1 round · PR #7

## Issue

````text
### Cuerpo

Pasos para reproducir:

```python
>>> from textkit import truncate
>>> truncate("uno\tdos tres", 6)
"uno\td…"
```

Esperado: `"uno…"`. Con un espacio normal funciona bien (`truncate("uno dos tres", 6)` da `"uno…"`). Parece que solo se busca el espacio `" "` como frontera de palabra y no cualquier espacio en blanco.
````

## Plan

**DECISION:** ACCEPT · **RISK:** low · **SURFACES:** none

### Alcance

Bug en `truncate` (`src/textkit/text.py`). Hoy, cuando el corte cae a mitad de palabra, la
función busca la frontera de palabra solo con el espacio literal `" "` (`" " in cut` /
`cut.rfind(" ")`), aunque para decidir si el corte cae en una frontera ya usa
`str.isspace()`. Por eso `truncate("uno\tdos tres", 6)` devuelve `"uno\td…"` en vez de
`"uno…"`. Lo reproduje leyendo el código: con room=5, cut=`"uno\td"`, text[5]=`"o"` y no hay
`" "` en cut.

El arreglo: que cualquier carácter de espacio en blanco (el mismo criterio que `str.isspace()`:
tabulador, salto de línea, retorno de carro, etc.) cuente como frontera de palabra al buscar el
último punto de corte. La firma no cambia, `__all__` no cambia y la interfaz pública tampoco.
Los demás casos se comportan igual que ahora: texto que ya cabe, palabra única sin espacios
(corte duro), sufijo personalizado y `ValueError` cuando `limit < len(suffix)`.

Fuera de alcance: cambiar la definición de "word" del glosario (`_WORD_RE`) o la de otras
funciones.

### Criterios de aceptación

- C1: `truncate("uno\tdos tres", 6) == "uno…"`.
- C2: `truncate("uno\ndos tres", 6) == "uno…"`.
- C3: `truncate("uno\r\ndos tres", 7) == "uno…"`. Con un CRLF no queda ningún espacio en blanco antes del sufijo.
- C4: Separadores mezclados: `truncate("uno dos\ttres", 10) == "uno dos…"`. Se corta en el último espacio en blanco que cabe, aunque no sea `" "`.
- C5: No quedan espacios en blanco antes del sufijo: `truncate("uno\t\tdos", 7) == "uno…"`.
- C6: Lo que ya funcionaba sigue igual: `truncate("uno dos tres", 6) == "uno…"`, `truncate("supercalifragilistic", 6) == "super…"`, `truncate("hola", 10) == "hola"`, y los tests existentes de `tests/test_text.py` siguen pasando sin modificarlos.
- C7: Para textos con tabuladores o saltos de línea y límites entre `len(suffix)` y `len(text)`, `len(truncate(text, limit)) <= limit`.

### Seams

- Seam: la función pública `textkit.truncate(text, limit, suffix="…")`. Los tests la importan desde
  `textkit`, nunca desde `textkit.text`.
- Tests nuevos en un fichero nuevo, p. ej. `tests/test_truncate_whitespace.py`, con un `TestCase`
  para `truncate` y métodos `test_<behaviour>`. `tests/test_text.py` está protegido y no se
  toca.

### Notas

- Cambio local dentro de `truncate`. Valen tanto un `re` de la stdlib (`\s`) como recorrer los
  caracteres con `str.isspace()`, siempre que el criterio coincida con el `text[room].isspace()`
  que ya existe.
- Como la interfaz pública no cambia, no hay que actualizar `docs/architecture.md`. Puede valer
  la pena precisar en el docstring que la frontera de palabra es cualquier espacio en blanco.
  `GLOSSARY.md` ("cutting at a word boundary") ya lo cubre.
- Validar con `factory/checks.sh`.

## Round 1

### Build

**STATUS:** READY

#### Evidencia

- C1: tests/test_truncate_whitespace.py::test_tab_is_word_boundary — tabulador como frontera
- C2: tests/test_truncate_whitespace.py::test_newline_is_word_boundary — salto de línea como frontera
- C3: tests/test_truncate_whitespace.py::test_crlf_leaves_no_whitespace_before_suffix — CRLF sin espacio antes del sufijo
- C4: tests/test_truncate_whitespace.py::test_mixed_separators_cut_at_last_whitespace — separadores mezclados
- C5: tests/test_truncate_whitespace.py::test_consecutive_whitespace_is_stripped — espacios consecutivos eliminados
- C6: tests/test_truncate_whitespace.py::test_previous_behaviour_unchanged — casos previos intactos
- C7: tests/test_truncate_whitespace.py::test_result_never_exceeds_limit — longitud <= limit

### Gate

**GATE:** PASS · **PROTECTED:** none

#### Resumen

- checks.sh: OK
- Rutas protegidas modificadas o borradas: 0
- Problemas de evidencia: 0

### Review

**VERDICT:** PASS

#### Estándares

Sin hallazgos.

Revisado contra CLAUDE.md (type hints completos, `unittest` con un `TestCase` por función pública y `test_<behaviour>`, ficheros protegidos de `tests/` no tocados) y la línea de docstring (98 caracteres, dentro del `line-length = 100` de `pyproject.toml`). `CODING_STANDARDS.md` y `CONTRIBUTING.md` no existen en el worktree. No hay smells relevantes en el cambio: la búsqueda del último espacio en blanco es una sola pasada y el nombre `last` es explícito.

#### Spec

Sin hallazgos.

- C1 (`truncate("uno\tdos tres", 6)`): room=5, `text[5]` es `o`, el último espacio en blanco de `"uno\td"` está en el índice 3, resultado `"uno…"`. Cumple.
- C2 (`\n`): mismo razonamiento que C1. Cumple.
- C3 (`"uno\r\ndos tres", 7`): room=6, el `\n` está en el índice 4, `cut[:4]="uno\r"`, rstrip deja `"uno…"`. Cumple.
- C4 (`"uno dos\ttres", 10`): room=9, `text[9]="r"`, el `\t` en el índice 7, resultado `"uno dos…"`. Cumple.
- C5 (`"uno\t\tdos", 7`): room=6, el último espacio en blanco de `cut` está en el índice 4, rstrip elimina el tabulador restante, resultado `"uno…"`. Cumple.
- C6: la lógica de `" "` se sustituye por el mismo criterio `isspace()` que ya usaba la guarda, así que `"uno dos tres"`, `"supercalifragilistic"` y `"hola"` siguen igual. Los tests existentes de `tests/test_text.py` no aparecen en el diff. Cumple.
- C7: `test_result_never_exceeds_limit` recorre límites de 1 a `len(text)` sobre textos con tabuladores, saltos de línea y CRLF. Cumple.
- Alcance: el diff toca solo `src/textkit/text.py` (cuerpo de `truncate` y docstring) y añade `tests/test_truncate_whitespace.py`, que es el fichero previsto en el plan. `_WORD_RE` y el resto de funciones no cambian. No hay alcance de más.

#### Arquitectura

Sin hallazgos.

- La firma de `truncate`, `__all__` y la interfaz pública de `textkit` no cambian, así que `docs/architecture.md` no necesita actualizarse, como indica el plan.
- El cambio no añade imports. `textkit.text` sigue sin importar el facade, `src/` no importa de `tests/` ni de `factory/`, y no hay I/O.
- El test importa `truncate` desde `textkit` (seam correcto), no desde `textkit.text`.
- No se toca ninguna carpeta protegida (`factory/`, `.claude/`, `.github/`, ni ficheros existentes de `tests/`).

## Timeline

| Time | From | To | Reason |
| --- | --- | --- | --- |
| 2026-11-02T10:52:43+01:00 | (new) | intake | created from #4 |
| 2026-11-02T10:53:38+01:00 | intake | build | ACCEPT risk=low surfaces=none |
| 2026-11-02T10:54:26+01:00 | build | gate | READY |
| 2026-11-02T10:54:53+01:00 | gate | review | GATE PASS |
| 2026-11-02T10:55:43+01:00 | review | ready | PASS |
| 2026-11-02T11:20:14+01:00 | ready | done | PR #7 merged |
