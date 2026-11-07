"""GitHub adapter. The real one shells out to `gh`; FACTORY_GH=fake uses a JSON fixture dir.

Normalised shapes (both implementations return exactly these):

    Comment = {"author": str, "body": str, "created_at": iso str}
    Issue   = {"number", "title", "author", "url", "body", "labels": [str],
               "state": "OPEN"|"CLOSED", "comments": [Comment]}
    PR      = {"number", "url", "head", "base", "draft": bool,
               "state": "OPEN"|"CLOSED"|"MERGED", "comments": [Comment]}

PR comments include conversation comments, review bodies and inline review comments
(inline ones prefixed with "path:line").
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from lib.util import CommandError, UsageError, now, run

Issue = dict[str, Any]
PR = dict[str, Any]
Comment = dict[str, Any]
# For the wiki (lib/vault.py): every PR, open or closed, without comments.
#   PullSummary = {"number", "title", "url", "head", "base", "body", "draft": bool,
#                  "state": "OPEN"|"CLOSED"|"MERGED"}
PullSummary = dict[str, Any]


class GitHub(Protocol):
    def issue(self, number: int) -> Issue: ...
    def list_issues(self, label: str) -> list[Issue]: ...
    def list_open_issues(self) -> list[Issue]: ...
    def comment(self, number: int, body: str) -> None: ...
    def add_label(self, number: int, label: str) -> None: ...
    def remove_label(self, number: int, label: str) -> None: ...
    def close_issue(self, number: int) -> None: ...
    def create_pr(self, head: str, base: str, title: str, body: str, draft: bool) -> PR: ...
    def mark_ready(self, number: int) -> None: ...
    def pr(self, number: int) -> PR: ...
    def find_pr(self, head: str) -> PR | None: ...
    def all_issues(self) -> list[Issue]: ...
    def all_prs(self) -> list[PullSummary]: ...


def connect(root: Path) -> GitHub:
    mode = os.environ.get("FACTORY_GH", "")
    if mode == "fake":
        fixture = os.environ.get("FACTORY_GH_DIR")
        if not fixture:
            raise UsageError("FACTORY_GH=fake requires FACTORY_GH_DIR")
        return FakeGitHub(Path(fixture))
    if mode not in ("", "gh"):
        raise UsageError(f"unknown FACTORY_GH={mode!r} (expected 'gh' or 'fake')")
    return GhCli(root)


# ---------------------------------------------------------------- real: gh CLI


class GhCli:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _gh(self, *args: str, input_text: str | None = None) -> str:
        return run(["gh", *args], cwd=self.root, input_text=input_text).stdout

    def _json(self, *args: str) -> Any:
        return json.loads(self._gh(*args) or "null")

    @staticmethod
    def _comment(author: Any, body: str, created_at: str) -> Comment:
        login = (author or {}).get("login", "ghost") if isinstance(author, dict) else str(author)
        return {"author": login, "body": body or "", "created_at": created_at}

    def issue(self, number: int) -> Issue:
        d = self._json(
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,author,url,body,labels,state,comments",
        )
        return {
            "number": d["number"],
            "title": d["title"],
            "author": (d.get("author") or {}).get("login", "ghost"),
            "url": d["url"],
            "body": d.get("body") or "",
            "labels": [lbl["name"] for lbl in d.get("labels", [])],
            "state": d["state"],
            "comments": [
                self._comment(c.get("author"), c.get("body", ""), c["createdAt"])
                for c in d.get("comments", [])
            ],
        }

    def list_open_issues(self) -> list[Issue]:
        return self._list("--state", "open")

    def list_issues(self, label: str) -> list[Issue]:
        return self._list("--state", "open", "--label", label)

    def _list(self, *filters: str) -> list[Issue]:
        rows = self._json(
            "issue",
            "list",
            *filters,
            "--limit",
            "500",
            "--json",
            "number,title,author,url,body,labels,state",
        )
        return [
            {
                "number": d["number"],
                "title": d["title"],
                "author": (d.get("author") or {}).get("login", "ghost"),
                "url": d["url"],
                "body": d.get("body") or "",
                "labels": [lbl["name"] for lbl in d.get("labels", [])],
                "state": d["state"],
                "comments": [],
            }
            for d in rows
        ]

    def comment(self, number: int, body: str) -> None:
        # The issues endpoint accepts PR numbers too.
        self._gh(
            "api",
            f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
            "--input",
            "-",
            input_text=json.dumps({"body": body}),
        )

    def add_label(self, number: int, label: str) -> None:
        self._gh(
            "api",
            f"repos/{{owner}}/{{repo}}/issues/{number}/labels",
            "--input",
            "-",
            input_text=json.dumps({"labels": [label]}),
        )

    def remove_label(self, number: int, label: str) -> None:
        try:
            self._gh(
                "api",
                "-X",
                "DELETE",
                f"repos/{{owner}}/{{repo}}/issues/{number}/labels/{label}",
            )
        except CommandError as exc:
            if "404" not in str(exc):  # label was not there: nothing to do
                raise

    def close_issue(self, number: int) -> None:
        self._gh("issue", "close", str(number))

    def create_pr(self, head: str, base: str, title: str, body: str, draft: bool) -> PR:
        d = json.loads(
            self._gh(
                "api",
                "repos/{owner}/{repo}/pulls",
                "--input",
                "-",
                input_text=json.dumps(
                    {"head": head, "base": base, "title": title, "body": body, "draft": draft}
                ),
            )
        )
        return self.pr(int(d["number"]))

    def mark_ready(self, number: int) -> None:
        self._gh("pr", "ready", str(number))

    def pr(self, number: int) -> PR:
        d = self._json(
            "pr",
            "view",
            str(number),
            "--json",
            "number,url,state,isDraft,headRefName,baseRefName,comments,reviews",
        )
        comments = [
            self._comment(c.get("author"), c.get("body", ""), c["createdAt"])
            for c in d.get("comments", [])
        ]
        comments += [
            self._comment(r.get("author"), r.get("body", ""), r["submittedAt"])
            for r in d.get("reviews", [])
            if r.get("body") and r.get("submittedAt")
        ]
        inline = self._json("api", f"repos/{{owner}}/{{repo}}/pulls/{number}/comments")
        comments += [
            self._comment(
                c.get("user"),
                f"{c.get('path')}:{c.get('line') or c.get('original_line') or '?'} {c.get('body', '')}",
                c["created_at"],
            )
            for c in inline or []
        ]
        comments.sort(key=lambda c: c["created_at"])
        return {
            "number": d["number"],
            "url": d["url"],
            "head": d["headRefName"],
            "base": d["baseRefName"],
            "draft": bool(d["isDraft"]),
            "state": d["state"],
            "comments": comments,
        }

    def find_pr(self, head: str) -> PR | None:
        rows = self._json("pr", "list", "--head", head, "--state", "all", "--json", "number")
        return self.pr(int(rows[0]["number"])) if rows else None

    def all_issues(self) -> list[Issue]:
        return self._list("--state", "all")

    def all_prs(self) -> list[PullSummary]:
        rows = self._json(
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            "1000",
            "--json",
            "number,title,url,state,isDraft,headRefName,baseRefName,body",
        )
        return [
            {
                "number": d["number"],
                "title": d["title"],
                "url": d["url"],
                "head": d["headRefName"],
                "base": d["baseRefName"],
                "body": d.get("body") or "",
                "draft": bool(d["isDraft"]),
                "state": d["state"],
            }
            for d in rows
        ]


# ---------------------------------------------------------------- fake: JSON fixtures


class FakeGitHub:
    """Reads and writes <dir>/state.json. Every mutating call is appended to state['log']."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / "state.json"

    # -- fixture helpers (also used by tests)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"issues": {}, "prs": {}, "next_number": 1000, "log": []}
        data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _log(self, state: dict[str, Any], op: str, **kw: Any) -> None:
        state["log"].append({"op": op, **kw})

    def _issue(self, state: dict[str, Any], number: int) -> dict[str, Any]:
        key = str(number)
        if key in state["issues"]:
            return dict(state["issues"][key])
        if key in state["prs"]:
            return dict(state["prs"][key])
        raise CommandError(["gh(fake)", "issue", key], 1, "", f"issue #{number} not found")

    # -- GitHub protocol

    def issue(self, number: int) -> Issue:
        state = self.load()
        d = self._issue(state, number)
        if str(number) not in state["issues"]:
            raise CommandError(["gh(fake)", "issue", str(number)], 1, "", "is a pull request")
        d.setdefault("comments", [])
        d.setdefault("labels", [])
        d.setdefault("state", "OPEN")
        d.setdefault("body", "")
        d.setdefault("author", "someone")
        d.setdefault("url", f"https://github.com/fake/repo/issues/{number}")
        return d

    def list_open_issues(self) -> list[Issue]:
        state = self.load()
        return [
            self.issue(int(n))
            for n, d in sorted(state["issues"].items(), key=lambda kv: int(kv[0]))
            if d.get("state", "OPEN") == "OPEN"
        ]

    def list_issues(self, label: str) -> list[Issue]:
        state = self.load()
        return [
            self.issue(int(n))
            for n, d in sorted(state["issues"].items(), key=lambda kv: int(kv[0]))
            if d.get("state", "OPEN") == "OPEN" and label in d.get("labels", [])
        ]

    def _mutate_item(self, number: int, fn: Any, op: str, **kw: Any) -> None:
        state = self.load()
        for bucket in ("issues", "prs"):
            if str(number) in state[bucket]:
                fn(state[bucket][str(number)])
                self._log(state, op, number=number, **kw)
                self.save(state)
                return
        raise CommandError(["gh(fake)", op, str(number)], 1, "", f"#{number} not found")

    def comment(self, number: int, body: str) -> None:
        def fn(d: dict[str, Any]) -> None:
            d.setdefault("comments", []).append(
                {"author": "factory-bot", "body": body, "created_at": now()}
            )

        self._mutate_item(number, fn, "comment", body=body)

    def add_label(self, number: int, label: str) -> None:
        def fn(d: dict[str, Any]) -> None:
            labels = d.setdefault("labels", [])
            if label not in labels:
                labels.append(label)

        self._mutate_item(number, fn, "add_label", label=label)

    def remove_label(self, number: int, label: str) -> None:
        def fn(d: dict[str, Any]) -> None:
            d["labels"] = [x for x in d.get("labels", []) if x != label]

        self._mutate_item(number, fn, "remove_label", label=label)

    def close_issue(self, number: int) -> None:
        def fn(d: dict[str, Any]) -> None:
            d["state"] = "CLOSED"

        self._mutate_item(number, fn, "close_issue")

    def create_pr(self, head: str, base: str, title: str, body: str, draft: bool) -> PR:
        state = self.load()
        number = int(state.get("next_number", 1000))
        state["next_number"] = number + 1
        state["prs"][str(number)] = {
            "number": number,
            "url": f"https://github.com/fake/repo/pull/{number}",
            "head": head,
            "base": base,
            "title": title,
            "body": body,
            "draft": draft,
            "state": "OPEN",
            "labels": [],
            "comments": [],
        }
        self._log(state, "create_pr", number=number, head=head, base=base, draft=draft)
        self.save(state)
        return self.pr(number)

    def mark_ready(self, number: int) -> None:
        def fn(d: dict[str, Any]) -> None:
            d["draft"] = False

        self._mutate_item(number, fn, "mark_ready")

    def pr(self, number: int) -> PR:
        state = self.load()
        if str(number) not in state["prs"]:
            raise CommandError(["gh(fake)", "pr", str(number)], 1, "", f"PR #{number} not found")
        d = dict(state["prs"][str(number)])
        d.setdefault("comments", [])
        return d

    def find_pr(self, head: str) -> PR | None:
        for d in self.load()["prs"].values():
            if d["head"] == head:
                return self.pr(int(d["number"]))
        return None

    def all_issues(self) -> list[Issue]:
        state = self.load()
        return [self.issue(int(n)) for n in sorted(state["issues"], key=int)]

    def all_prs(self) -> list[PullSummary]:
        out = []
        for n in sorted(self.load()["prs"], key=int):
            d = self.pr(int(n))
            out.append(
                {
                    "number": d["number"],
                    "title": d.get("title", ""),
                    "url": d.get("url", ""),
                    "head": d["head"],
                    "base": d["base"],
                    "body": d.get("body", ""),
                    "draft": bool(d.get("draft")),
                    "state": d.get("state", "OPEN"),
                }
            )
        return out
