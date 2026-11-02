"""Test fixtures: a throwaway project with a bare 'origin', fake GitHub, no network."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY))

from lib import config, jobs, machine  # noqa: E402
from lib.github import FakeGitHub  # noqa: E402

CONFIG: dict[str, Any] = {
    "base_branch": "main",
    "merge_method": "merge",
    "concurrency": 1,
    "max_rounds": 3,
    "spec_branch_prefix": "spec/",
    "job_branch_prefix": "factory/",
    "worktrees_dir": ".claude/worktrees",
    "labels": {
        "queue": "ready-for-agent",
        "spec": "spec",
        "needs_info": "needs-info",
        "needs_human": "ready-for-human",
        "in_progress": "factory:working",
    },
    "models": {
        "planner": "opus",
        "builder": {"low": "sonnet", "medium": "sonnet", "high": "opus"},
        "reviewer": {"low": "haiku", "medium": "sonnet", "high": "sonnet"},
        "final_reviewer": "opus",
    },
    "always_human_surfaces": ["payments"],
    "protected_paths": ["factory/**", ".github/**", ".claude/**", "tests/**"],
    "checks_timeout_s": 30,
    "log_tail_lines": 40,
}

CHECKS_SH = """#!/usr/bin/env bash
set -euo pipefail
echo "MAIN-CHECKS running in $PWD"
python3 -m unittest discover -s tests -q 2>&1
"""

QUEUE = "ready-for-agent"


def sh(cwd: Path, *args: str) -> str:
    proc = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"{args} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


class FactoryTestCase(unittest.TestCase):
    """Builds tmp/origin.git + tmp/main (the main checkout) + tmp/gh (fake GitHub)."""

    config_overrides: ClassVar[dict[str, Any]] = {}

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._env = dict(os.environ)
        self.addCleanup(self._restore_env)
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text(
            "[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n"
        )
        os.environ.update(
            {
                "GIT_CONFIG_GLOBAL": str(gitconfig),
                "GIT_CONFIG_NOSYSTEM": "1",
                "FACTORY_GH": "fake",
                "FACTORY_GH_DIR": str(self.tmp / "gh"),
                "FACTORY_ROOT": str(self.tmp / "main"),
            }
        )
        self.origin = self.tmp / "origin.git"
        self.root = self.tmp / "main"
        sh(self.tmp, "git", "init", "--quiet", "--bare", "-b", "main", str(self.origin))
        sh(self.tmp, "git", "clone", "--quiet", str(self.origin), str(self.root))
        cfg = json.loads(json.dumps(CONFIG))
        cfg.update(self.config_overrides)
        self.write(self.root, "factory/config.json", json.dumps(cfg, indent=2))
        self.write(self.root, "factory/checks.sh", CHECKS_SH, executable=True)
        self.write(self.root, "mod.py", "def add(a, b):\n    return a + b\n")
        self.write(
            self.root,
            "tests/test_mod.py",
            "import unittest\n\nfrom mod import add\n\n\nclass ModTest(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n",
        )
        self.write(
            self.root, ".gitignore", "factory/jobs/\n.claude/worktrees/\n__pycache__/\n.env\n"
        )
        self.write(self.root, ".worktreeinclude", ".env\n")
        self.write(self.root, ".env", "SECRET=1\n")
        self.git(self.root, "add", "-A")
        self.git(self.root, "commit", "--quiet", "-m", "init")
        self.git(self.root, "push", "--quiet", "origin", "main")
        self.gh = FakeGitHub(self.tmp / "gh")
        self.gh.save({"issues": {}, "prs": {}, "next_number": 1000, "log": []})
        self.cfg = config.load(self.root)
        self.ctx = machine.Ctx(self.cfg, self.gh)

    def _restore_env(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    # ------------------------------------------------------------ fs / git

    @staticmethod
    def write(base: Path, rel: str, content: str, executable: bool = False) -> Path:
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    @staticmethod
    def git(cwd: Path, *args: str) -> str:
        return sh(cwd, "git", *args)

    def commit(self, cwd: Path, rel: str, content: str, msg: str = "change") -> None:
        self.write(cwd, rel, content)
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "--quiet", "-m", msg)

    def remote_branches(self) -> list[str]:
        out = sh(self.origin, "git", "for-each-ref", "--format=%(refname:short)", "refs/heads")
        return out.split()

    # ------------------------------------------------------------ fake GitHub

    def add_issue(
        self,
        number: int,
        title: str = "Reading time",
        body: str = "Add it.",
        labels: list[str] | None = None,
    ) -> None:
        state = self.gh.load()
        state["issues"][str(number)] = {
            "number": number,
            "title": title,
            "author": "alice",
            "url": f"https://github.com/fake/repo/issues/{number}",
            "body": body,
            "labels": [QUEUE] if labels is None else labels,
            "state": "OPEN",
            "comments": [],
        }
        self.gh.save(state)

    def human_comment(self, number: int, body: str, author: str = "alice") -> None:
        import datetime as dt

        state = self.gh.load()
        bucket = "issues" if str(number) in state["issues"] else "prs"
        ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)).isoformat(
            timespec="seconds"
        )
        state[bucket][str(number)].setdefault("comments", []).append(
            {"author": author, "body": body, "created_at": ts}
        )
        self.gh.save(state)

    def merge_pr(self, number: int) -> None:
        state = self.gh.load()
        state["prs"][str(number)]["state"] = "MERGED"
        self.gh.save(state)

    def ops(self, op: str) -> list[dict[str, Any]]:
        return [entry for entry in self.gh.load()["log"] if entry["op"] == op]

    def labels(self, number: int) -> list[str]:
        return list(self.gh.load()["issues"][str(number)]["labels"])

    def comments(self, number: int) -> list[str]:
        state = self.gh.load()
        bucket = "issues" if str(number) in state["issues"] else "prs"
        return [c["body"] for c in state[bucket][str(number)].get("comments", [])]

    # ------------------------------------------------------------ jobs and agent files

    def job(self, ref: str | int = 12) -> jobs.Job:
        return jobs.resolve(self.cfg, str(ref))

    def new_job(self, number: int = 12, **issue: Any) -> jobs.Job:
        self.add_issue(number, **issue)
        machine.create(self.ctx, number)
        return self.job(number)

    def write_plan(
        self, job: jobs.Job, decision: str = "ACCEPT", risk: str = "medium", surfaces: str = "ui"
    ) -> None:
        body = {
            "ACCEPT": "## Scope\n\nAdd sub().\n\n## Acceptance criteria\n\n- C1: sub(3, 1) == 2\n\n"
            "## Seams\n\n`mod.sub`\n\n## Notes\n\nnone\n",
            "NEEDS-INFO": "## Question\n\nIntegers or floats?\n",
            "REJECT": "## Reason\n\nOut of scope.\n",
        }[decision]
        self.write(
            job.dir,
            "plan.md",
            f"DECISION: {decision}\nRISK: {risk}\nSURFACES: {surfaces}\n\n{body}",
        )

    def build_feature(self, job: jobs.Job, evidence: str | None = None) -> None:
        """What a builder does: commit code + a new test, write a READY build.md."""
        wt = job.worktree
        self.commit(
            wt,
            "mod.py",
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            "C1: sub",
        )
        self.commit(
            wt,
            "tests/test_sub.py",
            "import unittest\n\nfrom mod import sub\n\n\nclass SubTest(unittest.TestCase):\n"
            "    def test_sub(self):\n        self.assertEqual(sub(3, 1), 2)\n",
            "C1: test",
        )
        self.write_build(job, evidence=evidence)

    def write_build(
        self, job: jobs.Job, status: str = "READY", evidence: str | None = None
    ) -> None:
        if status == "READY":
            ev = evidence or "C1: tests/test_sub.py::test_sub — sub(3, 1) == 2"
            text = f"STATUS: READY\n\n## Evidence\n\n{ev}\n"
        else:
            text = "STATUS: BLOCKED\n\n## Blocker\n\nMay I change the signature of add()?\n"
        self.write(job.dir, "build.md", text)

    def write_checks(self, job: jobs.Job, gate: str = "PASS") -> None:
        self.write(job.round_dir(), "checks.md", f"GATE: {gate}\nPROTECTED: none\n\nlog\n")

    def write_review(self, job: jobs.Job, verdict: str = "PASS") -> None:
        self.write(
            job.round_dir(),
            "review.md",
            f"VERDICT: {verdict}\n\n## Standards\n\nok\n\n## Spec\n\nok\n\n## Architecture\n\nok\n",
        )

    # ------------------------------------------------------------ driving

    def start(self, job: jobs.Job) -> jobs.Job:
        machine.start(self.ctx, job)
        return self.job(job["issue"])

    def advance(self, job: jobs.Job) -> jobs.Job:
        machine.advance(self.ctx, self.job(job["issue"]))
        return self.job(job["issue"])

    def to_build(self, number: int = 12, **issue: Any) -> jobs.Job:
        job = self.start(self.new_job(number, **issue))
        self.write_plan(job)
        return self.advance(job)

    def to_gate(self, number: int = 12, **issue: Any) -> jobs.Job:
        job = self.to_build(number, **issue)
        self.build_feature(job)
        return self.advance(job)

    def to_review(self, number: int = 12, **issue: Any) -> jobs.Job:
        job = self.to_gate(number, **issue)
        self.write_checks(job, "PASS")
        return self.advance(job)

    def make_spec_ticket(self, number: int = 12, spec_branch: str = "spec/010-blog") -> jobs.Job:
        """A ticket that belongs to a spec (spec level itself arrives in phase 5)."""
        self.git(self.root, "push", "--quiet", "origin", f"main:refs/heads/{spec_branch}")
        job = self.new_job(number)
        job["spec"] = "010-blog"
        job["base"] = spec_branch
        job.save()
        return self.job(number)

    def run_cli(self, tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FACTORY / "bin" / f"factory-{tool}"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )
