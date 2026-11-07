"""The project wiki: a folder of linked markdown notes built from the repository and GitHub.

`factory-job vault <out>` writes it. The folder is at the same time an Obsidian vault and the
`content/` folder of a Quartz site (DESIGN.md · Wiki). It is a projection: everything in it comes
from the repository (docs/, GLOSSARY.md, docs/history/) and from a snapshot of GitHub issues and
PRs, so it can be thrown away and rebuilt at any time.

    index.md                 milestones, what is going on, documents, recent history
    board.md                 every spec and ticket grouped by status
    specs/<n>.md             a spec: status, milestone, ticket table, dependency graph, description
    tickets/<n>.md           a ticket: status, spec, blockers, PR, history, description
    history/<job-id>.md      the job records committed by factory-job
    docs/…, GLOSSARY.md      the repository's documents, same paths as in the repo

Text from GitHub (titles, bodies) and from agents (history) can contain HTML: every `<` outside
code is escaped, so it renders as text. Links are relative markdown links, so they work in
Quartz, Obsidian and on GitHub alike.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib import git
from lib import issue as issue_md
from lib.config import Config
from lib.github import Issue, PullSummary
from lib.util import FactoryError, now

MARKER = ".factory-vault"

# Status, in the order the board shows them.
# "done" is a closed issue with a merged PR or a job record; "closed" is any other closed one.
STATUSES = ("working", "needs human", "needs info", "queued", "open", "done", "closed")

MILESTONE_RE = re.compile(
    r"^###\s+(M\d+)\s*·\s*(.+?)\s*(?:—|--)\s*status:\s*(.+?)\s*$", re.MULTILINE
)


# ---------------------------------------------------------------- text helpers


def _outside_code(text: str, fn: Any) -> str:
    """Apply fn to the parts of markdown text outside fenced blocks and inline code."""
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            out.append(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        parts = re.split(r"(`+[^`]*?`+)", line)
        out.append("".join(p if i % 2 else fn(p) for i, p in enumerate(parts)))
    return "\n".join(out)


# A link target or reference definition that would run code when clicked.
_UNSAFE_URL = re.compile(r"(\]\(\s*|^\s*\[[^\]]*\]:\s*)(javascript|vbscript|data):", re.IGNORECASE)


def escape_html(text: str) -> str:
    """External text never becomes markup: `<` outside code becomes `&lt;` and link targets
    with a javascript:, vbscript: or data: scheme are defused."""

    def fn(s: str) -> str:
        s = s.replace("<", "&lt;")
        return _UNSAFE_URL.sub(lambda m: f"{m.group(1)}#unsafe-{m.group(2).lower()}-", s)

    return _outside_code(text, fn)


def inline(text: str) -> str:
    """A title for a heading, link text or table cell."""
    t = " ".join(str(text).split())
    for ch, rep in (("<", "&lt;"), ("[", "\\["), ("]", "\\]"), ("|", "\\|")):
        t = t.replace(ch, rep)
    return t


def _front(data: dict[str, Any]) -> str:
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items()]
    return "\n".join([*lines, "---", ""])


def _split_front(text: str) -> tuple[dict[str, Any], str]:
    """JSON-valued front matter, as factory-job writes it. Unknown values stay strings."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return {}, text
    data: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        try:
            data[key.strip()] = json.loads(value.strip())
        except json.JSONDecodeError:
            data[key.strip()] = value.strip()
    return data, text[m.end() :]


def rel_link(from_note: str, to_note: str, text: str) -> str:
    target = os.path.relpath(to_note, os.path.dirname(from_note) or ".")
    return f"[{text}]({target})"


# ---------------------------------------------------------------- model


