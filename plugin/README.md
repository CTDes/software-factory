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
- Human skills: `/software-factory:to-spec`, `/software-factory:to-tickets`,
  `/software-factory:grilling`, `/software-factory:domain-modeling`, `/software-factory:retro`.

## Events (optional)

The factory can send every transition to a collector such as factory-office, so one place shows
every repository on every machine. Set it once per machine, not per repository, in
`~/.claude/settings.json`:

```json
{ "env": { "FACTORY_EVENTS_URL": "http://127.0.0.1:8765/events", "FACTORY_EVENTS_TOKEN": "<token>" } }
```

Events wait in `factory/jobs/_events/outbox.jsonl` until the collector accepts them; a collector
that is down never blocks the factory. `factory-job events status` shows what is configured and
pending, and `factory-job events backfill` sends the history of the jobs a repository already has.
Details and the event format: DESIGN.md · Events.

## Update

The version in `.claude-plugin/plugin.json` gates updates: bump it to publish a change.

Repositories prepared with `factory-init` declare the `ctdes-factory` marketplace with
`autoUpdate: true`, so Claude Code picks up new versions by itself a few minutes into a session
(`Plugin updated … Run /reload-plugins to apply`). To update by hand:

```sh
claude plugin marketplace update ctdes-factory
claude plugin update software-factory@ctdes-factory                    # user-scope install
claude plugin update software-factory@ctdes-factory --scope project    # run inside each repo
```

Opening a repository whose `.claude/settings.json` enables the plugin creates a project-scope
install besides your user-scope one; each is updated separately when done by hand.

## Requirements

`git` 2.40+, `python3` 3.10+ (standard library only), `gh` authenticated with push, PR and
label rights, and the global git guardrails hook described in DESIGN.md.
