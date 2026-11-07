"""The project wiki: a folder of linked markdown notes built from the repository and GitHub.

`factory-job vault <out>` writes it. The folder is at the same time an Obsidian vault and the
`content/` folder of a Quartz site (DESIGN.md · Wiki). It is a projection: everything in it comes
from the repository (docs/, GLOSSARY.md, docs/history/) and from a snapshot of GitHub issues and
PRs, so it can be thrown away and rebuilt at any time.

What the project knows is grouped in categories, one folder each with an index note. The
repository's files are not moved: only the wiki is organised this way (CATEGORIES, place_doc).

    index.md                 the categories, milestones, what is going on, latest records
    product/                 README, brief, requirements, roadmap (index: milestones)
    domain/                  GLOSSARY.md (index: the terms)
    architecture/            architecture.md, CLAUDE.md, any other document in docs/
    decisions/               the ADRs (index: number, title, status, date)
    work/                    index: the board; specs/<n>.md and tickets/<n>.md from GitHub
    history/                 the job records committed by factory-job (index: every record)

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

# (folder, title, what it holds), in the order the home page lists them.
CATEGORIES = (
    ("product", "Product", "What we are building and why: brief, requirements, roadmap."),
    ("domain", "Domain", "The project's language: the glossary."),
    ("architecture", "Architecture", "How the code is organised and how to work in it."),
    ("decisions", "Decisions", "Architecture decisions and why they were taken."),
    ("work", "Work", "Specs and tickets, from GitHub, by status."),
    ("history", "History", "How each job was planned, built and reviewed."),
)


def place_doc(rel: str) -> str:
    """Where a repository document goes in the wiki (by its path in the repository)."""
    fixed = {
        "README.md": "product/README.md",
        "docs/brief.md": "product/brief.md",
        "docs/roadmap.md": "product/roadmap.md",
        "GLOSSARY.md": "domain/GLOSSARY.md",
        "CLAUDE.md": "architecture/CLAUDE.md",
        "docs/architecture.md": "architecture/architecture.md",
    }
    if rel in fixed:
        return fixed[rel]
    if rel.startswith("docs/requirements/"):
        return "product/" + rel.removeprefix("docs/")
    if rel.startswith("docs/adr/"):
        return "decisions/" + rel.removeprefix("docs/adr/")
    placed = "architecture/" + rel.removeprefix("docs/")
    # a document must not take the place of a category's index
    if placed.endswith("/index.md") and placed.count("/") == 1:
        placed = placed[: -len(".md")] + "-document.md"
    return placed


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
        return f"work/{self.kind}s/{self.number}.md"

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
    doc_repo_path: dict[str, str] = field(default_factory=dict)  # note path -> path in the repo


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

    sources: list[str] = [
        n for n in ("README.md", "GLOSSARY.md", "CLAUDE.md") if (root / n).is_file()
    ]
    if (root / "docs").is_dir():
        for p in sorted((root / "docs").rglob("*.md")):
            rel = p.relative_to(root).as_posix()
            if history_dir and (rel + "/").startswith(history_dir + "/"):
                continue
            sources.append(rel)
    docs: dict[str, Path] = {}
    doc_repo_path: dict[str, str] = {}
    for rel in sources:
        note = place_doc(rel)
        docs[note], doc_repo_path[note] = root / rel, rel

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
    return Vault(cfg, title, items, milestones, histories, docs, pr_by_number, doc_repo_path)


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
    """The Work category's index: every spec and ticket grouped by status."""
    note = "work/index.md"
    out = [_front({"title": "Work"}), "# Work", "", _category_text("work"), ""]
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
    if len(out) == 5:
        out += ["No issues yet.", ""]
    return "\n".join(out)


def _category_text(folder: str) -> str:
    return next(text for key, _, text in CATEGORIES if key == folder)


