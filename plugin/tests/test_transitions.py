"""One test per legal ticket transition (DESIGN.md table) plus illegal ones per state."""

from __future__ import annotations

import unittest

from helpers import QUEUE, FactoryTestCase
from lib import machine
from lib.jobs import TICKET_STAGES
from lib.util import FactoryError


class IntakeTransitions(FactoryTestCase):
    def test_intake_to_build_on_accept(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "ACCEPT", risk="high", surfaces="ui, api")
        job = self.advance(job)
        self.assertEqual(job.stage, "build")
        self.assertEqual(job["risk"], "high")
        self.assertEqual(job["surfaces"], ["ui", "api"])
        self.assertEqual(job["models"], {"builder": "opus", "reviewer": "sonnet"})
        self.assertIsNone(job["claim"])
        self.assertIn("factory:working", self.labels(12))
        comment = self.comments(12)[-1]
        self.assertTrue(comment.startswith(f"[factory] {job.id}"))
        self.assertIn("Add sub()", comment)
        self.assertIn("C1: sub(3, 1) == 2", comment)
        self.assertIn("intake\tbuild\tACCEPT", job.file("events.log").read_text())

    def test_intake_to_needs_info(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "NEEDS-INFO")
        job = self.advance(job)
        self.assertEqual(job.stage, "needs-info")
        self.assertIn("needs-info", self.labels(12))
        self.assertIn("¿Enteros o floats?", self.comments(12)[-1])
        self.assertIsNotNone(job["asked_at"])

    def test_intake_to_rejected(self) -> None:
        job = self.start(self.new_job(12))
        self.assertTrue(job.worktree.is_dir())
        self.write_plan(job, "REJECT")
        job = self.advance(job)
        self.assertEqual(job.stage, "rejected")
        self.assertNotIn(QUEUE, self.labels(12))
        self.assertIn("Fuera de alcance", self.comments(12)[-1])
        self.assertFalse(job.worktree.exists())

    def test_intake_to_needs_human_after_two_contract_failures(self) -> None:
        job = self.start(self.new_job(12))
        self.write(job.dir, "plan.md", "DECISION: MAYBE\n")
        with self.assertRaises(FactoryError) as first:
            self.advance(job)
        self.assertIn("plan.md:1", str(first.exception))
        self.assertIn("contract failure 1", job.file("events.log").read_text())
        self.assertEqual(self.job(12).stage, "intake")
        # the orchestrator re-sends the error to the planner once; it fails again
        job = self.advance(job)
        self.assertEqual(job.stage, "needs-human")
        self.assertIn("ready-for-human", self.labels(12))


class NeedsInfoTransitions(FactoryTestCase):
    def _needs_info(self):  # type: ignore[no-untyped-def]
        job = self.start(self.new_job(12))
        self.write_plan(job, "NEEDS-INFO")
        return self.advance(job)

    def test_needs_info_to_intake_on_human_answer(self) -> None:
        job = self._needs_info()
        self.human_comment(12, "Enteros, por favor.")
        job = self.advance(job)
        self.assertEqual(job.stage, "intake")
        self.assertNotIn("needs-info", self.labels(12))
        self.assertIn("Enteros, por favor.", job.file("issue.md").read_text())
        self.assertFalse(job.file("plan.md").exists())
        self.assertTrue(job.file("plan.needs-info-1.md").exists())

    def test_needs_info_ignores_factory_comments(self) -> None:
        job = self._needs_info()
        self.gh.comment(12, "[factory] something else")
        with self.assertRaises(FactoryError):
            self.advance(job)
        self.assertEqual(self.job(12).stage, "needs-info")

    def test_queue_picks_up_answer(self) -> None:
        self._needs_info()
        self.human_comment(12, "Enteros.")
        out = machine.queue(self.ctx)
        self.assertTrue(any("needs-info -> intake" in line for line in out), out)