@dataclass
class Item:
    """A spec or ticket issue, with everything the wiki says about it."""

    number: int
    title: str
    kind: str  # spec | ticket
    status: str
    url: str
    body: str
    parent: int | None = None
    blocked_by: list[int] = field(default_factory=list)
    pr: PullSummary | None = None
    history: str | None = None  # note path, e.g. history/012-x.md
    milestone: str | None = None

    @property
    def note(self) -> str:
        return f"{self.kind}s/{self.number}.md"

    @property
    def label(self) -> str:
        return f"#{self.number} {inline(self.title)}"


@dataclass
class Milestone:
    key: str
    title: str
    status: str
    spec: int | None
    pr: int | None


@dataclass
class Vault:
    cfg: Config
    title: str
    items: dict[int, Item]
    milestones: list[Milestone]
    histories: dict[str, dict[str, Any]]  # note path -> front matter
    docs: dict[str, Path]  # note path -> source file
    prs: dict[int, PullSummary]


def status_of(cfg: Config, issue: Issue) -> str:
    if issue.get("state") == "CLOSED":
        return "closed"
    labels = set(issue.get("labels") or [])
    for key, status in (
        ("needs_human", "needs human"),
        ("needs_info", "needs info"),
        ("in_progress", "working"),
        ("queue", "queued"),
    ):
        if cfg.label(key) in labels:
            return status
    return "open"


def parse_milestones(roadmap: str) -> list[Milestone]:
    out = []
    for m in MILESTONE_RE.finditer(roadmap):
        status_text = m.group(3)
        word = next(
            (w for w in ("in progress", "done", "planned") if w in status_text.lower()),
            status_text,
        )
        spec = re.search(r"spec\s+#(\d+)", status_text, re.IGNORECASE)
        pr = re.search(r"PR\s+#(\d+)", status_text, re.IGNORECASE)
        out.append(
            Milestone(
                m.group(1),
                m.group(2),
                word,
                int(spec.group(1)) if spec else None,
                int(pr.group(1)) if pr else None,
            )
        )
    return out


def _closes(body: str) -> list[int]:
    found = re.findall(
        r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)|\bTicket\s+#(\d+)\s+of\s+spec",
        body or "",
    )
    return [int(a or b) for a, b in found]


def collect(cfg: Config, issues: list[Issue], prs: list[PullSummary], title: str) -> Vault:
    root = cfg.root
    history_dir = str(cfg.data.get("history_dir") or "").strip("/")

    histories: dict[str, dict[str, Any]] = {}
    by_issue_history: dict[int, str] = {}
    if history_dir and (root / history_dir).is_dir():
        for p in sorted((root / history_dir).glob("*.md")):
            front, _ = _split_front(p.read_text(encoding="utf-8", errors="replace"))
            note = f"history/{p.name}"
            histories[note] = front
            if isinstance(front.get("issue"), int):
                by_issue_history[front["issue"]] = note

    docs: dict[str, Path] = {}
    if (root / "docs").is_dir():
        for p in sorted((root / "docs").rglob("*.md")):
            rel = p.relative_to(root).as_posix()
            if history_dir and (rel + "/").startswith(history_dir + "/"):
                continue
            docs[rel] = p
    for name in ("GLOSSARY.md", "README.md"):
        if (root / name).is_file():
            docs[name] = root / name

    roadmap = root / "docs" / "roadmap.md"
    milestones = parse_milestones(roadmap.read_text(encoding="utf-8")) if roadmap.exists() else []
    milestone_of_spec = {m.spec: m.key for m in milestones if m.spec}

    pr_by_number = {int(pr["number"]): pr for pr in prs}
    pr_for_issue: dict[int, PullSummary] = {}
    for pr in sorted(prs, key=lambda x: int(x["number"])):
        for n in _closes(pr.get("body", "")):
            pr_for_issue[n] = pr

    spec_label = cfg.label("spec")
    items: dict[int, Item] = {}
    for issue in issues:
        n = int(issue["number"])
        body = issue.get("body") or ""
        kind = "spec" if spec_label in (issue.get("labels") or []) else "ticket"
        hist = by_issue_history.get(n)
        linked: PullSummary | None = None
        if hist and isinstance(histories[hist].get("pr"), int):
            linked = pr_by_number.get(histories[hist]["pr"])
        linked = linked or pr_for_issue.get(n)
        status = status_of(cfg, issue)
        if status == "closed" and (hist or (linked and linked["state"] == "MERGED")):
            status = "done"
        items[n] = Item(
            number=n,
            title=str(issue["title"]),
            kind=kind,
            status=status,
            url=str(issue.get("url") or ""),
            body=body,
            parent=issue_md.parent_of(body),
            blocked_by=issue_md.blocked_by(body),
            pr=linked,
            history=hist,
            milestone=milestone_of_spec.get(n) if kind == "spec" else None,
        )
    return Vault(cfg, title, items, milestones, histories, docs, pr_by_number)


