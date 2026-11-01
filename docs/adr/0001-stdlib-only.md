# 0001 · Standard library only

- Status: accepted
- Date: 2026-11-01

## Context

textkit is a playground for the software factory. Dependencies would add install time to every
fresh worktree and noise to reviews.

## Decision

`src/textkit` uses only the Python standard library. Dev tooling (ruff, mypy, setuptools) is allowed
in `requirements-dev.txt`.

## Consequences

Features that would normally pull a library (e.g. HTML parsing) must be implemented with `re`,
`html` or other stdlib modules, or rejected.
