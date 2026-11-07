---
name: setup
description: "Prepare a repository for the software factory, new or existing: checks the requirements, writes the real factory/checks.sh and the context files, opens the setup PR and guides the required check. For a new project it first interviews the user and writes the brief, glossary and roadmap. Resumable: rerun it to continue."
disable-model-invocation: true
argument-hint: "[path to a requirements document]"
allowed-tools:
  - Bash(factory-init *)
---

# /software-factory:setup

Arguments: `$ARGUMENTS`

The one command a user runs after installing the plugin. It takes a repository from "nothing"
to "the factory can take its first issue or spec", doing everything that can be automated and
asking the user only for decisions and for the steps Claude is not allowed to do.

The factory's agents start every job knowing only what the repository says, and the gate judges
every change with the base branch's `factory/checks.sh`. That is why setup cares so much about
two things: **checks that are real and green**, and **context files that are true**.

## Ground rules

- **Resumable.** Each step leaves a file or a GitHub state behind. Always start with
  `factory-init --check` and the files on disk, skip what is done, and say what you skipped.
- **Show before writing.** Every file you write for the project (`checks.sh`, the CI workflow,
  `CLAUDE.md`, `GLOSSARY.md`, `docs/architecture.md`, `protected_paths`, the brief, the
  roadmap) is shown to the user as a draft first. Never drop content someone already wrote.
- **Facts are yours, decisions are the user's.** Explore the code, manifests, CI and docs
  yourself; ask the user only what the repository cannot tell you.
- **You do not push.** When a push is needed, stop and ask the user to run it with `!`
  (for example `! git push -u origin factory-setup`), then continue.
- **You do not change GitHub settings** other than labels and the setup PR. The required check
  is turned on by the user (step 6).
- **Everything goes through one PR** on the branch `factory-setup` against the base branch.
  `factory/**` and `.github/**` are protected paths: the factory itself can never write them,
  so this PR is the one moment they are set up.
- **Follow the bundled skills, do not reinvent them.** When a step says "follow X", read
  `${CLAUDE_PLUGIN_ROOT}/skills/X/SKILL.md` and do what it says, scoped as the step describes.
- Talk to the user in their language; write every repository file, branch and commit in English
  unless the project's existing files are in another language.

## 1. Preflight

Run `factory-init --check` from the repository root.

- **Not a git repository** (it says so): ask the user whether to start one here. If yes:
  `git init -b main`, an initial commit (`git commit --allow-empty -m "Initial commit"` if there
  are no files yet), then `gh repo create <name> --private --source . --remote origin` (ask for
  the name and visibility; never pass `--push`). Ask the user to run
  `! git push -u origin main`, and run the check again.
- **Any `fail` line:** explain how to fix each one (install or upgrade git/python, `gh auth
  login`, ask for write access, add the `origin` remote) and stop. Rerun when the user says it
  is fixed.
- **`warn` for the guardrails hook:** tell the user once that Claude can run destructive git
  commands in this machine without it (DESIGN.md · Guardrails), and continue.
- **Every setup line is `ok`:** the repository is ready. Skip to step 7.
- If the base branch does not exist on `origin` yet (an empty GitHub repository), ask the user to
  push it first: the setup PR needs a base.

## 2. New or existing project

Decide which path to take from what is tracked (`git ls-files`):

- **Existing project:** there is source code, a package manifest or tests.
- **New project:** only a README, LICENSE, `.gitignore`, docs or nothing at all.

Say which one you think it is and why, in one line, and let the user correct you. If a
`docs/brief.md` or `docs/roadmap.md` already exists, it is a new project that was set up halfway:
continue where it stopped.

Then switch to the setup branch: `git switch factory-setup` if it exists, otherwise
`git switch -c factory-setup` from an up-to-date base branch. Run `factory-init --labels`. It
writes only the missing files, merges `.gitignore` and `.claude/settings.json`, creates the
missing labels and warns about existing workflows or labels with open issues; relay its warnings.

