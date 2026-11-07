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
[`plugin/DESIGN.md`](plugin/DESIGN.md).

## Quick start

Requirements: Claude Code, `git` 2.40+, `python3` 3.10+, and `gh` authenticated with push, PR and
label rights on the target repository.

```sh
claude plugin marketplace add CTDes/software-factory
claude plugin install software-factory@ctdes-factory
```

Then, in each repository that should use the factory, open a Claude Code session at the repo
root and run:

```text
/software-factory:setup [path to a requirements document]
```

It checks the requirements, then takes one of two paths:

- **Existing project:** it reads the code and CI, writes a `factory/checks.sh` that runs your
  real lint, typecheck, tests and build, drafts `CLAUDE.md`, `GLOSSARY.md` and
  `docs/architecture.md`, and protects your existing tests.
- **New project:** it interviews you (starting from your requirements document, if you have one),
  writes `docs/brief.md`, the glossary, the ADRs and `docs/roadmap.md`, and builds milestone 0
  with you: the scaffold and the real checks.

Either way it shows every file before writing it, opens a setup PR with green CI, and walks you
through making `checks` a required check. You only answer questions, run the push it asks for
and merge. If you stop halfway, run it again: it continues where it left off.
`factory-init --check` shows at any time what is ready and what is missing.

Then label an issue `ready-for-agent` and run `/software-factory:factory issue <n>`. Once you
trust it, `/software-factory:factory run` drains the whole queue.

`/software-factory:setup` is safe on existing repositories: it works on a `factory-setup` branch,
and the `factory-init` script underneath never overwrites files or labels. See
[`plugin/README.md`](plugin/README.md) for the details, every command and how updates work.

## Two ways to work

### New project: roadmap → specs

For something bigger than one PR. The human's work goes into thinking up front and testing at
the end; the factory builds everything in between.

1. **Set up with `/software-factory:setup`.** In a new project it is a guided session with you:
   - **Interview:** a grilling about the whole project (vision, users, MVP scope, what is out,
     rough architecture, technical risks), starting from your requirements document if you pass
     its path. It writes `docs/brief.md`.
   - **Domain and roadmap:** `GLOSSARY.md` and ADRs for the hard-to-reverse decisions, then
     `docs/roadmap.md`: ordered milestones, each testable by a human on its own and sized for
     one spec (about 4–10 tickets). Milestone 1 is a walking skeleton, the riskiest work comes
     next. `CLAUDE.md` and `docs/architecture.md` get what was decided, since the agents start
     every job knowing only what the repo says.
   - **Milestone 0:** the stack's minimal scaffold and a `factory/checks.sh` that runs the real
     lint, typecheck, tests and build, built with you in the same session. The factory cannot do
     this one: `factory/**` and `.github/**` are protected paths, and the gate always judges
     with the base branch's `checks.sh`. Keep it honest: it is the only judge the factory has.
   - **Setup PR** with green CI, merged by you, and `checks` as a required check.
2. **For each factory milestone, in order:**
   1. `/software-factory:grilling` on the milestone (short, feature level). If the milestone is
      still foggy (unknown APIs, an unsettled data model, something that needs a prototype),
      resolve those decisions first, one session each, before writing its spec. Matt Pocock's
      [`wayfinder`](https://github.com/mattpocock/skills/tree/main/skills/engineering/wayfinder)
      skill is built for that; it is not bundled with this plugin.
   2. `/software-factory:to-spec` publishes the spec issue with the `spec` label.
   3. `/software-factory:to-tickets` publishes the child tickets with `Parent:` / `Blocked by:`.
   4. Review the graph, then add `ready-for-agent` to the spec **and** every child. That is the
      approval.
   5. `/software-factory:factory spec <n>`. Answer `needs-info` questions on the issues; fix
      `ready-for-human` escalations with a comment and `/software-factory:factory rework <n>`.
   6. Test the final `spec/<id>` PR by hand and merge it.
   7. `/software-factory:retro` to improve `CLAUDE.md`, `checks.sh` and the context files, then
      `/software-factory:to-roadmap update` to mark the milestone done and re-plan the rest.

### Existing project: issues

For bugs, small features and refactors in a codebase that already works and has real checks.

1. **Set up with `/software-factory:setup`.** It reads the code and CI, writes a
   `factory/checks.sh` that runs your real lint, typecheck, tests and build, adds your existing
   tests to `protected_paths`, drafts `CLAUDE.md`, `GLOSSARY.md` and `docs/architecture.md` so
   the agents know the conventions, and opens the setup PR. You review the drafts and merge.
2. **Write issues** as you would for a colleague: what to change and how to know it works. One
   issue is one PR. If the issue is fuzzy, `/software-factory:grilling` it first.
3. **Queue them:** add `ready-for-agent`. Start with `/software-factory:factory issue <n>` on one
   or two issues to build trust, then `/software-factory:factory run` to drain the queue.
4. **Review and merge** each PR in `ready-for-human`. Ask for changes with PR comments and
   `/software-factory:factory rework <n>`.

When a change in an existing project is too big for one PR, use a single spec for it (steps
2.1–2.6 of the new-project flow). Use a roadmap only when it needs several specs.

## Skills for the human

The factory never runs these; you do. They sit at the two ends of the work: thinking and
writing it down before the factory builds, and learning from it after. Listed in the order they
first come up:

| Skill | Use | When | Level |
| --- | --- | --- | --- |
| `/software-factory:setup` | Prepare a repository, new or existing, until the factory can take its first job | Once per repository | Repository |
| `/software-factory:grilling` | Stress-test a plan or idea | Before each spec, and before any issue that is still fuzzy | Project, feature or issue |
| `/software-factory:domain-modeling` | Build `GLOSSARY.md` and ADRs | Whenever a new term or a hard-to-reverse decision comes up, usually right after a grilling | Cross-cutting |
| `/software-factory:to-roadmap` | Turn a project-level conversation into `docs/roadmap.md`: milestones, one spec each | At the start of a new project; `to-roadmap update` after each milestone | Project |
| `/software-factory:to-spec` | Turn a conversation into a spec issue | Once per milestone, or per change too big for one PR | Feature |
| `/software-factory:to-tickets` | Break an approved spec into child tickets with `Parent:` / `Blocked by:` | Right after `to-spec` | Feature |
| `/software-factory:retro` | Run a retrospective on a coding session | After each milestone or session | The factory itself |

### In what order

`setup` comes first, once. In a new project it runs the first three steps itself: an interview
(a project-level grilling) into `docs/brief.md`, then `domain-modeling`, then `to-roadmap`, and
milestone 0 by hand.

After that, every milestone (or big change in an existing project) follows the same loop:

```text
grilling → (domain-modeling) → to-spec → to-tickets → approve (ready-for-agent on spec + children)
  → factory spec <n> → test and merge the spec PR → retro → to-roadmap update → next milestone
```

Small changes skip the spec:

```text
(grilling if fuzzy) → write the issue → ready-for-agent → factory issue <n> / factory run
  → review and merge the PR → (retro)
```

The rule behind the order: think (`grilling`), fix the words and decisions (`domain-modeling`),
write it down as work (`to-spec`, `to-tickets`), approve with labels, let the factory build, test
and merge by hand, then feed what you learned back into the context (`retro`) and re-plan
(`to-roadmap update`). Each step is detailed in [Two ways to work](#two-ways-to-work).

`tdd`, `code-review`, `grilling`, `domain-modeling`, `to-spec`, `to-tickets` and `retro` are
adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT). Each skill folder
keeps its license. `setup`, `to-roadmap` and `factory` are this repository's own.

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
