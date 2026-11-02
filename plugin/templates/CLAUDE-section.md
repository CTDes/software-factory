## Software factory

- The single source of truth for "is this change OK" is `factory/checks.sh` (CI runs it too).
- Run a single test: <command>.
- Existing tests listed in `factory/config.json` `protected_paths` cannot be modified by the
  factory; it adds new test files instead.
- Public interface: `docs/architecture.md`. Domain vocabulary: `GLOSSARY.md`. Architecture
  decisions: `docs/adr/`.
