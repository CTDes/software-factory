---
name: to-roadmap
description: "Turn a project-level conversation (usually a grilling session about a new project) into docs/roadmap.md: an ordered list of milestones, each one a spec the factory can build into a single testable PR. Also updates an existing roadmap after a milestone ships."
disable-model-invocation: true
argument-hint: "[update]"
---

# To Roadmap

The software factory builds one **spec** at a time: a spec and its ticket graph become a single
PR that a human tests and merges. A project bigger than one spec needs a **roadmap** first: an
ordered list of **milestones**, each of which will later become one spec through
`/software-factory:to-spec` and `/software-factory:to-tickets`.

This skill takes the current conversation (normally a `/software-factory:grilling` session about
the whole project: vision, users, MVP scope, what is out, rough architecture, technical risks)
and writes `docs/roadmap.md`. Do NOT interview the user from scratch: synthesize what was
discussed. If a decision the roadmap depends on was never settled, list it under **Open
questions** instead of inventing an answer, and suggest another grilling round for it.

It does not create GitHub issues, milestones or labels. Milestones become issues one at a time,
when their spec is written.

## Process

### 1. Gather context

- The conversation so far.
- `docs/brief.md` and `docs/requirements/` if they exist (written by `/software-factory:setup`
  for a new project): the roadmap delivers that brief's MVP and respects its out-of-scope list.
- `GLOSSARY.md` and `docs/adr/` if they exist: use the glossary's vocabulary and respect the ADRs.
- `docs/roadmap.md` if it exists: then this is an **update** (see below), not a new roadmap.
- In an existing codebase, explore enough to know what already exists, so no milestone rebuilds it.

### 2. Draft the milestones

<milestone-rules>

- **Each milestone is testable by a human on its own.** When its PR lands, someone can run the
  product and see something new working end to end. "Database layer done" is not a milestone.
- **Milestone 0 is a bootstrap done by hand, not by the factory,** in a new project or whenever
  the repo has no real checks yet. The factory cannot write it: `factory/**` and `.github/**`
  are protected paths, and the gate always runs the base branch's `factory/checks.sh`. M0 is the
  stack's minimal scaffold (package manifest, lint, typecheck and test tooling, one trivial
  test), a `factory/checks.sh` that runs them for real, and CI as a required check, merged to
  the base branch. The human builds it in their own session, with Claude's help if they want.
  Skip M0 when the repo already has real checks.
- **The first factory milestone (M1) is a walking skeleton:** the thinnest path through every
  layer (input → logic → storage → output, deploy if relevant), with almost no features. It
  fixes the architecture before anything grows on it.
- **Risk first.** Order next by what would change everything else if it went wrong: unknown
  integrations, performance limits, data model. Cosmetic and nice-to-have work goes last.
- **Size:** a milestone should break into roughly 4–10 tickets. Bigger means split it; one or
  two tickets means merge it with a neighbour or make it a standalone issue instead.
- **Linear by default.** Milestones run one after another: the factory builds one spec branch
  at a time against the base branch. Only mark two milestones as parallel if they touch
  unrelated parts of the code.
- **Later milestones stay coarse.** Describe the first two in detail; later ones in a few lines.
  They will be re-planned with what the first ones teach.

</milestone-rules>

### 3. Quiz the user

Present the milestones as a numbered list. For each: **title**, **what a human can test when it
lands**, **why it is in this position**. Ask:

- Is the first milestone thin enough to be a walking skeleton?
- Is the order right: does each milestone only depend on earlier ones?
- Should any milestone be split or merged?

Iterate until the user approves it.

### 4. Write `docs/roadmap.md`

Use the template below. Write the file; do not commit it unless the user asks.

If the conversation settled architectural decisions that are hard to reverse (stack, storage,
deployment, main boundaries), offer to record them as ADRs with
`/software-factory:domain-modeling`. New domain terms go to `GLOSSARY.md` the same way.

### 5. Fill the agents' context files

The factory's agents start every job without this conversation: they only know what the repo's
files say. Offer to fill, from what was decided, the files `factory-init` left as templates (read
each one first; replace placeholders, never drop content someone already wrote):

- `CLAUDE.md`: one paragraph on what the project is; the stack; how to install, run one test and
  format; the conventions (public interface, test style, error handling) that were settled.
  Commands that only exist after M0 can be written as the intended ones and checked in M0.
- `docs/architecture.md`: the modules agreed so far, their responsibility and public interface,
  and the allowed dependencies between them and on third-party packages. Only what was decided:
  later milestones add rows.

Do not touch `GLOSSARY.md` or `docs/adr/` here (that is `/software-factory:domain-modeling`'s job)
nor `factory/checks.sh` and `factory/config.json` (that is M0). Show the user the changes before
writing them.

### 6. Hand off

If the roadmap has an M0, the next step is building it by hand: scaffold, a real
`factory/checks.sh` that passes, CI as a required check, merged to the base branch. Add the
existing tests to `protected_paths` in `factory/config.json`. When this skill runs inside
`/software-factory:setup`, return to it here: setup builds M0 with the user and opens its PR.

Then, for the first factory milestone:
`/software-factory:grilling` on that milestone (short, feature-level), then
`/software-factory:to-spec`, `/software-factory:to-tickets`, label the spec and its tickets
with the queue label from `factory/config.json`, and `/software-factory:factory spec <n>`.

## Updating an existing roadmap

Run after a milestone's PR is merged, or when plans change (`/software-factory:to-roadmap update`).

- Mark finished milestones `done` with their spec issue and PR. Never rewrite a done milestone's
  content: it is history.
- Set the milestone being built to `in progress` with its spec issue.
- Re-plan the remaining ones with what was learned: reorder, split, merge, drop. Add a line to
  **Changes** saying what changed and why.
- Detail the next milestone if it was still coarse.

<roadmap-template>

# Roadmap

<One paragraph: what the project is, for whom, and what "done" means for this roadmap.>

## Out of scope

- <What this roadmap deliberately does not build.>

## Milestones

### M0 · Bootstrap (by hand) — status: planned | done (PR #m)

**Stack:** <language, framework, package manager, test runner, linter, typechecker.>

**Done when:** `factory/checks.sh` runs <the real checks> and passes on the base branch, CI
runs it as a required check, and `CLAUDE.md` lists the real commands.

### M1 · <title> — status: planned | in progress (spec #n) | done (spec #n, PR #m)

**A human can test:** <what works end to end when this lands, as a short demo script.>

**Scope:** <the capabilities included, in the glossary's vocabulary. No file paths.>

**Why here:** <the risk it retires or what it unblocks.>

**Depends on:** <earlier milestones, or "nothing".>

### M2 · <title> — status: planned

...

## Open questions

- <Decisions not settled yet, and which milestone needs them settled.>

## Changes

- <YYYY-MM-DD: what changed in the roadmap and why.>

</roadmap-template>

Avoid file paths and code snippets: they go stale. Milestones describe behaviour a human can see.
