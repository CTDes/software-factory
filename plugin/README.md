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

Then, in a Claude Code session at the root of each repository that should use the factory:

```text
/software-factory:setup [path to a requirements document]
```

It runs `factory-init --check` (requirements and what is missing), decides with you whether the
repository is a new or an existing project, and then:

- **Existing project:** writes a real `factory/checks.sh` from the commands the project already
  uses, adapts the CI workflow, adds the existing tests to `protected_paths`, drafts the context
  files from the code and adds the toolchain permissions.
- **New project:** interviews you (from your requirements document, if any) into
  `docs/brief.md`, then glossary and ADRs (`domain-modeling`), `docs/roadmap.md` and the context
  files (`to-roadmap`), and builds milestone 0 with you.

Both end the same way: checks proven on a fresh worktree, a `factory-setup` PR with green CI that
you merge, and `checks` as a required check, which you turn on (it needs admin rights; the
skill gives you the link and the steps). It never pushes: it asks you to run `! git push …`.
It is resumable: rerun it and it skips what is already done.

### factory-init

The script underneath, on PATH inside a Claude Code session. You rarely need it by hand.

- `factory-init --check` writes nothing and prints one line per requirement (`ok`, `fail`,
  `warn`) and per setup step (`ok`, `todo`): git 2.40+, python 3.10+, `gh` authenticated with
  write access to the repository, the global git guardrails hook, the factory files, the
  labels, a real `checks.sh` locally and on the base branch, and `checks` as a required check
  (branch protection or ruleset). It exits 1 only on a `fail`.
- `factory-init [--labels]` writes what is missing (`factory/config.json`, `factory/checks.sh`,
  the CI workflow, `.worktreeinclude`, `CLAUDE.md`, `GLOSSARY.md`, `docs/architecture.md`),
  merges `.gitignore` and `.claude/settings.json` (permissions, marketplace) and, with
  `--labels`, creates the labels. Only `factory/checks.sh`, `factory/config.json` and the
  context files are project-specific; everything else comes from the plugin.

In an existing repository it never overwrites anything (unless `--force`, which does not apply
to labels):

- An existing `CLAUDE.md` gets a `## Software factory` section appended, unless it already
  mentions `factory/checks.sh`.
- Other workflows in `.github/workflows/` produce a warning: the required check must run
  `factory/checks.sh`, so make one of them call it or drop their duplicated steps.
- `--labels` only creates the missing labels and leaves existing ones untouched. If the
  `queue` or `spec` label already exists with open issues, it warns: the factory would pick
  them up. Rename the label in `factory/config.json` and rerun `factory-init --labels`.

## Use

- `/software-factory:factory run` drains every labelled issue and spec.
- `/software-factory:factory issue <n>`, `spec <n>`, `rework <n>`, `status`.
- Human skills: `/software-factory:setup`, `/software-factory:to-roadmap`,
  `/software-factory:to-spec`, `/software-factory:to-tickets`, `/software-factory:grilling`,
  `/software-factory:domain-modeling`, `/software-factory:retro`.

Two ways to work, step by step, in the [repository README](../README.md#two-ways-to-work):

- **New project:** `setup` (interview → `docs/brief.md` → glossary and ADRs → `docs/roadmap.md`
  → milestone 0 → setup PR) → for each milestone: grilling → `to-spec` → `to-tickets` → approve
  with the queue label → `factory spec <n>` → test and merge the PR → `retro` and
  `to-roadmap update`.
- **Existing project:** `setup`, then write issues, label them `ready-for-agent`,
  `factory issue <n>` or `factory run`, review and merge each PR.

## Office (optional)

[factory-office](https://github.com/CTDes/factory-office) shows every linked repository, on every
machine, as a pixel-art office. Run it (`docker compose up -d` in its repository), show its token
with `docker compose exec office factory-office token`, and in each repository you want to see:

```sh
factory-job office link <office-token>                         # office on this machine
factory-job office link <office-token> --url http://nas:8765   # office elsewhere
```

The link lives in `factory/jobs/_events/link.json` (gitignored). Events wait in an outbox until
the office accepts them; an office that is down never blocks the factory. `factory-job office
status` shows where events go and whether the office answers; `office unlink` stops sending. For
CI, set `FACTORY_EVENTS_URL` and `FACTORY_EVENTS_TOKEN` instead. Details: DESIGN.md · Events.

## Update

The version in `.claude-plugin/plugin.json` gates updates: bump it to publish a change.

The plugin is installed once per user and machine (`claude plugin install`, above), not per
repository: `factory-init` declares the marketplace in each repository's settings but does not
enable the plugin there. Enabling it in a project's `.claude/settings.json` would create a
separate project-scope install for that repository, one more copy that falls behind.

The marketplace is declared with `autoUpdate: true`, so Claude Code picks up new versions by
itself a few minutes into a session (`Plugin updated … Run /reload-plugins to apply`).
`claude plugin list` shows the installed version. To update by hand:

```sh
claude plugin marketplace update ctdes-factory
claude plugin update software-factory@ctdes-factory
```

On a new machine, or for someone else working on the repository, run the two install commands
once. Repositories prepared before 0.5.2 enabled the plugin per project: remove
`enabledPlugins` from their `.claude/settings.json` and run
`claude plugin uninstall software-factory@ctdes-factory --scope project` inside each.

## Requirements

`git` 2.40+, `python3` 3.10+ (standard library only), `gh` authenticated with push, PR and
label rights, and the global git guardrails hook described in DESIGN.md.
