"""Publish the project wiki to the linked factory-office (DESIGN.md · Wiki publishing).

The office builds and serves the site; this side only sends the vault (`lib/vault.py`) as a
gzipped tar to ``POST <office>/wiki?repo=<owner/name>`` with the same bearer token as events.
It goes wherever events go (``FACTORY_EVENTS_URL`` or ``link.json``), so CI and local
machines publish the same way.

Every transition marks the wiki dirty. The automatic publish at the end of each factory-job
command sends it at once when a job reached a state a human looks at (URGENT), and otherwise at
most once every THROTTLE_S. Like events, it never raises and backs off after a failure.

Files under ``factory/jobs/_events/``:
  wiki-dirty      exists while the office's copy is stale; its text is "urgent" or "normal"
  wiki-published  timestamp of the last successful publish
  wiki-backoff    timestamp of the last failed automatic publish
"""

from __future__ import annotations

import io
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from lib import events, vault
from lib.config import Config
from lib.github import GitHub
from lib.util import atomic_write

URGENT = frozenset({"ready", "done", "needs-human", "needs-info", "rejected"})
THROTTLE_S = 120.0
BACKOFF_S = 60.0
TIMEOUT_S = 15.0


def _file(cfg: Config, name: str) -> Path:
    return cfg.jobs_dir / "_events" / name


def _stamp(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def mark_dirty(cfg: Config, to: str) -> None:
    """Called for every transition. Never raises."""
    try:
        if events.sink(cfg) is None:
            return
        path = _file(cfg, "wiki-dirty")
        level = "urgent" if to in URGENT else "normal"
        if level == "normal" and path.exists():
            return  # never downgrade an urgent mark
        atomic_write(path, level + "\n")
    except Exception:
        pass


def is_dirty(cfg: Config) -> str | None:
    try:
        return _file(cfg, "wiki-dirty").read_text(encoding="utf-8").strip() or "normal"
    except OSError:
        return None


def endpoint(target: events.Sink, repo: str) -> str:
    return f"{events.office_base(target.url)}/wiki?repo={urllib.parse.quote(repo, safe='')}"


def pack(folder: Path) -> bytes:
    """The vault as tar.gz: regular files only, relative paths, no owners or modes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(path.relative_to(folder).as_posix())
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@dataclass
class PublishResult:
    notes: int = 0
    bytes: int = 0
    url: str | None = None
    error: str | None = None
    skipped: str | None = None

    def line(self) -> str:
        if self.skipped:
            return f"wiki: skipped ({self.skipped})"
        if self.error:
            return f"wiki: error: {self.error}"
        return f"wiki: sent {self.notes} notes ({self.bytes // 1024} KiB) to {self.url}"


def _post(url: str, token: str | None, body: bytes) -> None:
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/gzip")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        if not 200 <= resp.status < 300:
            raise urllib.error.HTTPError(url, resp.status, "unexpected status", resp.headers, None)


def publish(cfg: Config, gh: GitHub, automatic: bool = False) -> PublishResult:
    """Build the vault and send it. Automatic: only when dirty, throttled, never raises."""
    result = PublishResult()
    target = events.sink(cfg)
    if target is None:
        result.skipped = "not linked to an office"
        return result
    level = is_dirty(cfg)
    if automatic:
        now_s = time.time()
        if level is None:
            result.skipped = "nothing changed"
            return result
        backoff = _stamp(_file(cfg, "wiki-backoff"))
        if backoff is not None and now_s - backoff < BACKOFF_S:
            result.skipped = "backoff after a failed publish"
            return result
        last = _stamp(_file(cfg, "wiki-published"))
        if level != "urgent" and last is not None and now_s - last < THROTTLE_S:
            result.skipped = "throttled"
            return result
    repo = events.repo_name(cfg.root)
    result.url = endpoint(target, repo)
    try:
        # Clear the mark first: a transition during the build marks it again and is not lost.
        _file(cfg, "wiki-dirty").unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="factory-vault-") as tmp:
            out = Path(tmp) / "vault"
            notes = vault.build(cfg, gh.all_issues(), gh.all_prs(), out, title=repo)
            body = pack(out)
        result.notes, result.bytes = len(notes), len(body)
        _post(result.url, target.token, body)
    except Exception as exc:
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
        result.error = f"{type(exc).__name__}: {exc}"
        try:
            if level is not None and not _file(cfg, "wiki-dirty").exists():
                atomic_write(_file(cfg, "wiki-dirty"), level + "\n")
            if automatic:
                atomic_write(_file(cfg, "wiki-backoff"), f"{time.time()}\n")
        except OSError:
            pass
        return result
    atomic_write(_file(cfg, "wiki-published"), f"{time.time()}\n")
    _file(cfg, "wiki-backoff").unlink(missing_ok=True)
    return result


def status_line(cfg: Config) -> str:
    last = _stamp(_file(cfg, "wiki-published"))
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last)) if last else "never"
    state = is_dirty(cfg)
    return f"wiki       published {when}" + (f", pending ({state})" if state else "")
