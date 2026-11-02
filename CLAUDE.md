# textkit

Small Python text-utilities library (`src/textkit/`). It exists to exercise the software factory
described in `plugin/DESIGN.md` (packaged as the `software-factory` plugin in `plugin/`); keep it small and well tested.

## Setup and validation

- Requirements: Python 3.10+. No runtime dependencies; dev tools live in `requirements-dev.txt`.
- The single source of truth for "is this change OK" is `factory/checks.sh`. It creates `.venv/`
  on first run, then runs, in order: `ruff check`, `ruff format --check`, `mypy --strict`,
  `unittest` over `tests/`, and a wheel build. CI runs the same script.
- Run a single test: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_text -k slugify`
  (from the repo root, after `factory/checks.sh` has created the venv).
- Format before committing: `.venv/bin/python -m ruff format .` (checks.sh only verifies, never fixes).

## Conventions

- Public API is whatever `src/textkit/__init__.py` exports in `__all__`. Changing it means updating
  `docs/architecture.md` in the same diff.
- Pure functions, standard library only, full type hints (mypy strict).
- Tests use `unittest`, one `TestCase` per public function, named `test_<behaviour>`.
- Existing files under `tests/` are protected: the factory gate fails if a branch modifies or
  deletes them. Add new test files or new test classes in new files instead.
- Domain vocabulary: `GLOSSARY.md`. Architecture decisions: `docs/adr/`.