## 3a. Existing project: make the repository describe itself

1. **Explore.** Find the stack and the commands the project already uses: package manifests
   (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`…), lockfiles, `Makefile`
   or task runners, existing CI workflows, `README`/`CONTRIBUTING`. For a large codebase, use an
   Explore sub-agent and keep only its conclusions.
2. **`factory/checks.sh`.** Replace the template with the project's real dependency install,
   lint, typecheck, tests and build, in that order, keeping the template's contract header
   (non-interactive, installs dependencies on a fresh worktree, never rewrites tracked files: no
   `--fix`, no snapshot updates, exits non-zero on any failure, runs from the current directory).
   Use the commands the project already has; if one of the four is missing (no linter, no
   typecheck), ask whether to add the stack's usual tool now or leave it out. Run it until it
   passes. A check that only passes because something was skipped is not passing: say so.
3. **CI.** Edit `.github/workflows/checks.yml` so it installs the toolchain `checks.sh` needs
   (`actions/setup-node`, `setup-python`… with the versions the project declares). Keep the job
   name `checks`: that is the required check. If `factory-init` warned about other workflows,
   ask whether to keep them as they are, make one of them call `factory/checks.sh`, or drop
   their steps that duplicate it.
4. **`protected_paths`.** Propose globs for the existing tests (`tests/**`, `**/*.test.ts`,
   `src/**/__tests__/**`…) and anything else the factory must never edit (migrations already
   applied, generated code, vendored code), and add them to `factory/config.json` after the
   defaults. Explain that the factory can still add new test files.
5. **Context files**, drafted from the code, not from guesses:
   - `CLAUDE.md`: what the project is, the stack, how to install, run one test and format, and
     the conventions you can see in the code (public interface, test style, error handling).
     In an existing `CLAUDE.md`, only fill the `## Software factory` section `factory-init`
     appended (its `Run a single test:` line especially).
   - `GLOSSARY.md`: the domain terms the code uses, in the template's format. Follow
     `domain-modeling` for the format; a first pass with the core terms is enough.
   - `docs/architecture.md`: the main modules, their responsibility and public interface, and
     the allowed dependencies between them and on third-party packages.
6. **Permissions.** Add the toolchain commands the factory's builder will need (for example
   `Bash(npm *)`, `Bash(uv run *)`) to `permissions.allow` in `.claude/settings.json`, so jobs
   do not stop for approval. Ask before adding anything broad.
7. **`.worktreeinclude`.** If the project needs untracked files to run (`.env`, local config),
   list them there so every job's worktree gets a copy.

Continue with step 4.

## 3b. New project: from an idea to milestone 0

This path needs the user throughout: they are the one who knows what they want. Each step ends
with a file, so a new session can resume from it.

1. **Requirements.** If `$ARGUMENTS` names a file, read it. Otherwise ask once whether there is
   a requirements document, notes or a previous spec anywhere on disk, and read it if there is.
   If it lives outside the repository, copy it into `docs/requirements/` (ask first) so the
   agents can read it later.
2. **Interview.** Follow `grilling`, scoped to the **whole project**, not a feature: vision,
   users, the problem, MVP scope, what is out, rough architecture and stack, data, integrations,
   technical risks, how it will be deployed and tested. With a requirements document, do not
   ask what it already answers: confirm your reading of it and grill the gaps and
   contradictions. Stop when the user confirms you share an understanding.
3. **Brief.** Write `docs/brief.md` with the template below, show it, iterate until the user
   approves it. It is the base every later document derives from.
4. **Domain.** Follow `domain-modeling`: `GLOSSARY.md` with the terms that came up, and an ADR
   in `docs/adr/` for each hard-to-reverse decision (stack, storage, deployment, main
   boundaries).
5. **Roadmap.** Follow `to-roadmap` (it reads the brief and this conversation): `docs/roadmap.md`
   with M0 and the milestones, and its step 5, which fills `CLAUDE.md` and
   `docs/architecture.md` from what was decided.
6. **Milestone 0, here and now.** M0 is the bootstrap the factory cannot build. Build it with the
   user in this session, following its description in the roadmap:
   - the stack's minimal scaffold: package manifest, lint, typecheck and test tooling, one
     trivial test, nothing else (features belong to M1, built by the factory);
   - a real `factory/checks.sh` and the CI toolchain, as in 3a steps 2–3, passing locally;
   - `protected_paths`, permissions and `.worktreeinclude`, as in 3a steps 4, 6 and 7;
   - `CLAUDE.md` updated with the commands that now really exist.

Continue with step 4.

## 4. Prove the checks on a fresh checkout

Commit everything on `factory-setup` (stage the files you wrote by name; no `git add -A`).
Then prove `checks.sh` works where the gate runs it, in a clean worktree:

```sh
dir="$(mktemp -d)/factory-setup-check"
git worktree add --detach "$dir" HEAD && (cd "$dir" && factory/checks.sh)
git worktree remove --force "$dir"
```

Copy the `.worktreeinclude` files into it first if there are any. If it fails there but passed
in the repository, something is missing from the repository or from `.worktreeinclude`: fix
it, commit, and try again.

## 5. The setup PR

1. Ask the user to run `! git push -u origin factory-setup`.
2. `gh pr create --base <base> --head factory-setup --title "Set up the software factory"` with a
   body that lists what was added and why (checks, CI, protected paths, context files, and the
   brief and roadmap for a new project).
3. Wait for CI: `gh pr checks <n> --watch`. If `checks` fails in CI but passed locally, it is
   almost always the toolchain step of the workflow: read the log
   (`gh run view <run> --log-failed`), fix, commit, and ask for another push.
4. Ask the user to review and merge the PR. If they ask you to merge it, use
   `gh pr merge <n> --merge`. Then `git switch <base>`, `git pull --ff-only` and
   `git branch -d factory-setup`.

## 6. The required check (by the user)

Branch protection makes GitHub refuse to merge anything into the base branch unless the `checks`
job is green. It is the last barrier behind the factory's gate, and it keeps the base branch the
gate starts from green. Turning it on needs admin rights, so the user does it:

1. Open the URL `factory-init --check` printed (`https://github.com/<owner>/<repo>/settings/branches`).
2. Add a branch protection rule (or a ruleset) for the base branch.
3. Tick **Require status checks to pass before merging** and add `checks`. It only appears in
   the search box once the workflow has run at least once (the setup PR did that).
4. Save.

Run `factory-init --check` again to confirm the line is `ok`. If it cannot be turned on (private
repository on GitHub Free, or no admin), say what is lost, a merge of a red PR by hand, and
continue: the factory itself works without it.

## 7. Hand off

Print the final `factory-init --check` and the next step:

- **Existing project:** offer to write the first issue together: small, one PR, with what to
  change and how to know it works. Label it with the queue label (`ready-for-agent` unless
  `factory/config.json` says otherwise) and run `/software-factory:factory issue <n>`. Once the
  user trusts it, `/software-factory:factory run` drains the queue.
- **New project:** M1 comes next. Offer to start it: `grilling` on that milestone
  (feature-level, short), then `/software-factory:to-spec`, `/software-factory:to-tickets`, add
  the queue label to the spec and every ticket, and `/software-factory:factory spec <n>`.

<brief-template>

# <Project name>

<One paragraph: what it is, for whom, and the problem it solves.>

## Users and their goals

- <Who uses it and what they need to get done.>

## MVP

- <The capabilities the first usable version must have, in the user's words.>

## Out of scope

- <What it will deliberately not do, at least for now.>

## Constraints

- <Stack, platforms, hosting, budget, deadlines, compliance, integrations that are given.>

## Risks and unknowns

- <What could change the plan if it goes wrong, and what still has to be found out.>

## Sources

- <Requirements documents in docs/requirements/, if any, and what each one covers.>

</brief-template>
