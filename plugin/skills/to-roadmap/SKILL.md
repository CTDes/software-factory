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
- `GLOSSARY.md` and `docs/adr/` if they exist: use the glossary's vocabulary and respect the ADRs.
- `docs/roadmap.md` if it exists: then this is an **update** (see below), not a new roadmap.
- In an existing codebase, explore enough to know what already exists, so no milestone rebuilds it.

### 2. Draft the milestones

<milestone-rules>

- **Each milestone is testable by a human on its own.** When its PR lands, someone can run the
  product and see something new working end to end. "Database layer done" is not a milestone.
- **The first milestone is a walking skeleton:** the thinnest path through every layer
  (input → logic → storage → output, deploy if relevant), with almost no features. It fixes the
  architecture, the stack and `factory/checks.sh` before anything grows on them.
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

### 5. Hand off

Tell the user the next step for milestone 1:
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
