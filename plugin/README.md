# software-factory (Claude Code plugin)

Turns GitHub issues labelled `ready-for-agent`, and approved specs with their ticket graph,
into reviewed PRs with green checks. Three agents (planner, builder, reviewer) do the judging;
two deterministic scripts (`factory-job`, `factory-gate`) do everything else. The full design
is in [DESIGN.md](DESIGN.md).

## Install

```sh
claude plugin marketplace add CTDes/software-factory
claude plugin install software-factory@ctdes-factory
```

Then, from the root of each repository that should use the factory:

```sh
factory-init --labels      # inside a Claude Code session: the plugin puts it on PATH
```

`factory-init` writes what is missing (`factory/config.json`, `factory/checks.sh`, the CI
workflow, `.worktreeinclude`, `CLAUDE.md`, `GLOSSARY.md`, `docs/architecture.md`), merges
`.gitignore` and `.claude/settings.json` (permissions, marketplace, plugin) and creates the
labels. Only `factory/checks.sh`, `factory/config.json` and the context files are
project-specific; everything else comes from the plugin.

## Use

- `/software-factory:factory run` drains every labelled issue and spec.
- `/software-factory:factory issue <n>`, `spec <n>`, `rework <n>`, `status`.
- Human skills: `/software-factory:to-spec`, `/software-factory:to-tickets`,
  `/software-factory:grilling`, `/software-factory:domain-modeling`, `/software-factory:retro`.

## Update

```sh
claude plugin marketplace update ctdes-factory
claude plugin update software-factory@ctdes-factory
```

The version in `.claude-plugin/plugin.json` gates updates: bump it to publish a change.

## Requirements

`git` 2.40+, `python3` 3.10+ (standard library only), `gh` authenticated with push, PR and
label rights, and the global git guardrails hook described in DESIGN.md.