class BuildTransitions(FactoryTestCase):
    def test_build_to_gate_pushes_and_opens_draft_pr(self) -> None:
        job = self.to_build()
        self.build_feature(job)
        job = self.advance(job)
        self.assertEqual(job.stage, "gate")
        self.assertEqual(job["round"], 1)
        self.assertTrue(job.round_dir(1).is_dir())
        self.assertIn(job["branch"], self.remote_branches())
        self.assertIsNotNone(job["pushed_at"])
        [created] = self.ops("create_pr")
        self.assertTrue(created["draft"])
        self.assertEqual(created["base"], "main")
        self.assertEqual(job["pr"], created["number"])
        self.assertIn("Closes #12", self.gh.pr(job["pr"])["body"])

    def test_build_to_gate_requires_clean_tree_and_a_commit(self) -> None:
        job = self.to_build()
        self.write_build(job)
        with self.assertRaisesRegex(FactoryError, r"(?s)no commits.*send this error back"):
            self.advance(job)
        self.assertEqual(self.job(12).stage, "build")
        self.write(job.worktree, "dirty.txt", "x")
        job = self.advance(job)  # second contract failure escalates
        self.assertEqual(job.stage, "needs-human")

    def test_second_round_reuses_pr(self) -> None:
        job = self.to_gate()
        self.write_checks(job, "FAIL")
        job = self.advance(job)
        self.commit(
            job.worktree,
            "mod.py",
            "def add(a, b):\n    return b + a\n\n\ndef sub(a, b):\n    return a - b\n",
        )
        self.write_build(job)
        job = self.advance(job)
        self.assertEqual((job.stage, job["round"]), ("gate", 2))
        self.assertEqual(len(self.ops("create_pr")), 1)

    def test_build_to_needs_human_when_blocked(self) -> None:
        job = self.to_gate()
        self.write_checks(job, "FAIL")
        job = self.advance(job)
        self.write_build(job, status="BLOCKED")
        job = self.advance(job)
        self.assertEqual(job.stage, "needs-human")
        self.assertIn("ready-for-human", self.labels(12))
        self.assertIn("firma de add()", self.comments(12)[-1])
        self.assertIn("firma de add()", self.comments(job["pr"])[-1])


class GateTransitions(FactoryTestCase):
    def test_gate_to_review_on_pass(self) -> None:
        job = self.to_gate()
        self.write_checks(job, "PASS")
        self.assertEqual(self.advance(job).stage, "review")

    def test_gate_to_build_on_fail_with_rounds_left(self) -> None:
        job = self.to_gate()
        self.write_checks(job, "FAIL")
        job = self.advance(job)
        self.assertEqual(job.stage, "build")
        self.assertEqual(job["feedback"], f"factory/jobs/{job.id}/round-1/checks.md")
        self.assertFalse(job.file("build.md").exists())
        self.assertTrue((job.round_dir(1) / "build.md").exists())

    def test_gate_to_needs_human_on_last_round(self) -> None:
        job = self.to_gate()
        job["round"] = 3
        job.save()
        self.write_checks(self.job(), "FAIL")
        job = self.advance(job)
        self.assertEqual(job.stage, "needs-human")
        self.assertIn("ready-for-human", self.labels(12))

    def test_gate_without_checks_file_is_condition_not_met(self) -> None:
        job = self.to_gate()
        with self.assertRaisesRegex(FactoryError, "checks.md not found"):
            self.advance(job)


class ReviewTransitions(FactoryTestCase):
    def test_review_to_build_on_changes(self) -> None:
        job = self.to_review()
        self.write_review(job, "CHANGES")
        job = self.advance(job)
        self.assertEqual(job.stage, "build")
        self.assertTrue(job["feedback"].endswith("round-1/review.md"))

    def test_review_to_needs_human_on_changes_last_round(self) -> None:
        job = self.to_review()
        job["round"] = 3
        job.save()
        self.write_review(self.job(), "CHANGES")
        self.assertEqual(self.advance(job).stage, "needs-human")

    def test_review_to_ready_for_standalone_ticket(self) -> None:
        job = self.to_review()
        self.write_review(job, "PASS")
        job = self.advance(job)
        self.assertEqual(job.stage, "ready")
        self.assertFalse(self.gh.pr(job["pr"])["draft"])
        self.assertIn("ready-for-human", self.labels(12))
        self.assertIn("listo para un humano", self.comments(12)[-1])

    def test_review_to_merging_for_spec_ticket(self) -> None:
        job = self.start(self.make_spec_ticket())
        self.write_plan(job)
        job = self.advance(job)
        self.build_feature(job)
        job = self.advance(job)
        self.assertEqual(self.ops("create_pr"), [])  # spec tickets have no draft PR
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job)
        self.assertEqual(self.advance(job).stage, "merging")

    def test_review_to_ready_for_spec_ticket_on_always_human_surface(self) -> None:
        job = self.start(self.make_spec_ticket())
        self.write_plan(job, surfaces="payments")
        job = self.advance(job)
        self.build_feature(job)
        job = self.advance(job)
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job)
        job = self.advance(job)
        self.assertEqual(job.stage, "ready")
        [created] = self.ops("create_pr")
        self.assertEqual((created["base"], created["draft"]), ("spec/010-blog", False))
        self.assertEqual(job["pr"], created["number"])


