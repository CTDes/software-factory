"""Load and validate factory/config.json. Refuse to work on any missing key or wrong type."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib import git
from lib.util import ConfigError

RISKS = ("low", "medium", "high")
MERGE_METHODS = ("merge", "squash", "rebase")
LABEL_KEYS = ("queue", "spec", "needs_info", "needs_human", "in_progress")

# key -> expected type (checked with isinstance; bool is rejected where int is expected)
SCHEMA: dict[str, type] = {
    "base_branch": str,
    "merge_method": str,
    "concurrency": int,
    "max_rounds": int,
    "spec_branch_prefix": str,
    "job_branch_prefix": str,
    "worktrees_dir": str,
    "labels": dict,
    "models": dict,
    "always_human_surfaces": list,
    "protected_paths": list,
    "checks_timeout_s": int,
    "log_tail_lines": int,
}

# Keys added after 0.6.0: optional, so existing config.json files keep working.
OPTIONAL: dict[str, tuple[type, object]] = {
    "history_dir": (str, "docs/history"),  # "" turns job history off
}


@dataclass(frozen=True)
class Config:
    root: Path  # main checkout (never a job worktree)
    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    @property
    def jobs_dir(self) -> Path:
        return self.root / "factory" / "jobs"

    @property
    def worktrees_dir(self) -> Path:
        return self.root / str(self.data["worktrees_dir"])

    def label(self, key: str) -> str:
        return str(self.data["labels"][key])

    def model(self, agent: str, risk: str | None = None) -> str:
        value = self.data["models"][agent]
        if isinstance(value, dict):
            return str(value[risk or "medium"])
        return str(value)


def find_root(cwd: Path | None = None) -> Path:
    """The main checkout: FACTORY_ROOT, else the parent of git's common dir.

    Using the common dir means bin/job run from inside a job worktree still finds
    the main checkout and its factory/jobs/.
    """
    env = os.environ.get("FACTORY_ROOT")
    if env:
        return Path(env).resolve()
    try:
        common = git.common_dir(cwd or Path.cwd())
    except Exception as exc:
        raise ConfigError(f"not inside a git repository: {exc}") from exc
    return common.parent


def _fail(msg: str) -> ConfigError:
    return ConfigError(f"factory/config.json: {msg}")


def validate(data: Any) -> None:
    if not isinstance(data, dict):
        raise _fail("top level must be an object")
    for key, typ in SCHEMA.items():
        if key not in data:
            raise _fail(f"missing key '{key}'")
        value = data[key]
        if typ is int and (isinstance(value, bool) or not isinstance(value, int)):
            raise _fail(f"'{key}' must be an integer, got {type(value).__name__}")
        if not isinstance(value, typ):
            raise _fail(f"'{key}' must be {typ.__name__}, got {type(value).__name__}")
    if data["merge_method"] not in MERGE_METHODS:
        raise _fail(f"'merge_method' must be one of {', '.join(MERGE_METHODS)}")
    for key in ("concurrency", "max_rounds", "checks_timeout_s", "log_tail_lines"):
        if data[key] < 1:
            raise _fail(f"'{key}' must be >= 1")
    for key in LABEL_KEYS:
        if not isinstance(data["labels"].get(key), str) or not data["labels"][key]:
            raise _fail(f"'labels.{key}' must be a non-empty string")
    models = data["models"]
    for key in ("planner", "final_reviewer"):
        if not isinstance(models.get(key), str):
            raise _fail(f"'models.{key}' must be a string")
    for key in ("builder", "reviewer"):
        per_risk = models.get(key)
        if not isinstance(per_risk, dict):
            raise _fail(f"'models.{key}' must be an object keyed by risk")
        for risk in RISKS:
            if not isinstance(per_risk.get(risk), str):
                raise _fail(f"'models.{key}.{risk}' must be a string")
    for key in ("always_human_surfaces", "protected_paths"):
        if not all(isinstance(v, str) for v in data[key]):
            raise _fail(f"'{key}' must be a list of strings")
    for key, (typ, _default) in OPTIONAL.items():
        if key in data and not isinstance(data[key], typ):
            raise _fail(f"'{key}' must be {typ.__name__}, got {type(data[key]).__name__}")
    history = str(data.get("history_dir", ""))
    if history.startswith("/") or ".." in Path(history).parts:
        raise _fail("'history_dir' must be a path inside the repository")


def load(root: Path | None = None) -> Config:
    root = root or find_root()
    path = root / "factory" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"{path} not found") from exc
    except json.JSONDecodeError as exc:
        raise _fail(f"invalid JSON: {exc}") from exc
    validate(data)
    for key, (_typ, default) in OPTIONAL.items():
        data.setdefault(key, default)
    return Config(root=root, data=data)
