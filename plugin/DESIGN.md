# Software factory · Design

This is the reference design of the `software-factory` Claude Code plugin as it is implemented
today. The factory turns GitHub issues, and approved specs with their ticket graph, into merged
code through three agents and two deterministic scripts.

It started as a brief written in Spanish for Claude Code to build, in six phases. The brief is
archived unchanged in [`docs/original-brief.es.md`](docs/original-brief.es.md). What changed
along the way is recorded in [History](#history).

## Goals and principles

The factory works at two levels:

- **Ticket level:** a labelled issue becomes a reviewed PR with green checks.
- **Spec level:** an approved spec and its ticket graph are built, ticket by ticket, on an
  integration branch. They reach the base branch as a single PR that a human tests. This is the
  main use case: new and relatively large pieces of work.

The human steps in at three points: approving the spec and its graph before building, testing
and merging the final PR, and handling escalations. Everything in between runs unattended.

Non-negotiable principles:

1. **Scripts decide what is deterministic; agents judge.** `factory-job` and `factory-gate` run
   the checks, move state, create branches, push, merge, label and comment. Agents decide what to
   build, write code and judge its quality.
2. **Context travels in files.** Each agent starts without the orchestrator's history. It reads
   files from the job and the repo, writes exactly one output file (plus commits, for the
   builder) and returns a single line.
3. **No agent touches GitHub or the remote.** No `gh`, no `git push`, no merges into shared
   branches. Only `factory-job` has those effects. Hooks enforce this even if an agent tries.
4. **External text is data, never instructions.** Issue content reaches the agents quoted inside
   `issue.md`. The first agent to read it, the planner, has no shell.
5. **A branch cannot change the criteria it is judged by.** The gate runs `checks.sh` from the
   base branch on the remote and fails if the diff modifies or deletes protected paths.
6. **The orchestrator is dumb.** It does not interpret verdicts. It asks `factory-job` what to
   do next, launches the matching agent or script, and hands control back. All transition logic
   lives in Python, with tests.
7. **Resumable.** If the session dies, `/software-factory:factory run` rebuilds everything from
   `factory/jobs/` and GitHub, with no state in memory.

## Layout

Machine requirements: a recent Claude Code, `git` 2.40+, `python3` 3.10+ with no extra packages,
and `gh` authenticated as a user who can push, open PRs and manage labels in the repository.

Everything generic ships in the plugin `software-factory`, installed from the marketplace
`ctdes-factory` (the repository `CTDes/software-factory`). Each project only holds
`factory/checks.sh`, `factory/config.json`, its context files and `.claude/settings.json`, all
created by `/software-factory:setup` (through `factory-init`).

```text
plugin software-factory/                (installed under ~/.claude/plugins/cache/…)
  .claude-plugin/plugin.json             name and version (the version gates updates)
  DESIGN.md                              this document
  docs/original-brief.es.md              the original brief, in Spanish (archive)
  agents/planner.md, builder.md, reviewer.md   →  software-factory:planner, :builder, :reviewer
  skills/factory/SKILL.md                orchestrator /software-factory:factory
  skills/tdd, code-review, grilling, domain-modeling, to-spec, to-tickets, retro   (Matt Pocock, MIT)
  skills/to-roadmap                      project → docs/roadmap.md (milestones, one spec each)
  skills/setup                           /software-factory:setup: prepares a repository, new or existing
  hooks/hooks.json, agent_guard.py       agent guardrails (PreToolUse, by agent_type)
  bin/factory-job                        state machine; the only thing with effects on the remote and GitHub
  bin/factory-gate                       runs checks.sh, checks protected paths and evidence
  bin/factory-init                       writes the factory files; --check reports what is missing
  lib/                                   shared Python modules
  tests/                                 unittest, no network, fake GitHub
  templates/                             what factory-init writes

<repo>/
  CLAUDE.md                              repo context: setup, how to validate, conventions
  GLOSSARY.md                            domain vocabulary
  docs/adr/NNNN-*.md                     architecture decisions
  docs/architecture.md                   module map, interfaces, allowed dependencies, folder ownership
  docs/history/<job-id>.md               each job's record, committed by factory-job (see Job history)
  .worktreeinclude                       untracked files every worktree needs (.env…)
  .gitignore                             adds factory/jobs/ and .claude/worktrees/
  .github/workflows/checks.yml           runs factory/checks.sh; required check on the base branch
  .claude/settings.json                  pre-approved permissions, marketplace (plugin installed per user)
  factory/
    checks.sh                            PROJECT-SPECIFIC · lint, typecheck, tests, build
    config.json                          PROJECT-SPECIFIC · see config.json
    jobs/<job-id>/                       state of each job (gitignored)
    jobs/_events/                        office link and event outbox (see Events)

~/.claude/settings.json                  global git guardrails hook (outside the repo)
```

Worktrees live in `.claude/worktrees/<job-id>/`, one per job, on the branch `factory/<job-id>`.

## config.json

One file per repository with everything that can be tuned without touching code. `factory-job`
validates it on start and refuses to work if a key is missing or has the wrong type.

```json
{
  "base_branch": "main",
  "merge_method": "merge",
  "concurrency": 1,
  "max_rounds": 3,
  "spec_branch_prefix": "spec/",
  "job_branch_prefix": "factory/",
  "worktrees_dir": ".claude/worktrees",
  "labels": {
    "queue": "ready-for-agent",
    "spec": "spec",
    "needs_info": "needs-info",
    "needs_human": "ready-for-human",
    "in_progress": "factory:working"
  },
  "models": {
    "planner": "opus",
    "builder":  { "low": "sonnet", "medium": "sonnet", "high": "opus" },
    "reviewer": { "low": "haiku",  "medium": "sonnet", "high": "sonnet" },
    "final_reviewer": "opus"
  },
  "always_human_surfaces": [],
  "protected_paths": ["factory/**", ".github/**", ".claude/**"],
  "checks_timeout_s": 900,
  "log_tail_lines": 80,
  "history_dir": "docs/history"
}
```

| Key | Meaning |
| --- | --- |
| `merge_method` | `merge`, `squash` or `rebase`; must be allowed in the repository |
| `concurrency` | Actions running at once. Start at 1; raise to 3 or 4 at spec level once the factory is reliable |
| `max_rounds` | Trips back to the builder (red gate, review with changes, failed merge) before escalating to a human |
| `labels.queue` | The label that lets an issue into the factory. It is the trust boundary: only people with triage rights can add it |
| `labels.in_progress` | Set by `factory-job` while a job is alive, so GitHub shows what the factory has picked up |
| `models` | Model per agent and, for builder and reviewer, per risk |
| `always_human_surfaces` | Surfaces that never merge into the spec branch on their own, even when everything passes (e.g. `payments`) |
| `protected_paths` | Globs. The gate fails if the diff modifies or deletes a matching file. Adding new matching files is allowed. Projects add their existing tests here |
| `history_dir` | Optional (default `docs/history`): where `factory-job` commits each job's record (see Job history). `""` turns it off. Must be a path inside the repository |

## Jobs

There are two kinds of job. A **ticket** is an issue built in its own worktree. A **spec** is a
parent issue that groups tickets and owns an integration branch. The id is `NNN-slug`: the issue
number with three digits and the title in kebab-case, cut to 40 characters.

```text
factory/jobs/012-reading-time/
  job.json             state; only factory-job writes it
  issue.md             the issue and its comments, quoted as data
  plan.md              planner
  build.md             builder (current round; earlier ones are archived in their round folder)
  round-1/checks.md    factory-gate
  round-1/review.md    reviewer
  round-1/merge.md     factory-job merge, when integrating the base failed
  round-1/build.md     the builder's build.md for that round, archived
  round-2/…
  rework-1.md          human comments pulled from the PR or issue
  events.log           one line per transition: time, from, to, reason
```

### job.json

```json
{
  "id": "014-text-stats",
  "kind": "ticket",
  "issue": 14,
  "title": "Text metrics in a dict (text_stats)",
  "spec": "010-text-statistics",
  "blocked_by": [11, 12],
  "stage": "build",
  "round": 1,
  "risk": "medium",
  "surfaces": ["api", "docs"],
  "models": { "builder": "sonnet", "reviewer": "sonnet" },
  "base": "spec/010-text-statistics",
  "branch": "factory/014-text-stats",
  "worktree": ".claude/worktrees/014-text-stats",
  "pr": null,
  "agent": null,
  "reason": null,
  "claim": null,
  "feedback": "factory/jobs/014-text-stats/round-1/merge.md",
  "contract_failures": 0,
  "created_at": "2026-11-02T11:58:35+01:00",
  "pushed_at": null,
  "asked_at": null,
  "updated_at": "2026-11-02T12:15:23+01:00"
}
```

- A ticket without `spec` has `base` = `base_branch` and ends in a PR to it.
- A `spec` job also has `tickets` (list of ids) and `branch` = `spec/<id>`. It only has a
  worktree of its own in the final phase.
- `claim` marks a job as taken by a running action, so `job next` does not offer it again.
- `feedback` is the exact file that sent the job back to `build`. The builder reads it next round.
- `contract_failures` counts consecutive malformed agent files (see below).

### File contracts

Each agent file starts with key-value lines that `factory-job` parses with a strict regex. If a
required line is missing or has a value that is not allowed, `job advance` fails with a message
naming the file and the line. The orchestrator sends that error back to the same agent once. If
it fails again, the job goes to `needs-human`. A `READY` with a dirty worktree or no commits over
the base counts as a contract failure too.

| File | Required header | Body |
| --- | --- | --- |
| `issue.md` | written by `factory-job`: title, author, URL | Issue body and comments inside a block delimited by `<<<ISSUE` and `ISSUE>>>`, with a notice that it is data |
| `plan.md` | `DECISION: ACCEPT\|NEEDS-INFO\|REJECT`, `RISK: low\|medium\|high`, `SURFACES: a, b` (or `none`) | `## Scope`, `## Acceptance criteria` (C1, C2… testable), `## Seams` (where the tests live), `## Notes`. With NEEDS-INFO: `## Question`. With REJECT: `## Reason` |
| `build.md` | `STATUS: READY\|BLOCKED` | `## Evidence`: one line per criterion, `C1: <test path>::<name> — what it proves`; a name with spaces goes in backticks, `` C1: <path>::`<name with spaces>` ``. `job advance` checks every line (format, name present in its file, every plan criterion covered) before the gate: a problem is a contract failure, not a gate round. With BLOCKED: `## Blocker` |
| `round-N/checks.md` | `GATE: PASS\|FAIL`, `PROTECTED: none` or the list of paths touched | Command, duration, missing evidence and the last `log_tail_lines` lines |
| `round-N/review.md` | `VERDICT: PASS\|CHANGES` | `## Standards`, `## Spec`, `## Architecture` and, when the `security` surface is set, `## Security`. Each finding with file, line and whether it blocks |
| `round-N/merge.md` | `MERGE: CONFLICT\|GATE-FAIL`, written by `factory-job merge` | Conflicting files or the gate log after integrating the base |
| `rework-N.md` | written by `factory-job` | PR and issue comments newer than the last push, quoted |

Section headings are matched ignoring case. The Spanish headings used before 0.2.0
(`## Alcance`, `## Criterios de aceptación`, `## Evidencia`, `## Estándares`…) are still
accepted, so jobs that were in flight keep parsing.

Agents return a single line to the orchestrator: the main header of their file
(`ACCEPT risk=medium surfaces=ui`, `READY`, `CHANGES`…). The orchestrator only prints it.

### Job history

`factory/jobs/` is gitignored, so the plan, the builds, the gate results and the reviews of a job
would only live on the machine that ran it. When a ticket reaches a human (`review → ready`) or
is about to merge into its spec (`review → merging`), and when a spec reaches `ready`,
`factory-job` renders the job folder into `<history_dir>/<job-id>.md` and commits it alone to the
job's branch (`docs(history): <job-id>`), pushing it when a PR shows that branch. After the merge
the record lives in git next to the code it explains: a wiki or any other view can be rebuilt
from the repository alone.

The file (`lib/history.py`) has a JSON-valued front matter (job, kind, issue, title, spec, pr,
stage, risk, surfaces, rounds, created, updated) and then: the issue, the plan (and earlier
NEEDS-INFO questions), one section per round (build, gate header and summary, review, merge),
human feedback (`rework-N.md`) and a timeline from `events.log` that includes the transition
being applied. A spec's file also links its tickets' files. Issue and comment text goes inside
code fences longer than any backtick run in it, so external text renders as text. A later trip
back to `build` regenerates the file at the next `ready`. `pushed_at` does not move: `job rework`
still sees comments made since the builder's last push. The reviewer ignores `docs/history/`
and the builder never edits it.

`factory-job history [<id|issue>…]` writes the same file into the main checkout, uncommitted,
for jobs that finished before this existed (by default every job with a PR).

### Wiki

`factory-job vault <out> [--title T]` builds the project wiki: a folder of linked markdown notes
that is at once an Obsidian vault and the `content/` folder of a Quartz site. It is a projection,
rebuilt from scratch every time from the repository and a snapshot of GitHub (every issue and
PR, open or closed); it refuses to write into a non-empty folder it did not make (`.factory-vault`
marker).

| Note | Built from |
| --- | --- |
| `index.md` | Milestones from `docs/roadmap.md` (`### M<n> · <title> — status: …`, with `spec #n` and `PR #m`), what is working or waiting for a human, the documents, the latest job records |
| `board.md` | Every spec and ticket grouped by status: working, needs human, needs info, queued (from the labels in `config.json`), open, done (closed with a merged PR or a job record), closed |
| `specs/<n>.md` | An issue with the `spec` label: status, milestone, its tickets (`Parent: #n`) with status, PR and record, a mermaid graph of their `Blocked by:` lines, the description |
| `tickets/<n>.md` | Any other issue: status, spec, blockers, PR (from its record, else a PR that says `Closes #n`; tickets of a spec show "via spec"), record, description |
| `history/<job-id>.md` | `<history_dir>/*.md`, with a link back to the issue's note |
| `docs/**`, `GLOSSARY.md`, `README.md` | Copied with the same paths, so links between them keep working |

Links are relative markdown links (Quartz, Obsidian and GitHub all follow them); `#n` outside
code becomes a link to that issue's note. Issue text and job records may carry HTML from outside:
every `<` outside code is escaped, and link targets with a `javascript:`, `vbscript:` or `data:`
scheme are defused. The generator only reads.

### Wiki publishing

The factory-office builds the site (Quartz) and serves it behind its token; the factory only
sends the vault, wherever its events go (`link.json` or `FACTORY_EVENTS_URL`), so a laptop and a
CI job publish the same way and the office never needs GitHub credentials (`lib/wiki.py`).

- Contract: `POST <office>/wiki?repo=<owner/name>`, `Content-Type: application/gzip`, body a
  tar.gz of the vault (regular files only, relative paths, mode 644), `Authorization: Bearer
  <office token>`. Any 2xx means accepted; the office replaces that repository's wiki.
- Every transition writes `factory/jobs/_events/wiki-dirty` (`urgent` for `ready`, `done`,
  `needs-human`, `needs-info`, `rejected`; else `normal`, never downgrading an urgent mark).
- At the end of every factory-job command, after the event flush, a dirty wiki is rebuilt
  (two `gh` list calls) and sent: urgent at once, normal at most every 120 s. A failure keeps the
  mark and pauses automatic publishing for 60 s. It never changes a command's outcome.
- `factory-job office wiki` publishes now; `office link` publishes once after linking;
  `office status` shows when it was last published.

## State machines

`factory-job` is the only implementation of these tables (`lib/machine.py`, `lib/spec.py`). Any
transition not listed is rejected. Each transition appends a line to `events.log` and updates
`updated_at`. GitHub and git effects run after the condition is checked and before the new
`stage` is written. If an effect fails, the job keeps its stage and the full error is shown.

### Ticket

States: `intake`, `needs-info`, `rejected`, `build`, `gate`, `review`, `merging`, `ready`,
`needs-human`, `done`. Terminal: `rejected`, `done`.

| From | To | Condition | Effects |
| --- | --- | --- | --- |
| `intake` | `build` | `plan.md` with `DECISION: ACCEPT` | Stores risk, surfaces and models. Adds `in_progress`. Comments the scope and criteria on the issue |
| `intake` | `needs-info` | `NEEDS-INFO` | Comments the question on the issue. Adds `needs_info` |
| `intake` | `rejected` | `REJECT` | Comments the reason. Removes `queue`. Deletes the worktree and branch |
| `intake` | `needs-human` | The planner broke the `plan.md` contract twice | Comments. Adds `needs_human` |
| `needs-info` | `intake` | A new comment from someone other than the factory, after the question | Regenerates `issue.md`. Removes `needs_info` |
| `build` | `gate` | `build.md` with `READY`, clean tree and at least one commit over the base | `round += 1`, creates `round-N/`. Pushes the branch with `--force-with-lease`. Standalone ticket: opens a draft PR "Closes #n" the first time |
| `build` | `needs-human` | `BLOCKED`, or the contract broken twice | Comments the blocker on the issue (and the PR if any). Adds `needs_human` |
| `gate` | `review` | `round-N/checks.md` with `GATE: PASS` | None |
| `gate` | `build` | `GATE: FAIL` and `round < max_rounds` | Archives `build.md`, sets `feedback` |
| `gate` | `needs-human` | `GATE: FAIL` and `round = max_rounds` | Comments. Adds `needs_human` |
| `review` | `build` | `VERDICT: CHANGES` and `round < max_rounds` | Archives `build.md`, sets `feedback` |
| `review` | `needs-human` | `CHANGES` and `round = max_rounds`, or the contract broken twice | Comments. Adds `needs_human` |
| `review` | `merging` | `PASS`, ticket of a spec, no surface in `always_human_surfaces` | Commits the job history (not pushed; `job merge` pushes it into the spec branch) |
| `review` | `ready` | `PASS` and standalone ticket, or a surface in `always_human_surfaces` | Commits and pushes the job history. Standalone: PR leaves draft. In a spec: opens a PR against the spec branch. Adds `needs_human`, comments a summary |
| `merging` | `done` | `job merge` succeeds | Fast-forward push of the ticket branch into the spec branch. Comments and closes the issue. Deletes worktree, local and remote branch. Removes labels |
| `merging` | `build` | Conflict integrating the base, or red gate after integrating it, and rounds left | Writes `round-N/merge.md`, sets `feedback`. `round` is not incremented here: `build → gate` does it |
| `merging` | `needs-human` | Same, with no rounds left | Comments. Adds `needs_human` |
| `ready`, `needs-human` | `build` | `job rework` | Pulls PR and issue comments into `rework-N.md`, sets `feedback`. Removes `needs_human` |
| `needs-human` | `intake` | `job rework` of a job escalated before it had a valid plan | Same as above, back to the planner |
| `ready`, `needs-human` | `done` | The job's PR is merged | Deletes worktree, local and remote branch. Removes labels |

If a merge push is rejected because the spec branch moved meanwhile, the job stays in `merging`
with its claim released, and the next `job next` retries the merge.

The builder is resumed on every trip back to `build`. It reads the file in `feedback`
(`rework-N.md`, `round-N/merge.md`, `round-N/checks.md` or `round-N/review.md`). The previous
`build.md` has been archived to its round folder.

### Spec

States: `building`, `final-review`, `final-build`, `ready`, `needs-human`, `done`.

| From | To | Condition | Effects |
| --- | --- | --- | --- |
| (new) | `building` | `job spec create <n>`: the issue has `spec` and `queue`, its children form a valid graph | Creates `spec/<id>` from `origin/<base_branch>` and pushes it. Creates a ticket job in `intake` per child. Comments the graph on the spec issue |
| `building` | `final-review` | Every ticket is `done` | Creates the spec branch worktree. `round = 1` |
| `final-review` | `ready` | Final gate PASS and final review PASS | Commits and pushes the spec's history. Opens PR `spec/<id>` → base "Closes #n", not draft. Adds `needs_human`. Comments a summary: tickets, rounds, escalations |
| `final-review` | `final-build` | Final gate or final review with changes and `round < max_rounds` | Archives `build.md`, sets `feedback` |
| `final-build` | `final-review` | `build.md` with `READY` | Pushes the spec branch. `round += 1` |
| `final-review`, `final-build` | `needs-human` | Rounds exhausted or `BLOCKED` | Comments. Adds `needs_human` |
| `ready`, `needs-human` | `final-build` | `job rework` | Same as for tickets |
| `ready` | `done` | PR merged | Deletes the worktree and the remote spec branch |

`final-review` runs in two steps: the `final-gate` action (`factory-gate <id> --final`), then
`job advance`, which answers `final review pending` without a transition; then the `final-review`
action (the reviewer agent with `final_reviewer` as model), then `job advance` again.

Graph rules:
- A spec's children are the open issues with a line `Parent: #<spec>`. Their blockers come from a
  line `Blocked by: #a, #b`.
- `job spec create` fails on cycles, on a blocker outside the spec, or on a child without the
  `queue` label.
- A ticket in `needs-human` does not stop the spec: it only holds back the tickets that depend on it.
- A child added while the spec is `building` joins on the next `job queue`.
- Merges into the same base branch run one at a time.

## factory-job and factory-gate

Two Python 3.10+ executables with no external dependencies. The logic is in `lib/`, the tests in
`tests/`. All GitHub access goes through an adapter (`lib/github.py`) that calls `gh`; with
`FACTORY_GH=fake` and `FACTORY_GH_DIR=<dir>` it reads and writes JSON fixtures instead, so tests
run without network. All git access goes through `lib/git.py`. Exit codes: 0 success, 1
condition not met or illegal transition, 2 usage or configuration error.

### factory-job

| Command | What it does |
| --- | --- |
| `queue` | Syncs with GitHub. Creates jobs for new issues with `queue`: `spec` ones as specs, ones with `Parent:` as children of their spec, the rest as standalone tickets. Detects answers to `needs-info`, merged PRs and new children. Prints a summary |
| `create <issue>` | Creates a ticket job in `intake` and writes `issue.md`. The issue must carry `queue` |
| `spec create <issue>` | Creates the spec job, validates the graph and creates its children's jobs |
| `next [--json] [--only <id\|issue>]` | Lists the actions that can run now, respecting `concurrency`, blockers, claims and one merge per base. Each action carries the job, kind (`plan`, `build`, `gate`, `review`, `merge`, `final-gate`, `final-review`, `final-build`), agent or command, model, name and the exact prompt. `--only` limits it to one job (a spec includes its tickets) |
| `start <id>` | Claims the job. For a ticket's `plan` action it also fetches and creates the worktree from `origin/<base>` on `factory/<id>`, copying `.worktreeinclude`, so the planner reads the base as it is when the ticket unblocks |
| `advance <id>` | Reads the job's files, picks the transition from the tables, runs its effects, writes the new state and releases the claim. Prints `<id> <from> -> <to>` |
| `merge <id>` | For tickets in `merging`: fetch, integrate `origin/<base>` into the ticket branch inside its worktree, run the gate, and if everything passes fast-forward the spec branch and advance to `done`. Otherwise advance to `build` with `merge.md` |
| `rework <id\|issue>` | Pulls human comments newer than the last push into `rework-N.md` and advances to `build`, `intake` or `final-build` |
| `recover` | Releases claims left by a dead session and checks that every worktree exists and is on the branch in `job.json`. The orchestrator runs it first |
| `status [<id>]` | Readable state of one or all jobs |
| `summary` | Table: job, kind, stage, round, risk, PR, reason |
| `vault <out> [--title T]` | Builds the project wiki in `<out>` (see Wiki) |
| `history [<id\|issue>…]` | Writes `<history_dir>/<job-id>.md` into the main checkout, uncommitted (backfill; default: every job with a PR) |
| `office link <token> [--url URL]` | Link this repository to a factory-office (see Events): check the office accepts the token, save the link, send the history |
| `office wiki` | Build the wiki and send it to the office now (see Wiki publishing) |
| `office status\|unlink\|flush\|backfill` | Show where events go and whether the office answers; forget the link; send the outbox now; send every job's `events.log` again |

`job next` is what keeps the orchestrator dumb. It builds each agent's prompt from a template in
`lib/prompts.py`, with absolute paths to the job folder and worktree, the base and the round. The
orchestrator only copies it.

Every comment `factory-job` posts on GitHub starts with `[factory]` and the job id. The factory
comments with the human's account, so this prefix is how it tells its own comments apart.

### Events

An optional emitter sends every transition to a factory-office, a separate service that shows
every linked repository on every machine. The factory never depends on it: an unlinked
repository behaves as before, and an office that is down never blocks or fails a command.

Linking is per repository and needs only the office's single token:

```sh
factory-job office link <office-token>                         # office on this machine
factory-job office link <office-token> --url http://nas:8765   # office elsewhere
```

`link` posts an empty batch to check that the office answers and accepts the token, saves
`factory/jobs/_events/link.json` (mode 600, gitignored with `factory/jobs/`, so the token never
reaches git) and sends the repository's history. `unlink` deletes it and drops pending events.

For CI or a whole machine, environment variables take precedence over the link:

| Variable | Meaning |
| --- | --- |
| `FACTORY_EVENTS_URL` | The office's events endpoint |
| `FACTORY_EVENTS_TOKEN` | The office token, sent as `Authorization: Bearer <token>` |
| `FACTORY_EVENTS_MACHINE` | Machine name in the events. Default: the hostname |

- `Job.log_event` is the single point every transition goes through. Besides the `events.log`
  line it appends the event to `factory/jobs/_events/outbox.jsonl`.
- At the end of every `factory-job` command the outbox is flushed: `POST` of
  `{"events": [...]}` in batches of 200, oldest first, 3 s timeout. Accepted events leave the
  outbox; the rest wait for the next command. After a failure, automatic flushes pause for 60 s,
  so an office that is down costs at most one timeout per minute. `office flush` always tries.
- One process flushes at a time (`flush.lock`); appends and rewrites take `outbox.lock`.
- `office backfill` queues every line of every job's `events.log`. Ids are deterministic, so the
  office drops copies of events it already has.
- The office must answer 2xx only once the batch is stored, and treat `id` as idempotent.

Event, schema 1:

```json
{
  "schema": 1,
  "id": "sha256(repo, job_id, ts, from, to, reason)[:32]",
  "repo": "CTDes/factory-sandbox",
  "machine": "xals-mbp",
  "job_id": "003-population-variance-of-a-sequence-varian",
  "kind": "ticket",
  "issue": 3,
  "spec": null,
  "ts": "2026-11-02T12:15:23+01:00",
  "from": "review",
  "to": "ready",
  "reason": "PASS",
  "job": { "...": "job.json right after the transition, updated_at = ts" }
}
```

- `repo` is `owner/name` from `origin`, or the folder name without a remote.
- `ts`, `from`, `to` and `reason` are exactly the `events.log` line.
- `from` equal to `to` marks a note inside a stage (contract failure, released claim…).
  `job start` logs `start <action>` with the claim in the snapshot, so a viewer can tell an
  agent at work from a job waiting in its stage.
- `job` is null on backfilled events except the last one of each job, which carries the current
  `job.json`. A collector keeps, per `repo` + `job_id`, the snapshot with the latest `ts`.
- Consumers ignore unknown fields and unknown stages; a new required field means `schema: 2`.

### factory-gate

`factory-gate <id> [--final]` does, in order:

1. Takes `factory/checks.sh` from `origin/<base_branch>`, never from the job's branch, and runs
   it with the worktree as working directory and `checks_timeout_s` as limit.
2. Diffs against the merge-base with the job's base (`--final`: with `base_branch`). Any
   modified, deleted or renamed-away file matching `protected_paths` is a failure. New files are
   allowed.
3. Checks the evidence in `build.md`. Every `path::name` must be a file inside the worktree that
   contains that name, and every criterion `Cn` in the plan must have evidence. The builder saying
   a criterion is met is not enough.
4. Writes `round-N/checks.md` with the verdict, protected paths touched, missing evidence, command,
   duration and log tail. Exits 0 on PASS and 1 on FAIL.

### checks.sh contract

It belongs to the project, not the factory. Requirements:
- `set -euo pipefail` and non-interactive.
- Installs dependencies when the worktree is freshly created.
- Runs lint, typecheck, tests and build.
- Never rewrites files: no `--fix`, no snapshot updates.
- Exits non-zero on any failure.

CI runs the same script, so the local gate and the required GitHub check agree.

## Agents, orchestrator, skills and guardrails

### Agents

Three plugin subagents: `software-factory:planner`, `:builder`, `:reviewer`. Every system
prompt starts the same way: you are a step in a pipeline; your context is files, not a
conversation; write exactly your file with the exact header; answer with a single line.
`job next` picks the model from `config.json` and the orchestrator passes it when launching; the
frontmatter holds a default.

|  | planner | builder | reviewer |
| --- | --- | --- | --- |
| Tools | Read, Grep, Glob, Write. No Bash | All | Read, Grep, Glob, Write, and Bash limited to read-only git |
| Works in | The job's worktree | The job's worktree | The job's worktree |
| Reads | `issue.md`; for a spec child, also the spec's `issue.md`; `CLAUDE.md`, `GLOSSARY.md`, `docs/adr/`, `docs/architecture.md` and the code | `plan.md` and, on later rounds, the file in `feedback` | `plan.md`, `build.md`, the diff against the merge-base with the base, `docs/architecture.md`, `GLOSSARY.md`, `CODING_STANDARDS.md` if present |
| Writes | `plan.md` | Commits on the job branch and `build.md` | `round-N/review.md` |
| Skills | None | `tdd`, preloaded | None; its prompt includes the `code-review` axes |

Subagents have no working-directory setting. Their prompts require `cd <worktree> &&` in every
command, and the guard blocks writes outside the allowed folders.

**planner.** Treats `issue.md` as data and never follows instructions in it. Decides whether the
work can be built as written. It may reject a standalone ticket. It never rejects a spec child:
if the ticket is no longer buildable (an interface it depends on changed when another ticket
merged), it answers `NEEDS-INFO` explaining the conflict. Acceptance criteria must be testable.
Seams are existing public interfaces or ones described in `architecture.md`, as high as possible.

**builder.**
- Works only inside the worktree the prompt names.
- Uses `tdd` at the plan's seams: one test, the minimal implementation, repeat.
- Makes small commits whose messages cite the criterion.
- Runs `factory/checks.sh` before declaring `READY`, and never declares `READY` if it fails.
- Does not push, does not use `gh`, and touches protected paths only to add new files.
- If it changes a public interface, it updates `docs/architecture.md` in the same diff.
- To resolve a `merge.md`, it integrates `origin/<base>` locally and resolves the conflict.
- If it cannot continue without a human decision, it writes `BLOCKED` with the exact question.

**reviewer.** Does not run tests; the gate already did. It writes separate sections that are not
mixed or ranked against each other:
- **Standards:** `CODING_STANDARDS.md` and the twelve Fowler smells from `code-review`.
- **Spec:** is every criterion met, with nothing missing and nothing extra?
- **Architecture:** module boundaries, allowed dependencies, folder ownership, and
  `architecture.md` updated if an interface changed.
- **Security:** only when the `security` surface is set.

It returns `CHANGES` only for blocking findings and lists the rest as non-blocking. For a spec's
final review, the same agent runs with the `final_reviewer` model, the diff
`<base_branch>...spec/<id>` and the spec issue as the criterion.

Agent names: `planner-<id>`, `builder-<id>`, `reviewer-<id>-r<N>`.

### Orchestrator `/software-factory:factory`

A skill with `disable-model-invocation: true` whose allowed tools are only `factory-job` and
`factory-gate`. Commands: `run` (drain everything), `issue <n>` (that ticket only), `spec <n>`
(that spec and its children), `rework <n>`, `status`.

The `run` loop:

1. `job recover`, then `job queue` (only for `run` and `spec`).
2. `job next --json`. If there are no actions and nothing running, print `job summary` and stop.
3. For each action: `job start <id>`. Launch agent actions as background subagents with the
   given agent, model and prompt, copied verbatim. Run script actions (`gate`, `merge`,
   `final-gate`) with Bash in the background.
4. When something finishes, run `job advance <id>` and print the transition line. `merge`
   already transitions by itself. If `advance` reports a contract error, send it to the same
   agent once with SendMessage.
5. Back to step 2.

A builder still alive in the session is resumed by its id with SendMessage on its next round;
otherwise a new one is launched, and it finds everything it needs in the files. The orchestrator
never runs `git` or `gh`, never reads project code and never decides a transition. If something
does not fit, it stops launching, waits for what is running, and reports.

### Skills from Matt Pocock

Copied from [mattpocock/skills](https://github.com/mattpocock/skills) with their `LICENSE` and an
attribution line: `tdd`, `code-review`, `grilling`, `domain-modeling`, `to-spec`, `to-tickets`,
`retro`. Adapted only where needed:

- Where they read labels or tracker settings from `docs/agents/`, they read `factory/config.json`
  and assume GitHub.
- `to-spec` publishes the spec with the `spec` label and without `queue`. The human adds `queue`
  to approve it.
- `to-tickets` writes in each child the `Parent: #<spec>` and `Blocked by: #a, #b` lines that
  `factory-job` parses, without labelling them.
- `to-spec` reads `docs/roadmap.md`, when it exists, to keep a spec within its milestone.

`to-roadmap` is the factory's own: it turns a project-level conversation into
`docs/roadmap.md`, ordered milestones that are each testable by a human and sized for one spec.
It touches no GitHub state: a milestone becomes an issue only when its spec is written.

### Guardrails and permissions

- **Global** (`~/.claude/settings.json`): Matt's `git-guardrails-claude-code` `PreToolUse` hook,
  which blocks `git push`, `git reset --hard`, `git clean -f` and `git branch -D` in the Bash
  tool. `factory-job` and `factory-gate` push through a subprocess, so it does not affect them.
- **Agents** (`hooks/hooks.json` in the plugin): a `PreToolUse` hook on Bash, Write, Edit,
  MultiEdit and NotebookEdit runs `agent_guard.py`, which takes the role from the hook's
  `agent_type`. Every other session and agent passes untouched.
  - Every agent: no `gh`, no `git push`, no `git remote` edits.
  - planner: writes only under `factory/jobs/`.
  - builder: writes only under the worktrees and `factory/jobs/`, and never edits an existing
    file matching `protected_paths`.
  - reviewer: writes only under `factory/jobs/`; Bash limited to `git diff`, `log`, `show`,
    `merge-base`, `rev-parse` and `status`, optionally after `cd`.

  This is defence in depth, not a sandbox: `factory-job` and the gate are the real boundary.
- **Project** (`.claude/settings.json`, written by `factory-init`, since plugins cannot ship
  permissions): allows `factory-job`, `factory-gate`, `factory/checks.sh`, `git add`, `commit`,
  `diff`, `log`, `show`, `status`, `fetch`, `merge`, `merge-base`, `rev-parse` and edits under
  the worktrees and `factory/jobs/`, so the factory never stops for approval. Denies `git push`.
  The project adds its own toolchain commands.

## factory-init

Users do not run it by hand any more: `/software-factory:setup` (below) runs it.
`factory-init [--base <branch>] [--force] [--labels] [--check]`, run from the repository root:

- Writes what is missing (everything with `--force`): `factory/config.json` (with the detected
  base branch), `factory/checks.sh`, `.github/workflows/checks.yml`, `.worktreeinclude`,
  `CLAUDE.md`, `GLOSSARY.md`, `docs/architecture.md`. The `checks.sh` template fails until the
  project replaces it.
- Merges `.gitignore` and `.claude/settings.json` (permissions, the `ctdes-factory` marketplace
  with `autoUpdate`) instead of replacing them. It does not enable the plugin: it is installed
  once per user (see 0.5.2).
- Appends a `## Software factory` section to an existing `CLAUDE.md` that does not mention
  `factory/checks.sh`.
- Warns about other workflows in `.github/workflows/`: the required check must run `checks.sh`.
- `--labels` creates only the missing labels and never modifies existing ones. It warns if the
  `queue` or `spec` label already exists with open issues, because the factory would pick them up.
- `--check` writes nothing. It prints one line per requirement, `ok`, `fail` or `warn` (git
  2.40+, python 3.10+, `gh` authenticated with `WRITE`, `MAINTAIN` or `ADMIN` on the repository,
  a global `PreToolUse` hook on Bash that mentions git), and per setup step, `ok` or `todo`
  (factory files, labels, `checks.sh` no longer the template locally and on `origin/<base>`,
  `checks` required by branch protection or a ruleset). It exits 1 only on a `fail`: a `todo`
  is the next step, not an error.

### /software-factory:setup

The single entry point after installing the plugin. A skill, because most of it is judgement:
reading a codebase, writing checks and context files, interviewing the user. The deterministic
parts stay in `factory-init`.

1. `factory-init --check`; stop on `fail` (or start a repository and its GitHub remote, with the
   user's consent, when there is none).
2. Decide new or existing project from the tracked files, confirmed by the user; switch to the
   `factory-setup` branch; `factory-init --labels`.
3. Existing project: real `checks.sh` from the project's own commands, CI toolchain,
   `protected_paths` for the existing tests, `CLAUDE.md`, `GLOSSARY.md` and
   `docs/architecture.md` drafted from the code, toolchain permissions, `.worktreeinclude`.
   New project: requirements document (optional) → project-level `grilling` → `docs/brief.md`
   → `domain-modeling` → `to-roadmap` → milestone 0 built with the user in the same session.
4. `checks.sh` proven on a fresh worktree, then the `factory-setup` PR. The user pushes and
   merges; the skill waits for CI.
5. The user turns on `checks` as a required check (it needs admin rights); `--check` confirms.

Every step leaves a file or a GitHub state, so rerunning the skill continues where it stopped.

## Out of scope

Not implemented, on purpose. Each item can be added later as one more transition or piece
without touching the rest.

- Auto-merge into the base branch. The factory never merges there; the human does. First
  candidate: standalone tickets with `risk: low` and a `PASS` review.
- UI or UX reviewers with a browser and per-port dev servers.
- Fast, standard and full lanes: risk already picks models and review.
- A `SubagentStop` hook on the builder: the gate decides.
- Dashboards inside the factory, cost per job and OpenTelemetry. The factory only emits events
  (see Events); viewing them is factory-office's job.
- Scheduled cloud runs and nightly triage.
- Deployment of any kind.
- Generating the ticket graph without human approval.

## History

### Phases

The factory was built in six phases, from the outside in: first what is deterministic and
testable without agents, then the agents one by one, and the orchestration last. Each phase
ended when all its acceptance criteria passed and the human confirmed it. The criteria are in
the [original brief](docs/original-brief.es.md#fases-de-implementación).

1. **Test repository:** `textkit`, `checks.sh`, CI as a required check, labels, global hook.
2. **`job` and `gate`:** the full ticket state machine, the GitHub adapter with a fake mode, the
   gate, and a test per legal transition.
3. **Agents and skills:** planner, builder and reviewer, each tested by hand on prepared job
   folders, including a prompt-injection issue.
4. **Orchestrator, ticket level:** standalone issues to ready PRs, `needs-info`, a second round
   after `CHANGES`, session kill and resume, `concurrency: 2`, `rework`.
5. **Spec level:** a five-ticket spec with a dependency graph built end to end into one PR,
   including a merge conflict, an isolated `needs-human` and a child added mid-spec.
6. **Packaging:** the plugin, installed in a second repository (`CTDes/factory-sandbox`) without
   copying folders, and one agent change published once that reached both repositories.

### Deviations and decisions

Everything that changed from the brief, with its reason. Each item was proposed to the human
before it was applied.

**Phase 1**
- The test repository is public: on GitHub Free, branch protection with a required check only
  exists for public repositories.
- `checks.sh` exports `PYTHONDONTWRITEBYTECODE=1`: a stale `.pyc` (same size, same second) gave
  false results twice.

**Phase 2**
- `job merge` was implemented in phase 2 because its transitions are in the ticket table.
- Added transitions: `intake → needs-human` (the planner breaks its contract twice) and
  `needs-human → intake` (rework of a job without a valid plan). The contract-failure counter
  lives in `job.json`, not in the orchestrator.
- `merging → build` does not increment `round`; `build → gate` already does.
- The builder does not apply a file priority order: `job.json` stores in `feedback` the exact
  file that sent it back to `build`, and the previous `build.md` is archived in `round-N/`.
- The gate also requires evidence for every plan criterion `Cn` and rejects evidence paths
  outside the worktree.
- `job create` requires the `queue` label. The factory's comments are recognised by the
  `[factory]` prefix, because the factory comments with the human's account.
- `ready`/`needs-human → done` also deletes the job's local and remote branch.

**Phase 3**
- Subagents have no working-directory field: the prompt requires `cd <worktree> &&` in every
  command and the guard blocks writes outside the worktree.
- The `tools` field cannot restrict Bash to some commands, so the guard limits the reviewer to
  read-only git.
- `gh` is blocked only for the agents, not with a project `deny`, so `/to-spec` and `/to-tickets`
  keep working in the human's session.
- Matt's global hook searches for the push text in the whole command, so it also blocks commit
  messages or scripts that contain it (known false positive).

**Phase 4**
- `job next --only <job|issue>` for `issue <n>` and `rework <n>`.
- `READY` with a dirty tree or no commits counts as a contract failure (back to the builder once,
  then escalate).
- From round 2, the builder's prompt says the previous `build.md` was archived (a resumed
  builder forgot it).
- The Agent tool has no `name` parameter: the orchestrator resumes builders by id with
  SendMessage within the session.
- Known gap: a standalone ticket's PR in `ready` that falls into conflict with the base is not
  detected on its own; it is handled with `rework` and a comment.

**Phase 5**
- Merges into the same base branch run one at a time (`job next`/`job start`), and a push
  rejected because the base moved releases the claim and leaves the job in `merging` to retry:
  two simultaneous `job merge` runs on the same spec branch raced.
- The final review uses the spec issue as its criterion.

**Phase 6**
- Packaged before finishing a spec in a real project, at the human's decision.
- Plugin agents ignore `hooks` and `permissionMode` in their frontmatter: the guardrails live in
  the plugin's `hooks/hooks.json`, and the guard derives the role from `agent_type`.
- Plugins cannot ship permissions: `factory-init` writes them into each repository's
  `.claude/settings.json`, together with the marketplace (with `autoUpdate`) and, until 0.5.2,
  the enabled plugin.
- Opening a repository whose `settings.json` enables the plugin creates a project-scope install
  besides the user-scope one, updated separately (superseded in 0.5.2: the plugin is no longer
  enabled per project).
- Names: agents `software-factory:<agent>`, skills `/software-factory:<skill>`, executables
  `factory-job`, `factory-gate`, `factory-init`.

**After phase 6**
- 0.1.3, `factory-init` for existing repositories:
  - An existing `CLAUDE.md` that does not mention `factory/checks.sh` gets a
    `## Software factory` section. Before, it was left without the factory's context.
  - It warns about workflows already in `.github/workflows/`, because the required check must
    run `checks.sh`.
  - `--labels` creates only missing labels, without `--force`. Before, it overwrote the colour
    and description of existing ones.
  - It warns if the `queue` or `spec` label already exists with open issues, because the factory
    would take them as work.
- The design was rewritten in English as a reference of the current implementation; the
  original Spanish brief is archived in `docs/original-brief.es.md`.
- 0.2.0, everything in English: the agents' and orchestrator's prompts, the prompts built by
  `job next`, the file-contract headings, `issue.md`, `checks.md`, `merge.md`, `rework-N.md` and
  every comment and PR body the factory posts. The parser still accepts the old Spanish headings,
  ignoring case, so jobs started before the switch keep working.
- 0.3.0, optional event emitter (Events) for factory-office, a separate service with its own
  database that shows every repository and machine. The factory pushes events instead of a
  second plugin in every repository, because repositories on other machines must report too and
  GitHub labels alone cannot tell build, gate and review apart. Built by hand, not by the
  factory: `plugin/**` is a protected path in this repository.
- 0.3.1, `job start` writes a `start <action>` note to `events.log` (and emits it).
- 0.4.0, `factory-job office link <token>` replaces per-machine environment variables as the way
  to connect: the office has a single token and each repository opts in. The variables remain
  for CI. `events status|flush|backfill` became `office status|flush|backfill`.
- 0.4.1, after factory-office's first job spent two gate rounds on evidence its checks never saw:
  - Evidence names may contain spaces inside backticks (node:test names); before, those lines
    were malformed and the builder had to rename tests.
  - `job advance` from build runs the gate's evidence check, so bad evidence goes back to the
    builder as a contract failure instead of costing a round.
  - The planner may not write criteria the gate already guarantees ("existing tests still
    pass", "checks.sh is green"); one such criterion forced the builder to invent a test.
  - The reviewer prompt lists the job's surfaces and says whether a security review is required,
    instead of "Security surface: not set", which read as a contradiction of `surfaces=ui`.
- 0.5.0, `to-roadmap` skill: the factory had no step between "a project" and "a spec", so large
  projects were either crammed into one spec or split by hand. It writes `docs/roadmap.md`
  (milestones, one spec each, walking skeleton first) and updates it after each milestone.
  `to-spec` reads it. The README documents the two ways to work: roadmap → specs for a new
  project, issues for an existing one.
- 0.5.1, the files a new project starts with:
  - The `GLOSSARY.md` template uses `domain-modeling`'s format (`**Term**:` / `_Avoid_:`)
    instead of a table, so the skill does not mix two formats.
  - `to-roadmap` offers to fill `CLAUDE.md` and `docs/architecture.md` from what was decided;
    the glossary and ADRs stay with `domain-modeling`.
  - Roadmaps start with a milestone 0 built by hand: scaffold, the real `factory/checks.sh` and
    CI. The factory cannot build it, because `factory/**` and `.github/**` are protected and the
    gate judges with the base branch's `checks.sh`.
- 0.5.2, `factory-init` no longer enables the plugin in the project's settings, only declares
  the marketplace. Each repository that enabled it had its own project-scope install, and those
  stayed on 0.4.x while the user-scope install reached 0.5.1. One install per user keeps a
  single copy up to date; the cost is a one-time `claude plugin install` per machine or person.

- 0.6.0, `/software-factory:setup`: getting started took a README of manual steps (fill
  `checks.sh`, the context files and `protected_paths`, push, protect the branch, and for a new
  project chain grilling, domain-modeling and to-roadmap and build milestone 0 by hand). One
  resumable skill now does all of it, new or existing project, and asks the user only for
  decisions, the push and the merge. `factory-init --check` reports requirements and progress.
  Branch protection stays manual: it needs admin rights and is a one-time click. New projects
  get a `docs/brief.md` from the interview (optionally seeded from a requirements document),
  which `to-roadmap` reads. Milestone 0 is still outside the factory, but built in the setup
  session instead of on the user's own.
- 0.7.0, job history in git: a job's plan, rounds and reviews lived only in the gitignored
  `factory/jobs/` of one machine, so a wiki on another machine (the factory-office) could not
  show how anything was built without becoming the only copy of it. `factory-job` now commits
  `docs/history/<job-id>.md` into the job's branch when it reaches a human or merges into its
  spec (see Job history); `factory-job history` backfills older jobs. `history_dir` is the
  first optional key in `config.json`, so existing configs keep validating.
- 0.8.0, `factory-job vault`: the roadmap, specs, tickets, decisions and job records were spread
  over the repository, GitHub and the job folders, with nothing to browse them as a whole. The
  vault joins them into linked notes (see Wiki) that Obsidian opens and Quartz publishes. The
  GitHub adapter gains `all_issues` and `all_prs` (open and closed) for it.
- 0.9.0, wiki publishing: the plan was a GitHub Action that builds Quartz and uploads the site,
  but the office runs on the user's machine (127.0.0.1), out of reach of GitHub's runners. The
  office builds Quartz instead and factory-job sends it the vault after transitions, through the
  same link as events. Once the office is on a public host, a CI job can send the same upload.

## References

- [mattpocock/skills](https://github.com/mattpocock/skills): the skills copied here (MIT)
- [ZazenCodes · Software Factory v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2): design reference for the spine; GPLv3, no files copied
- Claude Code docs: [Skills](https://code.claude.com/docs/en/skills), [Subagents](https://code.claude.com/docs/en/sub-agents), [Hooks](https://code.claude.com/docs/en/hooks), [Plugins](https://code.claude.com/docs/en/plugins/overview), [Worktrees](https://code.claude.com/docs/en/worktrees)
