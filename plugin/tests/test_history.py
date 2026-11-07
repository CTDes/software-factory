"""Job history: docs/history/<job-id>.md committed into the job branch (DESIGN.md · Job history)."""

from __future__ import annotations

import json
import unittest
from typing import Any, ClassVar

from helpers import CONFIG, FactoryTestCase
from lib import config, history, jobs, machine, spec
from lib.util import ConfigError

REL = "docs/history/012-reading-time.md"


class HistoryTestCase(FactoryTestCase):
    def to_ready(self, **issue: object) -> jobs.Job:
        job = self.to_review(**issue)
        self.write_review(job, "PASS")
        return self.advance(job)

    def remote_file(self, branch: str, rel: str) -> str:
        return self.git(self.origin, "show", f"{branch}:{rel}")

    def log_subjects(self, cwd: object, ref: str = "HEAD") -> list[str]:
        return self.git(cwd, "log", "--format=%s", ref).splitlines()  # type: ignore[arg-type]


class StandaloneTicket(HistoryTestCase):
    def test_ready_commits_history_and_pushes_it_before_the_pr_leaves_draft(self) -> None:
        job = self.to_ready()
        self.assertEqual(job.stage, "ready")
        text = self.remote_file(job["branch"], REL)
        self.assertEqual(self.log_subjects(job.worktree)[0], f"docs(history): {job.id}")
        self.assertIn('job: "012-reading-time"', text)
        self.assertIn('stage: "ready"', text)
        self.assertIn("# #12 Reading time", text)
        self.assertIn("Add it.", text)  # issue body
        self.assertIn("C1: sub(3, 1) == 2", text)  # plan
        self.assertIn("## Round 1", text)
        self.assertIn("**GATE:** PASS", text)
        self.assertIn("**VERDICT:** PASS", text)
        self.assertIn("| review | ready | PASS |", text)  # the transition being applied
        log = self.gh.load()["log"]
        ops = [e["op"] for e in log]
        self.assertIn("mark_ready", ops)
        self.assertTrue(job.worktree.joinpath(REL).exists())
        self.assertTrue(self.git(job.worktree, "status", "--porcelain").strip() == "")

    def test_history_push_does_not_move_pushed_at(self) -> None:
        job = self.to_review()
        pushed = job["pushed_at"]
        self.write_review(job, "PASS")
        self.assertEqual(self.advance(job)["pushed_at"], pushed)

    def test_rework_round_regenerates_history_with_feedback(self) -> None:
        job = self.to_ready()
        self.human_comment(job["pr"], "Please rename sub to subtract.")
        machine.rework(self.ctx, job)
        job = self.job()
        self.commit(
            job.worktree,
            "mod.py",
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b  # ok\n",
        )
        self.write_build(job)
        job = self.advance(job)
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job, "PASS")
        job = self.advance(job)
        self.assertEqual((job.stage, job["round"]), ("ready", 2))
        text = self.remote_file(job["branch"], REL)
        self.assertIn("## Round 2", text)
        self.assertIn("## Human feedback", text)
        self.assertIn("Please rename sub to subtract.", text)
        subjects = self.log_subjects(job.worktree)
        self.assertEqual(subjects.count(f"docs(history): {job.id}"), 2)

    def test_external_text_is_fenced(self) -> None:
        body = "Look:\n````\n# not a heading\n<script>alert(1)</script>\n````"
        job = self.to_ready(body=body)
        text = job.worktree.joinpath(REL).read_text()
        start = text.index("## Issue")
        self.assertIn("`````text\n", text[start:])
        fenced = text[start : text.index("## Plan")]
        self.assertIn("<script>alert(1)</script>", fenced)
        self.assertIn("\n# not a heading", fenced)


class HistoryOff(HistoryTestCase):
    config_overrides: ClassVar[dict[str, Any]] = {"history_dir": ""}

    def test_no_commit_when_history_dir_is_empty(self) -> None:
        job = self.to_ready()
        self.assertEqual(job.stage, "ready")
        self.assertNotIn(f"docs(history): {job.id}", self.log_subjects(job.worktree))
        self.assertFalse(job.worktree.joinpath("docs").exists())


