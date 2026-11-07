"""Job history: one markdown file per job, committed into the job's own branch.

When a job reaches a human (`ready`) or is about to merge into its spec (`merging`), factory-job
renders everything the job folder knows (issue, plan, every round, human feedback, timeline) into
`<history_dir>/<job-id>.md` and commits it to the job branch. After the merge the history lives in
git next to the code it explains, so nothing worth reading depends on factory/jobs/ (gitignored)
or on any server. `factory-job history` writes the same file into the main checkout for jobs that
finished before this existed (backfill).

External text (issue body, comments) goes inside fenced blocks so it renders as text, never as
markdown or HTML. Agent files are included with their headings demoted under the round they belong to.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lib import git
from lib import issue as issue_md
from lib.config import Config
from lib.jobs import Job, all_jobs
from lib.util import atomic_write

# (time, from, to, reason): a transition being applied, not yet in events.log
Event = tuple[str, str, str, str]

COMMIT_PREFIX = "docs(history):"


def history_rel(cfg: Config, job: Job) -> str | None:
    """Repository-relative path of the job's history file, or None when history is off."""
    folder = str(cfg.data.get("history_dir", "")).strip("/")
    return f"{folder}/{job.id}.md" if folder else None


# ---------------------------------------------------------------- rendering helpers


