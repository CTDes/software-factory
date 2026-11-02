"""Optional event emitter (DESIGN.md · Events).

Every transition that ``Job.log_event`` writes to ``events.log`` can also be sent to a collector
such as factory-office. Nothing here is required: with ``FACTORY_EVENTS_URL`` unset the factory
behaves exactly as before, and with it set a collector that is down never blocks or fails a
command. Events wait in a local outbox until a flush delivers them.

Files, all under ``factory/jobs/_events/``:
  outbox.jsonl   one event per line, oldest first
  outbox.lock    held while the outbox is appended to or rewritten
  flush.lock     held by the one process that is flushing
  backoff        timestamp of the last failed automatic flush
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from lib.config import Config
from lib.util import FactoryError, atomic_write, run

SCHEMA = 1
URL_ENV = "FACTORY_EVENTS_URL"
TOKEN_ENV = "FACTORY_EVENTS_TOKEN"
MACHINE_ENV = "FACTORY_EVENTS_MACHINE"
BATCH = 200
TIMEOUT_S = 3.0
BACKOFF_S = 60.0


# ---------------------------------------------------------------- settings


@dataclass(frozen=True)
class Sink:
    url: str
    token: str | None


def sink() -> Sink | None:
    """The configured collector, or None when events are off."""
    url = os.environ.get(URL_ENV, "").strip()
    if not url:
        return None
    return Sink(url=url, token=os.environ.get(TOKEN_ENV, "").strip() or None)


def machine_name() -> str:
    return os.environ.get(MACHINE_ENV, "").strip() or socket.gethostname()


_REMOTE_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")


def repo_from_remote(url: str) -> str | None:
    """'owner/name' from an https, ssh or scp-style remote URL (ssh host aliases included)."""
    m = _REMOTE_RE.search(url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


@cache
def repo_name(root: Path) -> str:
    """The repo as the collector knows it: origin's 'owner/name', else the folder name."""
    try:
        url = run(["git", "remote", "get-url", "origin"], cwd=root).stdout
    except (FactoryError, OSError):
        return root.name
    return repo_from_remote(url) or root.name


# ---------------------------------------------------------------- events


def event_id(repo: str, job: str, ts: str, frm: str, to: str, reason: str) -> str:
    """Deterministic, so a live event and its backfilled copy are the same event."""
    raw = "\x1f".join((repo, job, ts, frm, to, reason))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def make_event(
    repo: str,
    machine: str,
    ts: str,
    frm: str,
    to: str,
    reason: str,
    job: dict[str, Any],
    snapshot: bool = True,
) -> dict[str, Any]:
    """An event of schema 1. ``job`` is the job.json snapshot after the transition, or None."""
    jid = str(job["id"])
    return {
        "schema": SCHEMA,
        "id": event_id(repo, jid, ts, frm, to, reason),
        "repo": repo,
        "machine": machine,
        "job_id": jid,
        "kind": job.get("kind"),
        "issue": job.get("issue"),
        "spec": job.get("spec"),
        "ts": ts,
        "from": frm,
        "to": to,
        "reason": reason,
        "job": dict(job, updated_at=ts) if snapshot else None,
    }


# ---------------------------------------------------------------- outbox


def _dir(cfg: Config) -> Path:
    return cfg.jobs_dir / "_events"


def outbox_path(cfg: Config) -> Path:
    return _dir(cfg) / "outbox.jsonl"


@contextmanager
def _lock(path: Path, blocking: bool = True) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def append(cfg: Config, events: Sequence[dict[str, Any]]) -> None:
    if not events:
        return
    lines = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
    with _lock(_dir(cfg) / "outbox.lock"):
        with outbox_path(cfg).open("a", encoding="utf-8") as fh:
            fh.write(lines)


def pending(cfg: Config) -> int:
    path = outbox_path(cfg)
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def record(cfg: Config, job: dict[str, Any], ts: str, frm: str, to: str, reason: str) -> None:
    """Queue the event for a transition. Never raises: events must not break the factory."""
    if sink() is None:
        return
    try:
        append(cfg, [make_event(repo_name(cfg.root), machine_name(), ts, frm, to, reason, job)])
    except Exception:
        pass


# ---------------------------------------------------------------- delivery


@dataclass
class FlushResult:
    sent: int = 0
    pending: int = 0
    dropped: int = 0
    error: str | None = None
    skipped: str | None = None