# ---------------------------------------------------------------- rendering


def _linkify(v: Vault, note: str, text: str) -> str:
    """#123 outside code becomes a link to that spec or ticket note, when the wiki has it."""

    def fn(s: str) -> str:
        def rep(m: re.Match[str]) -> str:
            item = v.items.get(int(m.group(2)))
            if not item:
                return m.group(0)
            return m.group(1) + rel_link(note, item.note, f"#{item.number}")

        return re.sub(r"(^|[\s(,;:])#(\d+)\b", rep, s)

    return _outside_code(text, fn)


def _external(v: Vault, note: str, text: str) -> str:
    return _linkify(v, note, escape_html(text.strip() or "_(empty)_"))


def _pr_cell(pr: PullSummary | None) -> str:
    if not pr:
        return "-"
    state = "draft" if pr.get("draft") and pr["state"] == "OPEN" else pr["state"].lower()
    return (
        f"[#{pr['number']}]({pr['url']}) {state}" if pr.get("url") else f"#{pr['number']} {state}"
    )


def _item_pr(item: Item) -> str:
    if not item.pr and item.parent:
        return "via spec"
    return _pr_cell(item.pr)


def _history_cell(note: str, item: Item) -> str:
    return rel_link(note, item.history, "record") if item.history else "-"


def _item_row(v: Vault, note: str, item: Item) -> str:
    return (
        f"| {rel_link(note, item.note, item.label)} | {item.status} | {_item_pr(item)} "
        f"| {_history_cell(note, item)} |"
    )


def _children(v: Vault, spec: Item) -> list[Item]:
    return sorted((i for i in v.items.values() if i.parent == spec.number), key=lambda i: i.number)


def _mermaid_label(item: Item) -> str:
    return f"#{item.number} {item.title}".replace('"', "#quot;").replace("<", "#lt;")


def render_item(v: Vault, item: Item) -> str:
    note = item.note
    facts = [f"**Status:** {item.status}"]
    if item.milestone:
        facts.append(f"**Milestone:** {item.milestone}")
    if item.parent and item.parent in v.items:
        facts.append(
            "**Spec:** " + rel_link(note, v.items[item.parent].note, v.items[item.parent].label)
        )
    elif item.parent:
        facts.append(f"**Spec:** #{item.parent}")
    if item.blocked_by:
        facts.append(
            "**Blocked by:** "
            + ", ".join(
                rel_link(note, v.items[b].note, f"#{b}") if b in v.items else f"#{b}"
                for b in item.blocked_by
            )
        )
    facts.append(f"**PR:** {_item_pr(item)}")
    if item.history:
        facts.append(
            "**Record:** " + rel_link(note, item.history, item.history.split("/")[-1][:-3])
        )
    if item.url:
        facts.append(f"[GitHub]({item.url})")
    out = [
        _front(
            {
                "title": f"#{item.number} {item.title}",
                "tags": [item.kind, item.status.replace(" ", "-")],
                "status": item.status,
            }
        ),
        f"# {item.label}",
        "",
        " · ".join(facts),
        "",
    ]
    if item.kind == "spec":
        kids = _children(v, item)
        out += ["## Tickets", ""]
        if kids:
            out += ["| Ticket | Status | PR | Record |", "| --- | --- | --- | --- |"]
            out += [_item_row(v, note, k) for k in kids]
            out += ["", "```mermaid", "graph LR"]
            for k in kids:
                out.append(f'  t{k.number}["{_mermaid_label(k)}"]')
            for k in kids:
                out += [
                    f"  t{b} --> t{k.number}" for b in k.blocked_by if b in {c.number for c in kids}
                ]
            out += ["```"]
        else:
            out.append("No tickets yet.")
        out.append("")
    out += ["## Description", "", _external(v, note, item.body), ""]
    return "\n".join(out)