def fence(text: str, lang: str = "text") -> str:
    """A code fence longer than any backtick run inside text, so text cannot close it early."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text.rstrip()}\n{ticks}"


def demote(text: str, levels: int) -> str:
    """Push every markdown heading down `levels` levels (outside code fences)."""
    out, in_fence = [], False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^#{1,6}\s", line):
            line = "#" * levels + line
        out.append(line)
    return "\n".join(out)


def _header_and_body(text: str) -> tuple[list[tuple[str, str]], str]:
    """Split an agent file into its KEY: value header lines and the rest."""
    lines = text.splitlines()
    header: list[tuple[str, str]] = []
    i = 0
    while i < len(lines) and (m := re.match(r"^([A-Z][A-Z-]*):\s*(.*)$", lines[i])):
        header.append((m.group(1), m.group(2)))
        i += 1
    return header, "\n".join(lines[i:]).strip()


def _agent_file(path: Path, levels: int, first_section_only: bool = False) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    header, body = _header_and_body(text)
    if first_section_only:
        sections = re.split(r"(?m)^## ", body)
        body = ("## " + sections[1]).strip() if len(sections) > 1 else ""
    parts = [" · ".join(f"**{k}:** {v}" for k, v in header)] if header else []
    if body:
        parts.append(demote(body, levels))
    return "\n\n".join(parts)


def _issue_data(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    # the delimiters on a line of their own (the warning above them names them inline)
    m = re.search(rf"(?ms)^{re.escape(issue_md.OPEN)}$(.*)^{re.escape(issue_md.CLOSE)}$", text)
    return (m.group(1) if m else text).strip()


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _events(job: Job, pending: Event | None) -> list[Event]:
    events: list[Event] = []
    log = job.file("events.log")
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                events.append((parts[0], parts[1], parts[2], parts[3]))
    if pending:
        events.append(pending)
    return events


def _round_numbers(job: Job) -> list[int]:
    found = {
        int(m.group(1))
        for p in job.dir.glob("round-*")
        if (m := re.fullmatch(r"round-(\d+)", p.name))
    }
    return sorted(found | ({int(job["round"])} if int(job["round"] or 0) > 0 else set()))


def _yaml(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------- render


def render(job: Job, pending: Event | None = None) -> str:
    """The history file. `pending` is the transition being applied (not yet logged)."""
    events = _events(job, pending)
    stage = pending[2] if pending else job.stage
    surfaces = job.get("surfaces") or []
    front = {
        "job": job.id,
        "kind": job["kind"],
        "issue": job["issue"],
        "title": job["title"],
        "spec": job.get("spec"),
        "pr": job.get("pr"),
        "stage": stage,
        "risk": job.get("risk"),
        "surfaces": surfaces,
        "rounds": job["round"],
        "created": job.get("created_at"),
        "updated": events[-1][0] if events else job.get("updated_at"),
    }
    out = ["---"]
    out += [f"{k}: {_yaml(v)}" for k, v in front.items() if v is not None]
    out += ["---", "", f"# #{job['issue']} {job['title']}", ""]
    facts = [f"`{job.id}`", job["kind"], f"stage {stage}"]
    if job.get("risk"):
        facts.append(f"risk {job['risk']}")
    facts.append(f"surfaces {', '.join(surfaces) or 'none'}")
    facts.append(f"{job['round']} round{'s' if job['round'] != 1 else ''}")
    if job.get("pr"):
        facts.append(f"PR #{job['pr']}")
    if job.get("spec"):
        facts.append(f"spec [{job['spec']}]({job['spec']}.md)")
    out += [" · ".join(facts), ""]

    if job["kind"] == "spec":
        out += ["## Tickets", ""]
        tickets = sorted(
            (t for t in all_jobs(job.cfg) if t.get("spec") == job.id), key=lambda t: t["issue"]
        )
        out += [
            f"- [#{t['issue']} {t['title']}]({t.id}.md) · {t.stage} · {t['round']} rounds"
            for t in tickets
        ] or ["- none"]
        out.append("")

    if job.file("issue.md").exists():
        out += ["## Issue", "", fence(_issue_data(job.file("issue.md"))), ""]

    questions = sorted(job.dir.glob("plan.needs-info-*.md"))
    if questions or job.file("plan.md").exists():
        out += ["## Plan", ""]
        for i, q in enumerate(questions, start=1):
            out += [f"### Question {i}", "", _agent_file(q, 2), ""]
        if job.file("plan.md").exists():
            out += [_agent_file(job.file("plan.md"), 1), ""]

    for n in _round_numbers(job):
        rd = job.round_dir(n)
        build = rd / "build.md"
        if not build.exists() and n == job["round"]:
            build = job.file("build.md")
        parts = [
            ("Build", build, False),
            ("Gate", rd / "checks.md", True),
            ("Review", rd / "review.md", False),
            ("Merge", rd / "merge.md", True),
        ]
        present = [(title, p, first) for title, p, first in parts if p.exists()]
        if not present:
            continue
        out += [f"## Round {n}", ""]
        for title, p, first in present:
            out += [f"### {title}", "", _agent_file(p, 2, first_section_only=first), ""]

    reworks = sorted(job.dir.glob("rework-*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if reworks:
        out += ["## Human feedback", ""]
        for p in reworks:
            out += [f"### {p.stem}", "", fence(p.read_text(encoding="utf-8", errors="replace")), ""]

    out += ["## Timeline", "", "| Time | From | To | Reason |", "| --- | --- | --- | --- |"]
    out += [f"| {ts} | {frm} | {to} | {_cell(why)} |" for ts, frm, to, why in events]
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- write / commit


def commit(cfg: Config, job: Job, worktree: Path, pending: Event | None) -> bool:
    """Write the history file into the worktree and commit it alone. False if nothing changed."""
    rel = history_rel(cfg, job)
    if rel is None:
        return False
    atomic_write(worktree / rel, render(job, pending))
    if not git.git(worktree, "status", "--porcelain", "--", rel).strip():
        return False
    git.git(worktree, "add", "--", rel)
    git.git(worktree, "commit", "--quiet", "-m", f"{COMMIT_PREFIX} {job.id}", "--", rel)
    return True


def write(cfg: Config, job: Job) -> Path | None:
    """Backfill: write the history file into the main checkout, uncommitted."""
    rel = history_rel(cfg, job)
    if rel is None:
        return None
    path = cfg.root / rel
    atomic_write(path, render(job))
    return path
