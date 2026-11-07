"""factory-init: prepare a repository for the software factory, without copying folders by hand.

Writes only what is missing (or everything with --force), merges .gitignore and
.claude/settings.json instead of replacing them, and can create the GitHub labels.
In an existing repository it also appends the factory section to an existing CLAUDE.md,
warns about CI workflows that already exist, and never overwrites existing labels.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from lib.util import EXIT_OK, EXIT_USAGE, CommandError, run

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
GITIGNORE_LINES = ["factory/jobs/", ".claude/worktrees/"]

# (template name, destination relative to the repo root, executable)
FILES = [
    ("config.json", "factory/config.json", False),
    ("checks.sh", "factory/checks.sh", True),
    ("worktreeinclude", ".worktreeinclude", False),
    ("checks.yml", ".github/workflows/checks.yml", False),
    ("CLAUDE.md", "CLAUDE.md", False),
    ("GLOSSARY.md", "GLOSSARY.md", False),
    ("architecture.md", "docs/architecture.md", False),
]

CLAUDE_MD_MARKER = "factory/checks.sh"  # an existing CLAUDE.md that mentions it is left alone
# Labels the factory reads to find work: open issues already carrying them get picked up.
WORK_LABEL_KEYS = ("queue", "spec")

LABEL_COLORS = {
    "queue": "0E8A16",
    "spec": "5319E7",
    "needs_info": "FBCA04",
    "needs_human": "D93F0B",
    "in_progress": "1D76DB",
}


def repo_root() -> Path:
    try:
        out = run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    except CommandError as exc:
        raise SystemExit(f"factory-init: not inside a git repository\n{exc}") from exc
    return Path(out)


def default_branch(root: Path) -> str:
    proc = run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root, check=False
    )
    ref = proc.stdout.strip()
    return ref.split("/", 1)[1] if ref.startswith("origin/") else "main"


def _merge_list(base: list[Any], extra: list[Any]) -> list[Any]:
    return base + [x for x in extra if x not in base]


def merge_settings(existing: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    perms = dict(out.get("permissions") or {})
    for key in ("allow", "deny"):
        perms[key] = _merge_list(list(perms.get(key) or []), template["permissions"][key])
    out["permissions"] = perms
    for key in ("extraKnownMarketplaces",):
        merged = dict(out.get(key) or {})
        merged.update(template[key])
        out[key] = merged
    return out


def other_workflows(root: Path) -> list[str]:
    wf = root / ".github" / "workflows"
    if not wf.is_dir():
        return []
    return sorted(
        p.name
        for p in wf.iterdir()
        if p.is_file() and p.suffix in (".yml", ".yaml") and p.name != "checks.yml"
    )


def append_claude_section(path: Path) -> bool:
    """Append the factory section to an existing CLAUDE.md unless it already mentions checks.sh."""
    text = path.read_text(encoding="utf-8")
    if CLAUDE_MD_MARKER in text:
        return False
    section = (TEMPLATES / "CLAUDE-section.md").read_text(encoding="utf-8")
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    path.write_text(text + sep + section, encoding="utf-8")
    return True


def _gh_list(root: Path, *args: str, field: str) -> list[dict[str, Any]]:
    out = run(["gh", *args, "--limit", "1000", "--json", field], cwd=root).stdout
    return list(json.loads(out or "[]"))


def create_labels(root: Path) -> list[str]:
    """Create the config labels that are missing. Existing labels are never modified."""
    report: list[str] = []
    cfg = json.loads((root / "factory" / "config.json").read_text(encoding="utf-8"))
    existing = {d["name"] for d in _gh_list(root, "label", "list", field="name")}
    for key, label in cfg["labels"].items():
        if label not in existing:
            run(
                [
                    "gh",
                    "label",
                    "create",
                    label,
                    "--color",
                    LABEL_COLORS.get(key, "BFD4F2"),
                    "--description",
                    f"software factory: {key}",
                ],
                cwd=root,
            )
            report.append(f"label    {label}")
            continue
        report.append(f"kept     label {label} (already exists)")
        if key not in WORK_LABEL_KEYS:
            continue
        issues = _gh_list(
            root, "issue", "list", "--state", "open", "--label", label, field="number"
        )
        if issues:
            report.append(
                f"warn     label {label} already has {len(issues)} open issue(s): "
                "/software-factory:factory run will treat them as factory work. If that is "
                "not intended, rename it under `labels` in factory/config.json and rerun "
                "factory-init --labels"
            )
    return report


def init(root: Path, base: str | None, force: bool, labels: bool) -> list[str]:
    report: list[str] = []
    base = base or default_branch(root)
    workflows = other_workflows(root)
    for name, rel, executable in FILES:
        dst = root / rel
        if dst.exists() and not force:
            if name == "CLAUDE.md" and append_claude_section(dst):
                report.append(f"updated  {rel} (+software factory section)")
            else:
                report.append(f"kept     {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        if name == "config.json":
            cfg = json.loads(text)
            cfg["base_branch"] = base
            text = json.dumps(cfg, indent=2) + "\n"
        if name == "checks.yml":
            text = text.replace("branches: [main]", f"branches: [{base}]")
        dst.write_text(text, encoding="utf-8")
        if executable:
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        report.append(f"created  {rel}")

    gi = root / ".gitignore"
    current = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in current]
    if missing:
        sep = "" if not current or current[-1] == "" else "\n"
        with gi.open("a", encoding="utf-8") as fh:
            fh.write(sep + "# software factory\n" + "\n".join(missing) + "\n")
        report.append(f"updated  .gitignore (+{', '.join(missing)})")
    else:
        report.append("kept     .gitignore")

    settings_path = root / ".claude" / "settings.json"
    template = json.loads((TEMPLATES / "settings.json").read_text(encoding="utf-8"))
    existing = (
        json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    )
    merged = merge_settings(existing, template)
    if merged != existing:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        report.append("updated  .claude/settings.json (permissions, marketplace)")
    else:
        report.append("kept     .claude/settings.json")

    if workflows:
        report.append(
            f"warn     existing workflows: {', '.join(workflows)}. The required check must run "
            "factory/checks.sh: make one of them call it, or keep checks.yml and drop the "
            "duplicated steps"
        )

    if labels:
        report.extend(create_labels(root))
    return report


NEXT_STEPS = """
Next steps:
  1. Edit factory/checks.sh (lint, typecheck, tests, build) until it passes on {base}.
  2. Fill CLAUDE.md (and its "Software factory" section), GLOSSARY.md and
     docs/architecture.md; add your existing tests to protected_paths in factory/config.json.
  3. Commit, push, and make the `checks` workflow a required check on {base}.
  4. Label an issue `ready-for-agent` and run /software-factory:factory run.
New project? Start with /software-factory:grilling and /software-factory:to-roadmap
instead: steps 1-3 become its milestone 0 (see the README, "Two ways to work").
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory-init", description=__doc__)
    p.add_argument("--base", help="base branch (default: origin/HEAD, else main)")
    p.add_argument("--force", action="store_true", help="overwrite files that already exist")
    p.add_argument(
        "--labels", action="store_true", help="create the config labels on GitHub with gh"
    )
    args = p.parse_args(argv)
    root = repo_root()
    if Path(os.path.realpath(root)) != Path(os.path.realpath(Path.cwd())):
        print(f"factory-init: run it from the repository root ({root})", file=sys.stderr)
        return EXIT_USAGE
    for line in init(root, args.base, args.force, args.labels):
        print(line)
    print(NEXT_STEPS.format(base=args.base or default_branch(root)))
    return EXIT_OK