def render_board(v: Vault) -> str:
    note = "board.md"
    out = [_front({"title": "Board"}), "# Board", ""]
    for status in STATUSES:
        group = sorted((i for i in v.items.values() if i.status == status), key=lambda i: -i.number)
        if not group:
            continue
        out += [f"## {status.capitalize()} ({len(group)})", ""]
        out += ["| Issue | Kind | Spec | PR | Record |", "| --- | --- | --- | --- | --- |"]
        for i in group:
            spec = (
                rel_link(note, v.items[i.parent].note, f"#{i.parent}")
                if i.parent in v.items
                else "-"
            )
            out.append(
                f"| {rel_link(note, i.note, i.label)} | {i.kind} | {spec} | {_item_pr(i)} "
                f"| {_history_cell(note, i)} |"
            )
        out.append("")
    if len(out) == 3:
        out += ["No issues yet.", ""]
    return "\n".join(out)


def render_index(v: Vault, sha: str) -> str:
    note = "index.md"
    out = [
        _front({"title": v.title}),
        f"# {inline(v.title)}",
        "",
        f"Built from `{sha}` on {now()[:16].replace('T', ' ')}. "
        + rel_link(note, "board.md", "Board")
        + " · "
        + " · ".join(
            f"{s}: {n}"
            for s in STATUSES
            if (n := sum(1 for i in v.items.values() if i.status == s))
        ),
        "",
    ]
    if v.milestones:
        out += [
            "## Milestones",
            "",
            "| Milestone | Status | Spec | PR |",
            "| --- | --- | --- | --- |",
        ]
        for m in v.milestones:
            spec = (
                rel_link(note, v.items[m.spec].note, f"#{m.spec} · {v.items[m.spec].status}")
                if m.spec in v.items
                else (f"#{m.spec}" if m.spec else "-")
            )
            pr_data = v.prs.get(m.pr) if m.pr else None
            pr = _pr_cell(pr_data) if pr_data else (f"#{m.pr}" if m.pr else "-")
            out.append(f"| {m.key} · {inline(m.title)} | {m.status} | {spec} | {pr} |")
        out.append("")
    active = [i for i in v.items.values() if i.status in ("working", "needs human", "needs info")]
    if active:
        out += ["## Now", ""]
        out += [
            f"- {rel_link(note, i.note, i.label)} · {i.status}"
            for i in sorted(active, key=lambda i: i.number)
        ]
        out.append("")
    if v.docs:
        out += ["## Documents", ""]
        out += [f"- {rel_link(note, d, d.removeprefix('docs/')[:-3])}" for d in sorted(v.docs)]
        out.append("")
    if v.histories:
        recent = sorted(
            v.histories.items(), key=lambda kv: str(kv[1].get("updated") or ""), reverse=True
        )[:10]
        out += ["## Latest job records", ""]
        for path, front in recent:
            label = inline(f"#{front.get('issue', '?')} {front.get('title', path)}")
            out.append(
                f"- {rel_link(note, path, label)} · {front.get('stage', '?')} · "
                f"{front.get('rounds', '?')} rounds · {str(front.get('updated') or '')[:10]}"
            )
        out.append("")
    return "\n".join(out)