class SpecTicket(HistoryTestCase):
    def test_history_reaches_the_spec_branch_on_merge(self) -> None:
        job = self.start(self.make_spec_ticket())
        self.write_plan(job)
        job = self.advance(job)
        self.build_feature(job)
        job = self.advance(job)
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job)
        job = self.advance(job)
        self.assertEqual(job.stage, "merging")
        out = machine.merge(self.ctx, job)
        self.assertIn("merging -> done", out)
        text = self.remote_file("spec/010-blog", REL)
        self.assertIn('stage: "merging"', text)
        self.assertIn('spec: "010-blog"', text)
        self.assertIn("[010-blog](010-blog.md)", text)


class SpecJob(HistoryTestCase):
    def test_spec_history_lists_its_tickets_and_is_in_the_pr(self) -> None:
        self.add_issue(20, title="Text stats", body="The spec.", labels=["ready-for-agent", "spec"])
        self.add_issue(21, title="Ticket 21", body="Do it.\n\nParent: #20\n")
        spec.create(self.ctx, 20)
        t = self.start(self.job(21))
        self.write_plan(t)
        t = self.advance(t)
        self.build_feature(t)
        t = self.advance(t)
        self.write_checks(t)
        t = self.advance(t)
        self.write_review(t)
        t = self.advance(t)
        machine.merge(self.ctx, t)
        s = self.job(20)
        self.assertEqual(s.stage, "final-review")
        self.write_checks(s)
        self.write_review(s)
        machine.advance(self.ctx, s)
        s = self.job(20)
        self.assertEqual(s.stage, "ready")
        text = self.remote_file(s["branch"], f"docs/history/{s.id}.md")
        self.assertIn("## Tickets", text)
        self.assertIn(f"- [#21 Ticket 21]({t.id}.md) · done · 1 rounds", text)
        self.assertIn("| final-review | ready | FINAL PASS |", text)
        # the ticket's own history came along with its merge
        self.remote_file(s["branch"], f"docs/history/{t.id}.md")


class Backfill(HistoryTestCase):
    def test_cli_writes_uncommitted_files_for_jobs_with_a_pr(self) -> None:
        self.to_ready()
        self.new_job(13, title="Without PR")
        res = self.run_cli("job", "history")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f"012-reading-time -> {REL}", res.stdout)
        self.assertNotIn("013", res.stdout)
        self.assertTrue((self.root / REL).exists())
        self.assertIn(REL.split("/")[0], self.git(self.root, "status", "--porcelain"))

    def test_render_without_pending_uses_events_log(self) -> None:
        job = self.to_ready()
        text = history.render(job)
        self.assertIn("| review | ready | PASS |", text)
        self.assertEqual(text.count("| review | ready |"), 1)


class HistoryConfig(unittest.TestCase):
    def base(self) -> dict[str, object]:
        data: dict[str, object] = json.loads(json.dumps(CONFIG))
        return data

    def test_missing_key_is_allowed(self) -> None:
        config.validate(self.base())

    def test_rejects_paths_outside_the_repo(self) -> None:
        for bad in ("../docs", "/abs"):
            data = self.base()
            data["history_dir"] = bad
            with self.assertRaisesRegex(ConfigError, "history_dir"):
                config.validate(data)

    def test_rejects_wrong_type(self) -> None:
        data = self.base()
        data["history_dir"] = 3
        with self.assertRaisesRegex(ConfigError, "history_dir"):
            config.validate(data)


class Fence(unittest.TestCase):
    def test_fence_outgrows_backticks_inside(self) -> None:
        self.assertTrue(history.fence("a ```` b").startswith("`````text\n"))
        self.assertTrue(history.fence("plain").startswith("```text\n"))

    def test_demote_skips_code_fences(self) -> None:
        self.assertEqual(
            history.demote("## A\n```\n# code\n```\n### B", 2), "#### A\n```\n# code\n```\n##### B"
        )


if __name__ == "__main__":
    unittest.main()
