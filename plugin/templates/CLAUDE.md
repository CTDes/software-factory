# <project>

<One paragraph: what this project is.>

## Setup and validation

- The single source of truth for "is this change OK" is `factory/checks.sh` (CI runs it too).
- <How to install, run one test, format code.>

## Conventions

- <Public interface and where it is documented (docs/architecture.md).>
- <Test conventions. Existing tests listed in factory/config.json `protected_paths` cannot be
  modified by the factory; it adds new test files instead.>
- Domain vocabulary: `GLOSSARY.md`. Architecture decisions: `docs/adr/`.
