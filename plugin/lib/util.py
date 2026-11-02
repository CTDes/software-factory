"""Small helpers: errors, time, slugs, globs, atomic writes, subprocess."""

from __future__ import annotations

import datetime as dt
import os
import re
import signal
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Exit codes (DESIGN.md · factory-job and factory-gate)
EXIT_OK = 0
EXIT_CONDITION = 1  # condition not met / illegal transition / effect failed
EXIT_USAGE = 2  # usage or configuration error


class FactoryError(Exception):
    """An error that maps to an exit code and is shown to the user verbatim."""

    code = EXIT_CONDITION


class UsageError(FactoryError):
    code = EXIT_USAGE


class ConfigError(FactoryError):
    code = EXIT_USAGE


class CommandError(FactoryError):
    """An external command (git, gh) failed. The message carries its full output."""

    def __init__(self, args: Sequence[str], returncode: int, stdout: str, stderr: str) -> None:
        self.args_list = list(args)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        out = "\n".join(s for s in (stdout.strip(), stderr.strip()) if s)
        super().__init__(f"command failed ({returncode}): {' '.join(args)}\n{out}")


# ---------------------------------------------------------------- time


def now() -> str:
    """Local time, ISO 8601 with offset, second precision."""
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_ts(value: str) -> dt.datetime:
    """Parse ISO timestamps, including GitHub's trailing 'Z' (3.10 compatible)."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def is_after(a: str, b: str | None) -> bool:
    """True if timestamp a is strictly after b (any a is after a missing b)."""
    return b is None or parse_ts(a) > parse_ts(b)


# ---------------------------------------------------------------- slugs and globs


def slugify(text: str, max_length: int = 40) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "issue"


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob: ``**`` crosses directories, ``*`` and ``?`` do not."""
    i, out = 0, []
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


# ---------------------------------------------------------------- files


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- subprocess


def run(
    args: Sequence[str],
    cwd: Path | str | None = None,
    input_text: str | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if check and proc.returncode != 0:
        raise CommandError(args, proc.returncode, proc.stdout, proc.stderr)
    return proc


@dataclass
class TimedResult:
    returncode: int
    output: str
    duration_s: float
    timed_out: bool


def run_with_timeout(args: Sequence[str], cwd: Path, timeout_s: int) -> TimedResult:
    """Run a command, merging stdout and stderr; kill its whole process group on timeout."""
    start = time.monotonic()
    proc = subprocess.Popen(
        list(args),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
        output += f"\n[factory] TIMEOUT: killed after {timeout_s}s\n"
        timed_out = True
    return TimedResult(
        returncode=proc.returncode if not timed_out else 124,
        output=output or "",
        duration_s=time.monotonic() - start,
        timed_out=timed_out,
    )
