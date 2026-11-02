"""bin/gate: run checks.sh from origin/<base_branch>, check protected paths and evidence."""

from __future__ import annotations

import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lib import contracts, git
from lib.config import Config
from lib.jobs import Job
from lib.util import FactoryError, atomic_write, matches_any, run_with_timeout


@dataclass
class GateResult:
    passed: bool
    returncode: int
    duration_s: float
    command: str
    checks_ref: str
    protected: list[str] = field(default_factory=list)
    evidence_problems: list[str] = field(default_factory=list)
    log_tail: str = ""
    timed_out: bool = False


def protected_touched(cfg: Config, changes: list[git.Change]) -> list[str]:
    """Modified, deleted, type-changed or renamed-away files that match protected_paths."""
    patterns = cfg["protected_paths"]
    hits: list[str] = []
    for ch in changes:
        if ch.status in ("M", "D", "T") and matches_any(ch.path, patterns):
            hits.append(ch.path)
        elif ch.status == "R" and ch.old_path and matches_any(ch.old_path, patterns):
            hits.append(f"{ch.old_path} -> {ch.path}")
    return sorted(set(hits))


def check_evidence(job: Job, worktree: Path) -> list[str]:
    """Every `path::name` in build.md must exist; every plan criterion must have evidence."""
    problems: list[str] = []
    try:
        build = contracts.read_build(job.file("build.md"))
    except contracts.ContractError as exc:
        return [str(exc)]
    if build["STATUS"] != "READY":
        return ["build.md: STATUS is not READY"]
    evidence, malformed = contracts.parse_evidence(build.section("Evidence"))
    problems += [f"malformed evidence line: {line!r}" for line in malformed]
    if not evidence:
        problems.append("build.md: '## Evidence' lists no evidence")
    root = worktree.resolve()
    for ev in evidence:
        label = f"{ev.criterion}: {ev.path}::{ev.name}"
        target = (worktree / ev.path).resolve()
        if Path(ev.path).is_absolute() or root not in target.parents:
            problems.append(f"{label} — path must be relative to the worktree")
            continue
        if not target.is_file():
            problems.append(f"{label} — file not found")
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        if not re.search(rf"(?<![\w]){re.escape(ev.name)}(?![\w])", text):
            problems.append(f"{label} — '{ev.name}' does not appear in {ev.path}")
    plan_path = job.file("plan.md")
    if plan_path.exists():
        try:
            plan = contracts.read_plan(plan_path)
            wanted = contracts.criteria_ids(plan.section("Acceptance criteria"))
        except contracts.ContractError:
            wanted = []
        covered = {ev.criterion for ev in evidence}
        problems += [
            f"{c} — no evidence for this plan criterion" for c in wanted if c not in covered
        ]
    return problems


def run_gate(
    cfg: Config, job: Job, final: bool = False, out_path: Path | None = None
) -> GateResult:
    root, worktree = cfg.root, job.worktree
    if not worktree.is_dir():
        raise FactoryError(f"{job.id}: worktree {worktree} does not exist")
    base_branch = cfg["base_branch"]
    diff_base_branch = base_branch if final else job["base"]
    git.fetch(root)
    checks_ref = git.remote_ref(base_branch)
    try:
        script = git.show_file(root, checks_ref, "factory/checks.sh")
    except Exception as exc:
        raise FactoryError(f"cannot read factory/checks.sh from {checks_ref}: {exc}") from exc
    checks_sha = (git.rev_parse(root, checks_ref) or "?")[:12]

    with tempfile.TemporaryDirectory(prefix="factory-gate-") as tmp:
        path = Path(tmp) / "checks.sh"
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        result = run_with_timeout([str(path)], cwd=worktree, timeout_s=cfg["checks_timeout_s"])

    base_sha = git.merge_base(worktree, git.remote_ref(diff_base_branch))
    protected = protected_touched(cfg, git.diff_changes(worktree, base_sha))
    evidence = [] if final and not job.file("build.md").exists() else check_evidence(job, worktree)

    tail = "\n".join(result.output.rstrip("\n").splitlines()[-cfg["log_tail_lines"] :])
    gate = GateResult(
        passed=result.returncode == 0 and not protected and not evidence,
        returncode=result.returncode,
        duration_s=result.duration_s,
        command=f"factory/checks.sh from {checks_ref} @ {checks_sha}, cwd {worktree}",
        checks_ref=checks_ref,
        protected=protected,
        evidence_problems=evidence,
        log_tail=tail,
        timed_out=result.timed_out,
    )
    out = out_path or job.round_dir() / "checks.md"
    atomic_write(
        out,
        render(
            gate, diff_base=f"merge-base with {git.remote_ref(diff_base_branch)} ({base_sha[:12]})"
        ),
    )
    return gate


def render(g: GateResult, diff_base: str) -> str:
    lines = [
        f"GATE: {'PASS' if g.passed else 'FAIL'}",
        f"PROTECTED: {', '.join(g.protected) if g.protected else 'none'}",
        "",
        "## Summary",
        "",
        f"- checks.sh: {'OK' if g.returncode == 0 else f'FAILED (exit {g.returncode})'}"
        + (" — TIMEOUT" if g.timed_out else ""),
        f"- Protected paths modified or deleted: {len(g.protected)}",
        f"- Evidence problems: {len(g.evidence_problems)}",
        "",
        "## Command",
        "",
        f"- {g.command}",
        f"- Duration: {g.duration_s:.1f}s",
        f"- Diff against: {diff_base}",
        "",
        "## Protected paths",
        "",
    ]
    lines += [f"- {p}" for p in g.protected] or ["- none"]
    lines += ["", "## Missing evidence", ""]
    lines += [f"- {p}" for p in g.evidence_problems] or ["- none"]
    lines += ["", "## Log (tail)", "", "```text", g.log_tail, "```", ""]
    return "\n".join(lines)
