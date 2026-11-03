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
- Human skills: `/software-factory:to-roadmap`, `/software-factory:to-spec`,
  `/software-factory:to-tickets`, `/software-factory:grilling`,
  `/software-factory:domain-modeling`, `/software-factory:retro`.

Two ways to work, step by step, in the [repository README](../README.md#two-ways-to-work):

- **New project:** grilling about the whole project → `to-roadmap` (`docs/roadmap.md`, one
  milestone per spec) → for each milestone: grilling → `to-spec` → `to-tickets` → approve with the
  queue label → `factory spec <n>` → test and merge the PR → `retro` and `to-roadmap update`.
- **Existing project:** write issues, label them `ready-for-agent`, `factory issue <n>` or
  `factory run`, review and merge each PR.

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
