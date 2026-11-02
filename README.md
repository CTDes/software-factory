# software-factory

A software factory for [Claude Code](https://code.claude.com/docs): it turns GitHub issues, and
approved specs with their ticket graph, into reviewed pull requests with green checks.

Three agents do the judging: a **planner**, a **builder** and a **reviewer**. Two deterministic
Python scripts do everything else: `factory-job` runs the state machine and is the only thing
that touches git remotes and GitHub, and `factory-gate` runs the checks. The factory ships as the
Claude Code plugin `software-factory`, from the marketplace `ctdes-factory`, which is this repository.

## How it works

```text
issue labelled ready-for-agent
  └─ planner   issue.md → plan.md            ACCEPT · NEEDS-INFO · REJECT
      └─ builder   plan.md → commits, test-first (tdd) → build.md   READY · BLOCKED
          └─ gate      factory/checks.sh + protected paths + evidence  PASS · FAIL
              └─ reviewer  diff vs plan → review.md                PASS · CHANGES
                  └─ PR ready for a human   (or back to the builder, up to max_rounds)
```

- **Ticket level:** one issue becomes one PR.
- **Spec level:** an approved spec issue and its child tickets are built ticket by ticket on a
  `spec/<id>` integration branch. They reach `main` as a single PR after a final gate and review.
- **The human** approves specs, tests and merges the final PRs, and handles escalations
  (`ready-for-human`). Everything in between runs unattended.
- **Guardrails:**
  - Agents never push and never call `gh`.
  - Issue text is treated as data, never as instructions.
  - A branch cannot change the rules it is judged by: the gate always runs the base branch's
    `checks.sh` and fails if the branch modifies protected paths such as existing tests.
- **Resumable:** all state lives in `factory/jobs/` and on GitHub. If the session dies,
  `/software-factory:factory run` picks up where it left off.

The full specification, state machines and the log of design decisions are in
[`plugin/DESIGN.md`](plugin/DESIGN.md), which is written in Spanish.

## Quick start

Requirements: Claude Code, `git` 2.40+, `python3` 3.10+, and `gh` authenticated with push, PR and
label rights on the target repository.

```sh
claude plugin marketplace add CTDes/software-factory
claude plugin install software-factory@ctdes-factory
```

In each repository that should use the factory, inside a Claude Code session and from the repo
root:

```sh
factory-init --labels
```

Then:

1. Make `factory/checks.sh` run your lint, typecheck, tests and build, and make sure it passes on
   the base branch.
2. Fill in `CLAUDE.md`, `GLOSSARY.md` and `docs/architecture.md`, and add your existing tests to
   `protected_paths` in `factory/config.json`.
3. Commit, push, and make the `checks` workflow a required check on the base branch.
4. Label an issue `ready-for-agent` and run `/software-factory:factory issue <n>`. Once you trust
   it, use `/software-factory:factory run` to drain the whole queue.

`factory-init` is safe on existing repositories. It never overwrites files or labels, appends a
factory section to an existing `CLAUDE.md`, and warns about existing CI workflows and labels.
See [`plugin/README.md`](plugin/README.md) for the details, every command and how updates work.

## Skills for the human

| Skill | Use |
| --- | --- |
| `/software-factory:to-spec` | Turn a conversation into a spec issue |
| `/software-factory:to-tickets` | Break an approved spec into child tickets with `Parent:` / `Blocked by:` |
| `/software-factory:grilling` | Stress-test a plan or idea |
| `/software-factory:domain-modeling` | Build `GLOSSARY.md` and ADRs |
| `/software-factory:retro` | Run a retrospective on a coding session |

`tdd`, `code-review`, `grilling`, `domain-modeling`, `to-spec`, `to-tickets` and `retro` are
adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT). Each skill folder
keeps its license.

## This repository

| Path | What |
| --- | --- |
| `plugin/` | The `software-factory` plugin: agents, skills, hooks, `factory-*` executables, templates and their tests |
| `.claude-plugin/marketplace.json` | The `ctdes-factory` marketplace |
| `src/textkit/`, `tests/` | `textkit`, a small Python text-utilities library the factory is exercised on |
| `factory/` | This repo's own factory setup (`checks.sh`, `config.json`); `factory/jobs/` is gitignored |
| `docs/`, `GLOSSARY.md`, `CLAUDE.md` | Context files the agents read |

Working on this repo:

```sh
factory/checks.sh                                   # ruff, mypy --strict, unittest, wheel build (same as CI)
.venv/bin/python -m ruff format .                   # format before committing
(cd plugin && python3 -m unittest discover -s tests) # plugin tests, no network (fake GitHub)
```

### Releasing a plugin version

Bump `version` in `plugin/.claude-plugin/plugin.json` and push to `main`. Repositories prepared
with `factory-init` declare the marketplace with `autoUpdate: true` and pick up the new version
on their own. To update by hand, see [`plugin/README.md`](plugin/README.md#update).

## License

[MIT](LICENSE). The skills adapted from mattpocock/skills keep their own MIT license in each
skill folder.
