# Architecture

## Modules

| Module | Responsibility | Public interface |
| --- | --- | --- |
| `textkit` (`src/textkit/__init__.py`) | Package facade; the only supported import path | re-exports `char_count`, `slugify`, `word_count`, `truncate`, `initials`, `reading_time`, `sentence_count`, `normalize`, `longest_word` |
| `textkit.text` (`src/textkit/text.py`) | Pure string functions | `slugify(text, max_length=None) -> str`, `word_count(text) -> int`, `truncate(text, limit, suffix="…") -> str`, `initials(name) -> str`, `reading_time(text, wpm=200) -> int`, `sentence_count(text) -> int`, `normalize(text) -> str`, `char_count(text) -> int`, `longest_word(text) -> str` |

## Allowed dependencies

- `textkit.*` may import only the Python standard library. No third-party runtime dependencies.
- `textkit.text` must not import from `textkit` (the facade); new modules follow the same rule.
- Nothing under `src/` may import from `tests/` or `factory/`.
- No I/O (files, network, environment variables, printing) in `src/`.

## Folder ownership

| Folder | Owner | Notes |
| --- | --- | --- |
| `src/textkit/` | project | new functionality goes here |
| `tests/` | project | existing files are protected; add new files |
| `docs/` | project | update `architecture.md` when a public interface changes |
| `factory/`, `.claude/`, `.github/` | factory / humans | protected; agents must not modify |

## Test seams

The public functions exported by `textkit` are the seams. Tests import from `textkit`, never from
`textkit.text`.