def render_history(v: Vault, note: str, source: Path) -> str:
    front, body = _split_front(source.read_text(encoding="utf-8", errors="replace"))
    front["title"] = f"Record · #{front.get('issue', '?')} {front.get('title', note)}"
    front["tags"] = ["record", str(front.get("kind", "job"))]
    item = v.items.get(front["issue"]) if isinstance(front.get("issue"), int) else None
    back = f"Issue note: {rel_link(note, item.note, item.label)}\n\n" if item else ""
    body = re.sub(r"^\s*# .*\n", lambda m: m.group(0) + "\n" + back, body, count=1)
    return _front(front) + _linkify(v, note, escape_html(body))


# ---------------------------------------------------------------- build


def _prepare(out: Path) -> None:
    if out.exists():
        if not out.is_dir():
            raise FactoryError(f"{out} exists and is not a folder")
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise FactoryError(
                f"{out} is not empty and was not made by `factory-job vault`; "
                "choose an empty or new folder"
            )
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("made by factory-job vault; rebuilt from scratch each time\n")


_DOC_LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")


def relink_docs(note: str, text: str, notes: set[str], source_url: str | None) -> str:
    """A relative link from a document to a repository file the wiki does not have (LICENSE,
    code, other READMEs) points at that file in the repository instead of a missing page."""
    if not source_url:
        return text
    folders = {posixpath.dirname(n) for n in notes}

    def fix(m: re.Match[str]) -> str:
        target = m.group(2)
        if re.match(r"^[a-zA-Z][\w+.-]*:", target) or target.startswith(("#", "/")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(note), path))
        if resolved.startswith("..") or resolved in notes or resolved.rstrip("/") in folders:
            return m.group(0)
        if f"{resolved}.md" in notes:
            return m.group(0)
        url = f"{source_url}/{resolved}" + (f"#{anchor}" if anchor else "")
        return f"{m.group(1)}{url}{m.group(3)}"

    return _outside_code(text, lambda part: _DOC_LINK.sub(fix, part))


def github_source(cfg: Config) -> str | None:
    """https://github.com/<owner>/<name>/blob/<HEAD sha>, when origin is on GitHub."""
    try:
        remote = git.git(cfg.root, "remote", "get-url", "origin").strip()
    except Exception:
        return None
    # https://github.com/o/r, git@github.com:o/r.git and ssh host aliases (git@github.com-work:o/r)
    m = re.search(r"github\.com[^:/]*[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote)
    sha = git.rev_parse(cfg.root, "HEAD")
    return f"https://github.com/{m.group(1)}/{m.group(2)}/blob/{sha}" if m and sha else None


def build(
    cfg: Config,
    issues: list[Issue],
    prs: list[PullSummary],
    out: Path,
    title: str | None = None,
    source_url: str | None = None,
) -> list[str]:
    """Write the wiki into `out` (replacing a previous one). Returns the note paths written.

    `source_url` (default: the GitHub blob URL of HEAD, if any) is where links from documents to
    repository files outside the wiki point."""
    v = collect(cfg, issues, prs, title or cfg.root.name)
    sha = (git.rev_parse(cfg.root, "HEAD") or "unknown")[:12]
    source_url = source_url if source_url is not None else github_source(cfg)
    _prepare(out)
    notes: dict[str, str] = {
        "index.md": render_index(v, sha),
        "board.md": render_board(v),
    }
    for item in v.items.values():
        notes[item.note] = render_item(v, item)
    history_dir = str(cfg.data.get("history_dir") or "").strip("/")
    for note in v.histories:
        notes[note] = render_history(v, note, cfg.root / history_dir / note.split("/", 1)[1])
    all_notes = set(notes) | set(v.docs)
    for note, src in v.docs.items():
        text = _linkify(v, note, src.read_text(encoding="utf-8", errors="replace"))
        notes[note] = relink_docs(note, text, all_notes, source_url)
    for note, text in notes.items():
        path = out / note
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return sorted(notes)