def _milestone_rows(v: Vault, note: str) -> list[str]:
    rows = ["| Milestone | Status | Spec | PR |", "| --- | --- | --- | --- |"]
    for m in v.milestones:
        spec = (
            rel_link(note, v.items[m.spec].note, f"#{m.spec} · {v.items[m.spec].status}")
            if m.spec in v.items
            else (f"#{m.spec}" if m.spec else "-")
        )
        pr_data = v.prs.get(m.pr) if m.pr else None
        pr = _pr_cell(pr_data) if pr_data else (f"#{m.pr}" if m.pr else "-")
        rows.append(f"| {m.key} · {inline(m.title)} | {m.status} | {spec} | {pr} |")
    return rows


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _category_count(v: Vault, folder: str) -> str:
    docs = sum(1 for d in v.docs if d.startswith(folder + "/"))
    if folder == "work":
        specs = sum(1 for i in v.items.values() if i.kind == "spec")
        return f"{_n(specs, 'spec')}, {_n(len(v.items) - specs, 'ticket')}"
    if folder == "history":
        return _n(len(v.histories), "record")
    if folder == "decisions":
        return _n(docs, "decision")
    if folder == "domain":
        return _n(len(_glossary_terms(v)), "term")
    return _n(docs, "document")


def render_index(v: Vault, sha: str) -> str:
    note = "index.md"
    counts = " · ".join(
        f"{s}: {n}" for s in STATUSES if (n := sum(1 for i in v.items.values() if i.status == s))
    )
    out = [
        _front({"title": v.title}),
        f"# {inline(v.title)}",
        "",
        f"Built from `{sha}` on {now()[:16].replace('T', ' ')}."
        + (f" Work: {counts}." if counts else ""),
        "",
        "## What we know",
        "",
        "| Category | What it holds | |",
        "| --- | --- | --- |",
    ]
    for folder, title, text in CATEGORIES:
        out.append(
            f"| {rel_link(note, f'{folder}/index.md', title)} | {text} | {_category_count(v, folder)} |"
        )
    out.append("")
    if v.milestones:
        out += ["## Milestones", "", *_milestone_rows(v, note), ""]
    active = [i for i in v.items.values() if i.status in ("working", "needs human", "needs info")]
    if active:
        out += ["## Now", ""]
        out += [
            f"- {rel_link(note, i.note, i.label)} · {i.status}"
            for i in sorted(active, key=lambda i: i.number)
        ]
        out.append("")
    if v.histories:
        out += ["## Latest job records", "", *_record_lines(v, note, limit=5), ""]
    return "\n".join(out)


def _record_lines(v: Vault, note: str, limit: int | None = None) -> list[str]:
    recent = sorted(
        v.histories.items(), key=lambda kv: str(kv[1].get("updated") or ""), reverse=True
    )
    lines = []
    for path, front in recent[:limit]:
        label = inline(f"#{front.get('issue', '?')} {front.get('title', path)}")
        lines.append(
            f"- {rel_link(note, path, label)} · {front.get('kind', 'job')} · "
            f"{front.get('stage', '?')} · {front.get('rounds', '?')} rounds · "
            f"{str(front.get('updated') or '')[:10]}"
        )
    return lines


def _doc_title(path: Path, fallback: str) -> str:
    if path.name == "CLAUDE.md":  # its heading is the project's name, which says nothing here
        return "How to work in this repository"
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return fallback


def _doc_list(v: Vault, note: str, folder: str) -> list[str]:
    docs = sorted(d for d in v.docs if d.startswith(folder + "/"))
    return [
        f"- {rel_link(note, d, inline(_doc_title(v.docs[d], d.split('/')[-1][:-3])))}"
        f" · `{v.doc_repo_path[d]}`"
        for d in docs
    ]


def _adr_facts(path: Path) -> tuple[str, str]:
    """Status and date from an ADR's first lines: `Status: x`, `Date: y`, in any of the usual
    shapes (front matter, a list, one line with both)."""
    head = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:20])
    status = re.search(r"(?im)\bstatus\b\**\s*[:=]\s*\**\s*([^·|\n*]+)", head)
    date = re.search(r"(?im)\bdate\b\**\s*[:=]\s*\**\s*(\d{4}-\d{2}-\d{2})", head)
    return (
        status.group(1).strip() if status else "-",
        date.group(1) if date else "-",
    )


def _glossary_terms(v: Vault) -> list[str]:
    """Terms in GLOSSARY.md: `**Term**:` lines (domain-modeling) or the first column of a table."""
    path = v.docs.get("domain/GLOSSARY.md")
    if path is None:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    terms = re.findall(r"(?m)^\s*[-*]?\s*\*\*([^*]+?)\*\*\s*:", text)
    for row in re.findall(r"(?m)^\|\s*([^|]+?)\s*\|", text):
        if row.lower() not in ("term", "termino", "término") and not set(row) <= set("-: "):
            terms.append(row.strip("`* "))
    return list(dict.fromkeys(t.strip() for t in terms if t.strip()))