def _post(target: Sink, batch: list[dict[str, Any]]) -> None:
    body = json.dumps({"events": batch}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(target.url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if target.token:
        req.add_header("Authorization", f"Bearer {target.token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        if not 200 <= resp.status < 300:
            raise urllib.error.HTTPError(
                target.url, resp.status, "unexpected status", resp.headers, None
            )


def _backoff_active(cfg: Config) -> bool:
    try:
        last = float((_dir(cfg) / "backoff").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return time.time() - last < BACKOFF_S


def flush(cfg: Config, automatic: bool = False) -> FlushResult:
    """Send the outbox to the collector, oldest first, and drop what it accepted.

    Only one process flushes at a time; the others return at once. An automatic flush (the one
    at the end of every factory-job command) is skipped for BACKOFF_S after a failure, so a
    collector that is down costs at most one timeout per minute. Never raises.
    """
    result = FlushResult()
    target = sink()
    if target is None:
        result.skipped = f"{URL_ENV} is not set"
        result.pending = pending(cfg)
        return result
    if not outbox_path(cfg).exists():
        return result
    if automatic and _backoff_active(cfg):
        result.skipped = "backoff after a failed flush"
        result.pending = pending(cfg)
        return result
    try:
        with _lock(_dir(cfg) / "flush.lock", blocking=False) as got:
            if not got:
                result.skipped = "another process is flushing"
                result.pending = pending(cfg)
                return result
            _deliver(cfg, target, result)
    except Exception as exc:
        result.error = result.error or f"{type(exc).__name__}: {exc}"
    if result.error:
        try:
            atomic_write(_dir(cfg) / "backoff", f"{time.time()}\n")
        except OSError:
            pass
    else:
        (_dir(cfg) / "backoff").unlink(missing_ok=True)
    result.pending = pending(cfg)
    return result


def _parse(line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _cut(lines: list[str], sent: int) -> int:
    """How many leading raw lines to drop once ``sent`` events were accepted.

    Blank or malformed lines before the first unsent event go too.
    """
    valid = 0
    for i, line in enumerate(lines):
        if _parse(line) is not None:
            if valid == sent:
                return i
            valid += 1
    return len(lines)


def _deliver(cfg: Config, target: Sink, result: FlushResult) -> None:
    lines = outbox_path(cfg).read_text(encoding="utf-8").splitlines()
    events = [e for e in map(_parse, lines) if e is not None]
    result.dropped = sum(1 for line in lines if line.strip()) - len(events)
    try:
        for start in range(0, len(events), BATCH):
            batch = events[start : start + BATCH]
            _post(target, batch)
            result.sent += len(batch)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
    # Only flushers remove lines and only one flushes at a time, so the lines read above are
    # still the first ones in the file; anything appended meanwhile is kept.
    cut = _cut(lines, result.sent)
    with _lock(_dir(cfg) / "outbox.lock"):
        current = outbox_path(cfg).read_text(encoding="utf-8").splitlines()
        atomic_write(outbox_path(cfg), "".join(f"{line}\n" for line in current[cut:]))


# ---------------------------------------------------------------- backfill


def parse_log_line(line: str) -> tuple[str, str, str, str] | None:
    parts = line.rstrip("\n").split("\t", 3)
    if len(parts) != 4 or not parts[0]:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def backfill(cfg: Config, jobs: Sequence[dict[str, Any]]) -> int:
    """Queue every line of every job's events.log. Returns how many events were queued.

    Ids match the live events, so the collector drops the copies it already has. Only the last
    event of each job carries the job.json snapshot: the older ones never had it.
    """
    if sink() is None:
        raise FactoryError(f"backfill needs {URL_ENV}: set it to the collector's events URL")
    repo, machine = repo_name(cfg.root), machine_name()
    queued: list[dict[str, Any]] = []
    for job in jobs:
        log = cfg.jobs_dir / str(job["id"]) / "events.log"
        if not log.exists():
            continue
        rows = [r for r in map(parse_log_line, log.read_text(encoding="utf-8").splitlines()) if r]
        for i, (ts, frm, to, reason) in enumerate(rows):
            queued.append(
                make_event(repo, machine, ts, frm, to, reason, job, snapshot=i == len(rows) - 1)
            )
    append(cfg, queued)
    return len(queued)
