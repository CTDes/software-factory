"""All git access goes through here. Remote effects (push, delete) live only in this module."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from lib.util import CommandError, run

REMOTE = "origin"


def git(cwd: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=cwd, check=check).stdout


def common_dir(cwd: Path) -> Path:
    out = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    return Path(out).resolve()


def fetch(root: Path, *refs: str) -> None:
    git(root, "fetch", "--quiet", "--prune", REMOTE, *refs)


def remote_ref(branch: str) -> str:
    return f"{REMOTE}/{branch}"


def rev_parse(cwd: Path, ref: str) -> str | None:
    proc = run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=cwd, check=False
    )
    return proc.stdout.strip() or None


def branch_exists(root: Path, branch: str) -> bool:
    return rev_parse(root, f"refs/heads/{branch}") is not None


def current_branch(cwd: Path) -> str:
    return git(cwd, "branch", "--show-current").strip()


def show_file(root: Path, ref: str, path: str) -> str:
    return git(root, "show", f"{ref}:{path}")


# ---------------------------------------------------------------- worktrees


def worktree_add(root: Path, path: Path, branch: str, start: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(root, branch):
        git(root, "worktree", "add", "--quiet", str(path), branch)
    else:
        git(root, "worktree", "add", "--quiet", "--no-track", "-b", branch, str(path), start)


def worktree_remove(root: Path, path: Path) -> None:
    if path.exists():
        git(root, "worktree", "remove", "--force", str(path))
    git(root, "worktree", "prune")


def delete_local_branch(root: Path, branch: str) -> None:
    if branch_exists(root, branch):
        git(root, "branch", "-D", branch)


def copy_worktreeinclude(root: Path, worktree: Path) -> list[str]:
    """Copy untracked/ignored files matching .worktreeinclude from the main checkout."""
    include = root / ".worktreeinclude"
    if not include.exists():
        return []
    out = git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        f"--exclude-from={include}",
    )
    copied = []
    for rel in filter(None, out.splitlines()):
        if rel.endswith("/") or not (root / rel).is_file():
            continue
        dst = worktree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
        copied.append(rel)
    return copied


# ---------------------------------------------------------------- state of a worktree


def is_clean(cwd: Path) -> bool:
    return git(cwd, "status", "--porcelain").strip() == ""


def commits_ahead(cwd: Path, base_ref: str) -> int:
    return int(git(cwd, "rev-list", "--count", f"{base_ref}..HEAD").strip())


def merge_base(cwd: Path, a: str, b: str = "HEAD") -> str:
    return git(cwd, "merge-base", a, b).strip()


@dataclass(frozen=True)
class Change:
    status: str  # A, M, D, R, C, T
    path: str
    old_path: str | None = None


def diff_changes(cwd: Path, base: str, head: str = "HEAD") -> list[Change]:
    out = git(cwd, "diff", "--name-status", "-M", "-z", base, head)
    parts = out.split("\0")
    changes: list[Change] = []
    i = 0
    while i < len(parts) and parts[i]:
        status = parts[i][0]
        if status in ("R", "C"):
            changes.append(Change(status, parts[i + 2], parts[i + 1]))
            i += 3
        else:
            changes.append(Change(status, parts[i + 1]))
            i += 2
    return changes


@dataclass(frozen=True)
class MergeResult:
    ok: bool
    conflicts: list[str]
    output: str


def merge(cwd: Path, ref: str) -> MergeResult:
    """Merge ref into the current branch; on conflict, list files and abort."""
    proc = run(["git", "merge", "--no-edit", "--no-ff", ref], cwd=cwd, check=False)
    if proc.returncode == 0:
        return MergeResult(True, [], proc.stdout)
    conflicts = git(cwd, "diff", "--name-only", "--diff-filter=U").split()
    run(["git", "merge", "--abort"], cwd=cwd, check=False)
    return MergeResult(False, conflicts, proc.stdout + proc.stderr)


# ---------------------------------------------------------------- remote effects


def push_branch(cwd: Path, branch: str) -> None:
    """Push the job branch; --force-with-lease so rewritten history is allowed but races are not."""
    git(cwd, "push", "--quiet", "--force-with-lease", REMOTE, f"HEAD:refs/heads/{branch}")


def push_fast_forward(cwd: Path, target_branch: str) -> None:
    """Push HEAD to another remote branch. No force: git rejects anything but a fast-forward."""
    git(cwd, "push", "--quiet", REMOTE, f"HEAD:refs/heads/{target_branch}")


def push_new_branch(root: Path, start: str, branch: str) -> None:
    git(root, "push", "--quiet", REMOTE, f"{start}:refs/heads/{branch}")


def delete_remote_branch(root: Path, branch: str) -> None:
    try:
        git(root, "push", "--quiet", REMOTE, "--delete", branch)
    except CommandError as exc:
        if "remote ref does not exist" not in (exc.stderr + exc.stdout):
            raise