def render_category(v: Vault, folder: str) -> str:
    """The index note of a category (Work's is the board, see render_board)."""
    title = next(t for key, t, _ in CATEGORIES if key == folder)
    note = f"{folder}/index.md"
    out = [_front({"title": title}), f"# {title}", "", _category_text(folder), ""]
    if folder == "product" and v.milestones:
        out += ["## Milestones", "", *_milestone_rows(v, note), ""]
    if folder == "domain":
        terms = _glossary_terms(v)
        if terms:
            glossary = rel_link(note, "domain/GLOSSARY.md", "glossary")
            out += [f"## Terms ({len(terms)})", "", f"Defined in the {glossary}.", ""]
            out += [f"- {inline(t)}" for t in terms]
            out.append("")
    if folder == "decisions":
        adrs = sorted(d for d in v.docs if d.startswith("decisions/"))
        if adrs:
            out += ["| Decision | Status | Date |", "| --- | --- | --- |"]
            for d in adrs:
                status, date = _adr_facts(v.docs[d])
                label = inline(_doc_title(v.docs[d], d.split("/")[-1][:-3]))
                out.append(f"| {rel_link(note, d, label)} | {inline(status)} | {date} |")
            out.append("")
    elif folder != "history":
        docs = _doc_list(v, note, folder)
        if docs:
            out += ["## Documents", "", *docs, ""]
    if folder == "history" and v.histories:
        out += [*_record_lines(v, note), ""]
    if len(out) == 5:
        out += ["Nothing here yet.", ""]
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


def relink_docs(
    note: str, repo_path: str, text: str, placed: dict[str, str], source_url: str | None
) -> str:
    """Relative links in a document, written for the repository, made right for the wiki.

    `placed` maps repository paths to wiki notes. A link to a document the wiki has points at its
    note; to a folder of them, at that folder; to any other repository file (LICENSE, code), at
    the file in the repository (`source_url`), or stays as written without one."""

    def target_for(resolved: str) -> str | None:
        for candidate in (resolved, f"{resolved}.md"):
            if candidate in placed:
                return placed[candidate]
        prefix = resolved.rstrip("/") + "/"
        for repo, wiki in placed.items():
            suffix = repo[len(prefix) :]
            if repo.startswith(prefix) and wiki.endswith("/" + suffix):
                return wiki[: -len(suffix)]  # the folder, with its trailing slash
        return None

    def fix(m: re.Match[str]) -> str:
        target = m.group(2)
        if re.match(r"^[a-zA-Z][\w+.-]*:", target) or target.startswith(("#", "/")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(repo_path), path))
        if resolved.startswith(".."):
            return m.group(0)
        tail = f"#{anchor}" if anchor else ""
        wiki = target_for(resolved)
        if wiki is not None:
            rel = posixpath.relpath(wiki, posixpath.dirname(note) or ".")
            rel += "/" if wiki.endswith("/") and not rel.endswith("/") else ""
            return f"{m.group(1)}{rel}{tail}{m.group(3)}"
        if source_url:
            return f"{m.group(1)}{source_url}/{resolved}{tail}{m.group(3)}"
        return m.group(0)

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
        "work/index.md": render_board(v),
    }
    for folder, _, _ in CATEGORIES:
        if folder != "work":
            notes[f"{folder}/index.md"] = render_category(v, folder)
    for item in v.items.values():
        notes[item.note] = render_item(v, item)
    history_dir = str(cfg.data.get("history_dir") or "").strip("/")
    for note in v.histories:
        notes[note] = render_history(v, note, cfg.root / history_dir / note.split("/", 1)[1])
    placed = {repo: note for note, repo in v.doc_repo_path.items()}
    if history_dir:
        placed.update({f"{history_dir}/{n.split('/', 1)[1]}": n for n in v.histories})
    for note, src in v.docs.items():
        text = _linkify(v, note, src.read_text(encoding="utf-8", errors="replace"))
        notes[note] = relink_docs(note, v.doc_repo_path[note], text, placed, source_url)
    for note, text in notes.items():
        path = out / note
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return sorted(notes)
