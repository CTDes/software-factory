#!/usr/bin/env python3
"""PreToolUse guard for the factory's subagents (planner, builder, reviewer).

Wired from the plugin's hooks/hooks.json (role taken from the hook's `agent_type`),
or from a project agent's frontmatter as `agent_guard.py <planner|builder|reviewer>`.
Reads the hook JSON on stdin. Exit 0 = no objection (normal permissions apply);
exit 2 = blocked, stderr is shown to the agent.

Policy
- every agent: no `gh`, no `git push` (any spelling we can see), no remote edits.
- planner:  writes only under factory/jobs/. (It has no Bash at all.)
- builder:  writes only under .claude/worktrees/ and factory/jobs/; never edits an
            existing file matching protected_paths (adding new files is allowed).
- reviewer: writes only under factory/jobs/; Bash limited to read-only git
            (diff, log, show, merge-base, rev-parse, status), optionally after `cd`.

This is defence in depth, not a sandbox: a determined process can still reach the
network. The gate and bin/job are the real boundary for what reaches GitHub.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.util import matches_any

SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||&|\n")
GH_RE = re.compile(r"(^|[\s/;&|(`$'\"])gh(\s|$)")
GIT_PUSH_RE = re.compile(r"\bgit\b[^;&|\n]*\s['\"]?push['\"]?(\s|$)")
GIT_REMOTE_EDIT_RE = re.compile(r"\bgit\b[^;&|\n]*\sremote\s+(add|set-url|remove|rm|rename)\b")
REVIEWER_SEGMENT = re.compile(
    r"^\s*(cd\s+\S+|git(\s+-C\s+\S+)?(\s+--no-pager)?\s+(diff|log|show|merge-base|rev-parse|status)(\s[^`$<>]*)?)\s*$"
)


def block(message: str) -> int:
    print(f"BLOCKED by factory agent guard: {message}", file=sys.stderr)
    return 2


def project_root(payload: dict[str, object]) -> Path:
    env = os.environ.get("FACTORY_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path(str(payload.get("cwd") or ".")).resolve()


def protected_patterns(root: Path) -> list[str]:
    try:
        data = json.loads((root / "factory" / "config.json").read_text(encoding="utf-8"))
        return [str(p) for p in data.get("protected_paths", [])]
    except (OSError, ValueError):
        return ["factory/**", ".github/**", ".claude/**"]


def under(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def check_bash(agent: str, command: str) -> int:
    if GH_RE.search(command):
        return block("agents never call `gh`; bin/job is the only GitHub client.")
    if GIT_PUSH_RE.search(command):
        return block("agents never push; bin/job pushes after the gate.")
    if GIT_REMOTE_EDIT_RE.search(command):
        return block("agents never change git remotes.")
    if agent == "reviewer":
        for segment in filter(str.strip, SEGMENT_SPLIT.split(command)):
            if not REVIEWER_SEGMENT.match(segment):
                return block(
                    f"the reviewer may only run read-only git (diff, log, show, merge-base, "
                    f"rev-parse, status), optionally after `cd`; refused: {segment.strip()!r}"
                )
    if agent == "planner":
        return block("the planner has no shell.")
    return 0


def check_write(agent: str, root: Path, file_path: str, tool: str) -> int:
    if not file_path:
        return 0
    target = Path(file_path)
    if not target.is_absolute():
        return block(f"use an absolute path for {tool}: {file_path}")
    target = Path(os.path.realpath(target))
    jobs = root / "factory" / "jobs"
    worktrees = (root / ".claude" / "worktrees").resolve()
    allowed = [jobs.resolve()] + ([worktrees] if agent == "builder" else [])
    if not any(under(target, base) for base in allowed):
        where = "the job folder or its worktree" if agent == "builder" else "the job folder"
        return block(f"{agent} may only write inside {where}; refused: {target}")
    if agent == "builder" and under(target, worktrees):
        rel_parts = target.relative_to(worktrees).parts[1:]  # drop <job-id>/
        rel = "/".join(rel_parts)
        if rel and target.exists() and matches_any(rel, protected_patterns(root)):
            return block(
                f"{rel} is a protected path: you may add new files there but never modify "
                "or delete existing ones. Change the code, not the tests or the factory."
            )
    return 0


ROLES = ("planner", "builder", "reviewer")


def role_of(agent_type: object) -> str | None:
    """`software-factory:builder` (plugin agent) or `builder` (project agent) -> `builder`."""
    if not isinstance(agent_type, str) or not agent_type:
        return None
    name = agent_type.rsplit(":", 1)[-1]
    if name not in ROLES:
        return None
    if ":" in agent_type and not agent_type.startswith("software-factory:"):
        return None  # another plugin's agent that happens to share a name
    return name


def main(argv: list[str]) -> int:
    """Two wirings: `agent_guard.py <role>` from an agent's frontmatter (project agents), or
    `agent_guard.py` from the plugin's hooks.json, where the role comes from `agent_type`
    and any tool call that is not from a factory agent passes through untouched."""
    if len(argv) > 2 or (len(argv) == 2 and argv[1] not in ROLES):
        print("usage: agent_guard.py [planner|builder|reviewer]", file=sys.stderr)
        return 2
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return block("hook received invalid JSON")
    agent = argv[1] if len(argv) == 2 else role_of(payload.get("agent_type"))
    if agent is None:
        return 0
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if tool == "Bash":
        return check_bash(agent, str(tool_input.get("command", "")))
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        return check_write(agent, project_root(payload), path, tool)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