class MergingTransitions(FactoryTestCase):
    def _merging(self):  # type: ignore[no-untyped-def]
        job = self.start(self.make_spec_ticket())
        self.write_plan(job)
        job = self.advance(job)
        self.build_feature(job)
        job = self.advance(job)
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job)
        return self.advance(job)

    def test_merging_to_done_fast_forwards_spec_branch(self) -> None:
        job = self._merging()
        head = self.git(job.worktree, "rev-parse", "HEAD").strip()
        out = machine.merge(self.ctx, job)
        self.assertIn("merging -> done", out)
        job = self.job()
        spec_head = self.git(self.origin, "rev-parse", "spec/010-blog").strip()
        self.assertEqual(spec_head, head)
        self.assertNotIn(job["branch"], self.remote_branches())
        self.assertFalse(job.worktree.exists())
        self.assertEqual(self.gh.load()["issues"]["12"]["state"], "CLOSED")
        self.assertNotIn("factory:working", self.labels(12))
        self.assertTrue((job.round_dir(1) / "merge-checks.md").exists())

    def _advance_spec(self, rel: str, content: str) -> None:
        other = self.tmp / "other"
        self.git(self.tmp, "clone", "--quiet", "-b", "spec/010-blog", str(self.origin), str(other))
        self.commit(other, rel, content, "another ticket")
        self.git(other, "push", "--quiet", "origin", "spec/010-blog")

    def test_merging_to_build_on_conflict(self) -> None:
        job = self._merging()
        self._advance_spec(
            "mod.py",
            "def add(a, b):\n    return a + b + 0\n\n\ndef sub(a, b):\n    return -(b - a)\n",
        )
        out = machine.merge(self.ctx, job)
        self.assertIn("merging -> build", out)
        job = self.job()
        merge_md = (job.round_dir(1) / "merge.md").read_text()
        self.assertIn("- mod.py", merge_md)
        self.assertTrue(job["feedback"].endswith("round-1/merge.md"))
        self.assertTrue(self.git(job.worktree, "status", "--porcelain") == "")

    def test_merging_to_build_when_gate_red_after_merge(self) -> None:
        job = self._merging()
        self._advance_spec("helper.py", "raise RuntimeError('broken import')\n")
        self.commit(
            self.tmp / "other", "tests/test_helper.py", "import helper  # noqa\n", "bad test"
        )
        self.git(self.tmp / "other", "push", "--quiet", "origin", "spec/010-blog")
        out = machine.merge(self.ctx, job)
        self.assertIn("merging -> build", out)
        self.assertIn("GATE-FAIL", (self.job().round_dir(1) / "merge.md").read_text())

    def test_merging_to_needs_human_when_no_rounds_left(self) -> None:
        job = self._merging()
        job["round"] = 3
        job.save()
        self._advance_spec("mod.py", "def add(a, b):\n    return 0\n")
        out = machine.merge(self.ctx, self.job())
        self.assertIn("merging -> needs-human", out)


