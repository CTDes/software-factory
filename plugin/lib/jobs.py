"""Job folders under factory/jobs/<id>/: job.json, events.log, round-N/ ... Only bin/job writes job.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import events
from lib.config import Config
from lib.util import FactoryError, atomic_write, now, slugify

TICKET_STAGES = (
    "intake",
    "needs-info",
    "rejected",
    "build",
    "gate",
    "review",
    "merging",
    "ready",
    "needs-human",
    "done",
)
TERMINAL = ("rejected", "done")


def job_id(issue: int, title: str) -> str:
    return f"{issue:03d}-{slugify(title, 40)}"


class Job:
    """A job folder. Behaves like the job.json dict plus path helpers."""

    def __init__(self, cfg: Config, data: dict[str, Any]) -> None:
        self.cfg = cfg
        self.data = data

    # -- dict-like access

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def stage(self) -> str:
        return str(self.data["stage"])

    # -- paths

    @property
    def dir(self) -> Path:
        return self.cfg.jobs_dir / self.id

    @property
    def worktree(self) -> Path:
        return self.cfg.root / str(self.data["worktree"])

    def file(self, name: str) -> Path:
        return self.dir / name

    def round_dir(self, n: int | None = None) -> Path:
        return self.dir / f"round-{self.data['round'] if n is None else n}"

    def next_rework_path(self) -> Path:
        nums = [
            int(m.group(1))
            for p in self.dir.glob("rework-*.md")
            if (m := re.search(r"(\d+)", p.name))
        ]
        return self.dir / f"rework-{max(nums, default=0) + 1}.md"

    # -- persistence

    def save(self) -> None:
        self.data["updated_at"] = now()
        atomic_write(
            self.file("job.json"), json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        )

    def log_event(self, frm: str, to: str, reason: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        reason = " ".join(reason.split())
        ts = now()
        with self.file("events.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{ts}\t{frm}\t{to}\t{reason}\n")
        events.record(self.cfg, self.data, ts, frm, to, reason)


def new_ticket(cfg: Config, issue: dict[str, Any], spec: Job | None = None) -> Job:
    jid = job_id(int(issue["number"]), str(issue["title"]))
    base = spec["branch"] if spec else cfg["base_branch"]
    data: dict[str, Any] = {
        "id": jid,
        "kind": "ticket",
        "issue": int(issue["number"]),
        "title": issue["title"],
        "spec": spec.id if spec else None,
        "blocked_by": [],
        "stage": "intake",
        "round": 0,
        "risk": None,
        "surfaces": [],
        "models": {},
        "base": base,
        "branch": f"{cfg['job_branch_prefix']}{jid}",
        "worktree": f"{cfg['worktrees_dir']}/{jid}",
        "pr": None,
        "agent": None,
        "reason": None,
        "claim": None,
        "feedback": None,
        "contract_failures": 0,
        "created_at": now(),
        "pushed_at": None,
        "asked_at": None,
        "updated_at": now(),
    }
    return Job(cfg, data)


def load(cfg: Config, jid: str) -> Job:
    path = cfg.jobs_dir / jid / "job.json"
    if not path.exists():
        raise FactoryError(f"no such job: {jid}")
    return Job(cfg, json.loads(path.read_text(encoding="utf-8")))


def all_jobs(cfg: Config) -> list[Job]:
    if not cfg.jobs_dir.exists():
        return []
    return [
        Job(cfg, json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(cfg.jobs_dir.glob("*/job.json"))
    ]


def by_issue(cfg: Config, issue: int) -> Job | None:
    for job in all_jobs(cfg):
        if job["issue"] == issue:
            return job
    return None


def resolve(cfg: Config, ref: str) -> Job:
    """Accept a job id, an issue number, or '#n'."""
    ref = ref.lstrip("#")
    if ref.isdigit():
        job = by_issue(cfg, int(ref))
        if not job:
            raise FactoryError(f"no job for issue #{ref}")
        return job
    return load(cfg, ref)
