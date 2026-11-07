"""factory-init --check: is this machine and repository ready for the factory? Writes nothing.

Two groups of lines, in the same format as factory-init's report:

- Requirements (``ok`` / ``fail`` / ``warn``): git, python, gh and its rights on the repository,
  the global git guardrails hook. A ``fail`` means the factory cannot run; the exit code is 1.
- Setup (``ok`` / ``todo``): factory files, labels, a real ``factory/checks.sh`` locally and on
  the base branch, and ``checks`` as a required check on the base branch. A ``todo`` is the
  next step for ``/software-factory:setup``, not an error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from lib.util import run

MIN_GIT = (2, 40)
MIN_PYTHON = (3, 10)
REQUIRED_CHECK = "checks"  # job name in templates/checks.yml
# Printed by templates/checks.sh: while it is there, the project has not written its checks.
TEMPLATE_CHECKS_MARKER = "still the template written by factory-init"
# viewerPermission values that can push, open PRs and manage labels.
WRITE_PERMISSIONS = ("ADMIN", "MAINTAIN", "WRITE")


def line(status: str, text: str) -> str:
    return f"{status:<9}{text}"


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def _fmt(version: tuple[int, ...]) -> str:
    return ".".join(str(n) for n in version)


# ---------------------------------------------------------------- requirements


def check_git() -> str:
    proc = run(["git", "--version"], check=False)
    version = parse_version(proc.stdout) if proc.returncode == 0 else None
    if version is None:
        return line("fail", "git not found")
    if version[:2] < MIN_GIT:
        return line("fail", f"git {_fmt(version)} (needs {_fmt(MIN_GIT)}+)")
    return line("ok", f"git {_fmt(version)}")


def check_python(version: tuple[int, ...] | None = None) -> str:
    version = version or tuple(sys.version_info[:3])
    if version[:2] < MIN_PYTHON:
        return line("fail", f"python3 {_fmt(version)} (needs {_fmt(MIN_PYTHON)}+)")
    return line("ok", f"python3 {_fmt(version)}")


def check_gh(root: Path) -> tuple[list[str], dict[str, Any] | None]:
    """gh installed, authenticated, and allowed to push/PR/label here. Returns the repo info."""
    try:
        proc = run(["gh", "--version"], cwd=root, check=False)
    except FileNotFoundError:
        return [line("fail", "gh not found: install the GitHub CLI (https://cli.github.com)")], None
    if proc.returncode != 0:
        return [line("fail", "gh not working: `gh --version` failed")], None
    out = [line("ok", f"gh {_fmt(parse_version(proc.stdout) or (0,))}")]
    if run(["gh", "auth", "status"], cwd=root, check=False).returncode != 0:
        out.append(line("fail", "gh not authenticated: run `gh auth login`"))
        return out, None
    out.append(line("ok", "gh authenticated"))
    proc = run(
        ["gh", "repo", "view", "--json", "nameWithOwner,viewerPermission,defaultBranchRef"],
        cwd=root,
        check=False,
    )
    if proc.returncode != 0:
        out.append(
            line(
                "fail",
                "no GitHub repository for this checkout: add an `origin` remote on GitHub "
                "(for a new project: `gh repo create <name> --private --source . --remote origin`)",
            )
        )
        return out, None
    repo = dict(json.loads(proc.stdout))
    perm = str(repo.get("viewerPermission") or "")
    nwo = repo.get("nameWithOwner")
    if perm in WRITE_PERMISSIONS:
        out.append(line("ok", f"gh can push, open PRs and manage labels on {nwo} ({perm})"))
    else:
        out.append(
            line(
                "fail", f"gh has {perm or 'no'} access to {nwo}: it needs write (push, PRs, labels)"
            )
        )
    return out, repo


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def check_guardrails() -> str:
    """Heuristic: a global PreToolUse hook on Bash whose command mentions git."""
    path = claude_config_dir() / "settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    for entry in (settings.get("hooks") or {}).get("PreToolUse") or []:
        matcher = str(entry.get("matcher") or "*")
        if matcher not in ("*", "") and not re.search(matcher, "Bash"):
            continue
        for hook in entry.get("hooks") or []:
            if "git" in str(hook.get("command") or ""):
                return line("ok", "global git guardrails hook")
    return line(
        "warn",
        f"no global git guardrails hook in {path}: Claude can run destructive git commands "
        "(see the plugin DESIGN.md, Guardrails)",
    )


# ---------------------------------------------------------------- setup state


def _config(root: Path) -> dict[str, Any] | None:
    try:
        return dict(json.loads((root / "factory" / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def _is_template(text: str) -> bool:
    return TEMPLATE_CHECKS_MARKER in text


def check_files(root: Path) -> list[str]:
    if _config(root) is None:
        return [line("todo", "factory files: run `factory-init --labels`")]
    out = [line("ok", "factory files (factory/config.json)")]
    checks = root / "factory" / "checks.sh"
    if not checks.exists() or _is_template(checks.read_text(encoding="utf-8")):
        out.append(line("todo", "factory/checks.sh is still the template: write the real checks"))
    else:
        out.append(line("ok", "factory/checks.sh written"))
    return out


def check_labels(root: Path, cfg: dict[str, Any]) -> str:
    proc = run(["gh", "label", "list", "--limit", "1000", "--json", "name"], cwd=root, check=False)
    if proc.returncode != 0:
        return line("todo", "labels: could not list them with gh")
    existing = {d["name"] for d in json.loads(proc.stdout or "[]")}
    missing = [name for name in cfg["labels"].values() if name not in existing]
    if missing:
        return line("todo", f"labels missing: {', '.join(missing)} (`factory-init --labels`)")
    return line("ok", "labels")


def check_base_checks(root: Path, base: str) -> str:
    run(["git", "fetch", "--quiet", "origin", base], cwd=root, check=False)
    proc = run(["git", "show", f"origin/{base}:factory/checks.sh"], cwd=root, check=False)
    if proc.returncode != 0:
        return line("todo", f"factory/checks.sh is not on origin/{base}: merge the setup PR")
    if _is_template(proc.stdout):
        return line("todo", f"factory/checks.sh on origin/{base} is still the template")
    return line("ok", f"factory/checks.sh merged into {base}")


def required_contexts(root: Path, nwo: str, base: str) -> set[str] | None:
    """Required status checks on base, from branch protection and rulesets. None: unreadable."""
    found: set[str] = set()
    readable = False
    proc = run(["gh", "api", f"repos/{nwo}/branches/{base}"], cwd=root, check=False)
    if proc.returncode == 0:
        readable = True
        rsc = (json.loads(proc.stdout).get("protection") or {}).get("required_status_checks") or {}
        found.update(rsc.get("contexts") or [])
        found.update(c.get("context") for c in rsc.get("checks") or [] if c.get("context"))
    proc = run(["gh", "api", f"repos/{nwo}/rules/branches/{base}"], cwd=root, check=False)
    if proc.returncode == 0:
        readable = True
        for rule in json.loads(proc.stdout or "[]"):
            if rule.get("type") != "required_status_checks":
                continue
            params = rule.get("parameters") or {}
            found.update(c.get("context") for c in params.get("required_status_checks") or [] if c)
    return found if readable else None


def check_required(root: Path, nwo: str, base: str) -> str:
    contexts = required_contexts(root, nwo, base)
    if contexts is not None and REQUIRED_CHECK in contexts:
        return line("ok", f"`{REQUIRED_CHECK}` is a required check on {base}")
    return line(
        "todo",
        f"`{REQUIRED_CHECK}` is not a required check on {base}: "
        f"https://github.com/{nwo}/settings/branches",
    )


def check(root: Path, base: str) -> tuple[list[str], bool]:
    """Every line of the report, and whether all requirements are met."""
    report = [check_git(), check_python()]
    gh_lines, repo = check_gh(root)
    report += gh_lines
    report.append(check_guardrails())
    cfg = _config(root)
    if cfg is not None:
        base = str(cfg.get("base_branch") or base)
    report += check_files(root)
    if repo is not None:
        nwo = str(repo["nameWithOwner"])
        if cfg is not None:
            report.append(check_labels(root, cfg))
        report.append(check_base_checks(root, base))
        report.append(check_required(root, nwo, base))
    ok = not any(r.startswith("fail") for r in report)
    return report, ok