class HumanTransitions(FactoryTestCase):
    def _ready(self):  # type: ignore[no-untyped-def]
        job = self.to_review()
        self.write_review(job, "PASS")
        return self.advance(job)

    def test_ready_to_build_on_rework(self) -> None:
        job = self._ready()
        self.human_comment(job["pr"], "Renombra sub a subtract.", author="bob")
        out = machine.rework(self.ctx, self.job())
        self.assertIn("ready -> build", out)
        job = self.job()
        rework = job.file("rework-1.md").read_text()
        self.assertIn("Renombra sub a subtract.", rework)
        self.assertIn("@bob", rework)
        self.assertEqual(job["feedback"], f"factory/jobs/{job.id}/rework-1.md")
        self.assertNotIn("ready-for-human", self.labels(12))

    def test_needs_human_to_build_on_rework(self) -> None:
        job = self.to_build()
        self.write_build(job, status="BLOCKED")
        job = self.advance(job)
        self.human_comment(12, "Sí, cámbiala.")
        machine.rework(self.ctx, job)
        self.assertEqual(self.job().stage, "build")

    def test_needs_human_to_intake_on_rework_without_plan(self) -> None:
        job = self.start(self.new_job(12))
        self.write(job.dir, "plan.md", "nonsense\n")
        for _ in range(2):
            try:
                self.advance(job)
            except FactoryError:
                pass
        self.assertEqual(self.job().stage, "needs-human")
        self.human_comment(12, "Aclaro: solo enteros.")
        machine.rework(self.ctx, self.job())
        self.assertEqual(self.job().stage, "intake")

    def test_rework_without_new_comments_fails(self) -> None:
        self._ready()
        with self.assertRaisesRegex(FactoryError, "no human comments"):
            machine.rework(self.ctx, self.job())

    def test_ready_to_done_when_pr_merged(self) -> None:
        job = self._ready()
        self.merge_pr(job["pr"])
        job = self.advance(job)
        self.assertEqual(job.stage, "done")
        self.assertFalse(job.worktree.exists())
        self.assertEqual(self.labels(12), [])
        self.assertNotIn(job["branch"], self.remote_branches())
        self.assertNotIn(job["branch"], self.git(self.root, "branch", "--list"))

    def test_needs_human_to_done_when_pr_merged(self) -> None:
        job = self.to_gate()
        job["round"] = 3
        job.save()
        self.write_checks(self.job(), "FAIL")
        job = self.advance(job)
        self.assertEqual(job.stage, "needs-human")
        self.merge_pr(job["pr"])
        self.assertEqual(self.advance(job).stage, "done")


class IllegalTransitions(FactoryTestCase):
    def test_every_state_rejects_an_unlisted_target(self) -> None:
        illegal = {
            "intake": "done",
            "needs-info": "build",
            "rejected": "intake",
            "build": "review",
            "gate": "merging",
            "review": "gate",
            "merging": "ready",
            "ready": "merging",
            "needs-human": "review",
            "done": "build",
        }
        self.assertEqual(set(illegal), set(TICKET_STAGES))
        for frm, to in illegal.items():
            with self.subTest(frm=frm), self.assertRaisesRegex(FactoryError, "illegal transition"):
                machine.check_legal(frm, to)

    def test_terminal_states_do_not_advance(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "REJECT")
        job = self.advance(job)
        with self.assertRaisesRegex(FactoryError, "terminal"):
            self.advance(job)

    def test_commands_refuse_wrong_stage(self) -> None:
        job = self.to_build()
        with self.assertRaisesRegex(FactoryError, "rework is only possible"):
            machine.rework(self.ctx, job)
        with self.assertRaisesRegex(FactoryError, "needs stage 'merging'"):
            machine.merge(self.ctx, job)

    def test_merging_does_not_advance(self) -> None:
        job = self.to_build()
        job["stage"] = "merging"
        job.save()
        with self.assertRaisesRegex(FactoryError, "job merge"):
            self.advance(job)

    def test_ready_without_merged_pr_does_not_advance(self) -> None:
        job = self.to_review()
        self.write_review(job)
        job = self.advance(job)
        with self.assertRaisesRegex(FactoryError, "waiting for a human"):
            self.advance(job)

    def test_failed_effect_keeps_state(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "ACCEPT")
        state = self.gh.load()
        del state["issues"]["12"]  # GitHub effect will fail
        self.gh.save(state)
        with self.assertRaisesRegex(FactoryError, "job stays in 'intake'"):
            self.advance(job)
        self.assertEqual(self.job().stage, "intake")


if __name__ == "__main__":
    unittest.main()
