"""Spec level: graph validation, scheduling over the graph, final gate/review, PR to main."""

from __future__ import annotations

import unittest

from helpers import QUEUE, FactoryTestCase
from lib import gate, jobs, machine, spec
from lib.util import FactoryError

SPEC = 20
A, B, C, D, E = 21, 22, 23, 24, 25


class SpecTestCase(FactoryTestCase):
    def add_spec(self, number: int = SPEC, labels: list[str] | None = None) -> None:
        self.add_issue(
            number, title="Estadísticas de texto", body="La spec.", labels=labels or [QUEUE, "spec"]
        )

    def add_child(
        self,
        number: int,
        blocked: list[int] = (),
        parent: int = SPEC,  # type: ignore[assignment]
        labels: list[str] | None = None,
        title: str | None = None,
    ) -> None:
        body = f"Hacer {number}.\n\nParent: #{parent}\n"
        if blocked:
            body += "Blocked by: " + ", ".join(f"#{b}" for b in blocked) + "\n"
        self.add_issue(number, title=title or f"Ticket {number}", body=body, labels=labels)

    def five_ticket_spec(self) -> None:
        self.add_spec()
        self.add_child(A)
        self.add_child(B)
        self.add_child(C, [A, B])
        self.add_child(D, [C])
        self.add_child(E)

    def spec_job(self) -> jobs.Job:
        return self.job(SPEC)

    def set_stage(self, number: int, stage: str) -> None:
        j = self.job(number)
        j["stage"] = stage
        j.save()


class CreateTest(SpecTestCase):
    def test_creates_branch_tickets_and_graph_comment(self) -> None:
        self.five_ticket_spec()
        out = spec.create(self.ctx, SPEC)
        self.assertIn("created (building)", out)
        s = self.spec_job()
        self.assertEqual((s["kind"], s.stage, s["branch"]), ("spec", "building", f"spec/{s.id}"))
        self.assertIn(s["branch"], self.remote_branches())
        self.assertEqual(len(s["tickets"]), 5)
        c = self.job(C)
        self.assertEqual((c["spec"], c["base"], c["blocked_by"]), (s.id, s["branch"], [A, B]))
        self.assertEqual(self.job(D)["blocked_by"], [C])
        self.assertIn("| #23 Ticket 23 | #21, #22 |", self.comments(SPEC)[-1])
        self.assertIn("factory:working", self.labels(SPEC))

    def test_rejects_cycle(self) -> None:
        self.add_spec()
        self.add_child(A, [B])
        self.add_child(B, [A])
        with self.assertRaisesRegex(FactoryError, "cycle"):
            spec.create(self.ctx, SPEC)
        self.assertIsNone(jobs.by_issue(self.cfg, SPEC))
        self.assertEqual([b for b in self.remote_branches() if b.startswith("spec/")], [])

    def test_rejects_blocker_outside_spec(self) -> None:
        self.add_spec()
        self.add_child(A, [99])
        with self.assertRaisesRegex(FactoryError, "#99, outside spec #20"):
            spec.create(self.ctx, SPEC)

    def test_rejects_child_without_queue_label(self) -> None:
        self.add_spec()
        self.add_child(A, labels=[])
        with self.assertRaisesRegex(FactoryError, "#21 lacks the 'ready-for-agent' label"):
            spec.create(self.ctx, SPEC)

    def test_requires_spec_and_queue_labels(self) -> None:
        self.add_spec(labels=["spec"])  # human has not approved it yet
        self.add_child(A)
        with self.assertRaisesRegex(FactoryError, "lacks the 'ready-for-agent' label"):
            spec.create(self.ctx, SPEC)

    def test_queue_creates_spec_and_leaves_children_to_it(self) -> None:
        self.five_ticket_spec()
        out = machine.queue(self.ctx)
        self.assertTrue(any("(building)" in line for line in out), out)
        self.assertEqual(len(self.spec_job()["tickets"]), 5)
        self.assertEqual(len([j for j in jobs.all_jobs(self.cfg) if j["kind"] == "ticket"]), 5)

    def test_cli_spec_create(self) -> None:
        self.five_ticket_spec()
        res = self.run_cli("job", "spec", "create", str(SPEC))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.add_spec(30)
        res = self.run_cli("job", "spec", "create", "30")
        self.assertEqual(res.returncode, 1)
        self.assertIn("no open child issues", res.stderr)


class ScheduleTest(SpecTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.five_ticket_spec()
        spec.create(self.ctx, SPEC)
        self.cfg.data["concurrency"] = 2

    def offered(self) -> list[int]:
        return [a["issue"] for a in machine.next_actions(self.ctx)]

    def test_independent_tickets_first_c_waits_for_a_and_b(self) -> None:
        self.assertEqual(self.offered(), [A, B])
        self.cfg.data["concurrency"] = 5
        self.assertEqual(self.offered(), [A, B, E])
        self.set_stage(A, "done")
        self.assertNotIn(C, self.offered())
        self.set_stage(B, "done")
        self.assertIn(C, self.offered())
        self.assertNotIn(D, self.offered())

    def test_needs_human_blocks_only_dependents(self) -> None:
        self.cfg.data["concurrency"] = 5
        self.set_stage(A, "needs-human")
        self.set_stage(B, "done")
        offered = self.offered()
        self.assertNotIn(C, offered)
        self.assertNotIn(D, offered)
        self.assertIn(E, offered)

    def test_only_spec_includes_its_tickets(self) -> None:
        self.add_issue(40, title="Suelto")
        machine.create(self.ctx, 40)
        self.cfg.data["concurrency"] = 9
        only = [a["issue"] for a in machine.next_actions(self.ctx, only=str(SPEC))]
        self.assertEqual(only, [A, B, E])
        self.assertIn(40, self.offered())

    def test_new_child_is_incorporated_by_queue(self) -> None:
        self.add_child(26, [E], title="Hijo nuevo")
        out = machine.queue(self.ctx)
        self.assertTrue(any("026-hijo-nuevo created" in line for line in out), out)
        self.assertEqual(self.job(26)["blocked_by"], [E])
        self.assertIn("026-hijo-nuevo", self.spec_job()["tickets"])
        self.assertIn("tickets nuevos incorporados", self.comments(SPEC)[-1])

    def test_new_child_with_bad_blocker_is_reported_not_added(self) -> None:
        self.add_child(26, [77])
        out = machine.queue(self.ctx)
        self.assertTrue(any("new children not added" in line for line in out), out)
        self.assertIsNone(jobs.by_issue(self.cfg, 26))

    def test_spec_waits_while_tickets_open(self) -> None:
        with self.assertRaisesRegex(FactoryError, "tickets not done yet"):
            machine.advance(self.ctx, self.spec_job())
        self.assertEqual(machine.action_for(self.ctx, self.spec_job()), None)


class FinalTest(SpecTestCase):
    """One-ticket spec driven end to end through the real merge and final gate."""

    def setUp(self) -> None:
        super().setUp()
        self.add_spec()
        self.add_child(A)
        spec.create(self.ctx, SPEC)

    def drive_ticket_to_merging(self) -> jobs.Job:
        job = self.start(self.job(A))
        self.write_plan(job)
        job = self.advance(job)
        self.build_feature(job)
        job = self.advance(job)
        self.write_checks(job)
        job = self.advance(job)
        self.write_review(job)
        return self.advance(job)

    def to_final_review(self) -> jobs.Job:
        self.assertEqual(self.drive_ticket_to_merging().stage, "merging")
        out = machine.merge(self.ctx, self.job(A))
        self.assertIn("building -> final-review", out)
        return self.spec_job()

    def test_last_ticket_merge_moves_spec_to_final_review(self) -> None:
        s = self.to_final_review()
        self.assertEqual((s.stage, s["round"]), ("final-review", 1))
        self.assertTrue(s.worktree.is_dir())
        self.assertTrue((s.worktree / "tests" / "test_sub.py").exists())

    def test_final_gate_then_final_review_then_pr_to_main(self) -> None:
        s = self.to_final_review()
        [a] = machine.next_actions(self.ctx)
        self.assertEqual(
            (a["action"], a["command"]), ("final-gate", f"factory/bin/gate {s.id} --final")
        )
        machine.start(self.ctx, s)
        res = self.run_cli("gate", s.id, "--final")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = machine.advance(self.ctx, self.spec_job())
        self.assertIn("final review pending", out)
        [r] = machine.next_actions(self.ctx)
        self.assertEqual(
            (r["action"], r["agent"], r["model"]), ("final-review", "reviewer", "opus")
        )
        self.assertIn("git diff origin/main...HEAD", r["prompt"])
        self.assertIn("issue de la spec es el criterio", r["prompt"])
        machine.start(self.ctx, self.spec_job())
        self.write_review(self.spec_job(), "PASS")
        out = machine.advance(self.ctx, self.spec_job())
        self.assertIn("final-review -> ready", out)
        s = self.spec_job()
        [pr] = [o for o in self.ops("create_pr") if o["head"] == s["branch"]]
        self.assertEqual((pr["base"], pr["draft"]), ("main", False))
        body = self.gh.pr(s["pr"])["body"]
        self.assertIn(f"Closes #{SPEC}", body)
        self.assertIn("| #21 Ticket 21 | done | 1 | 0 |", body)
        self.assertIn("ready-for-human", self.labels(SPEC))
        # human merges the PR: next queue closes the spec
        self.merge_pr(s["pr"])
        out = machine.queue(self.ctx)
        self.assertTrue(any("ready -> done" in line for line in out), out)
        self.assertNotIn(s["branch"], self.remote_branches())
        self.assertFalse(s.worktree.exists())

    def test_final_gate_fail_goes_to_final_build_and_back(self) -> None:
        s = self.to_final_review()
        self.write_checks(s, "FAIL")
        out = machine.advance(self.ctx, s)
        self.assertIn("final-review -> final-build", out)
        s = self.spec_job()
        [b] = machine.next_actions(self.ctx)
        self.assertEqual((b["action"], b["agent"]), ("final-build", "builder"))
        self.assertIn("round-1/checks.md", b["prompt"])
        self.commit(s.worktree, "notes.md", "fix\n", "final fix")
        self.write_build(s, evidence="C1: tests/test_sub.py::test_sub — still green")
        out = machine.advance(self.ctx, s)
        self.assertIn("final-build -> final-review", out)
        s = self.spec_job()
        self.assertEqual(s["round"], 2)
        head = self.git(s.worktree, "rev-parse", "HEAD").strip()
        self.assertEqual(self.git(self.origin, "rev-parse", s["branch"]).strip(), head)

    def test_final_gate_checks_protected_paths_against_main(self) -> None:
        s = self.to_final_review()
        self.commit(s.worktree, "tests/test_mod.py", "import unittest\n", "weaken")
        result = gate.run_gate(self.cfg, s, final=True)
        self.assertFalse(result.passed)
        self.assertIn("tests/test_mod.py", result.protected)

    def test_final_review_changes_on_last_round_escalates(self) -> None:
        s = self.to_final_review()
        s["round"] = 3
        s.save()
        s = self.spec_job()
        self.write_checks(s, "PASS")
        self.write_review(s, "CHANGES")
        out = machine.advance(self.ctx, s)
        self.assertIn("final-review -> needs-human", out)

    def test_spec_rework_goes_to_final_build(self) -> None:
        s = self.to_final_review()
        self.write_checks(s, "PASS")
        self.write_review(s, "PASS")
        machine.advance(self.ctx, s)
        s = self.spec_job()
        self.human_comment(s["pr"], "Falta un caso.")
        out = machine.rework(self.ctx, s)
        self.assertIn("ready -> final-build", out)

    def test_illegal_spec_transitions(self) -> None:
        for frm, to in [("building", "ready"), ("final-build", "ready"), ("done", "building")]:
            with self.subTest(frm=frm), self.assertRaisesRegex(FactoryError, "illegal"):
                machine.check_legal(frm, to, "spec")

    def test_gate_final_refuses_tickets(self) -> None:
        res = self.run_cli("gate", self.job(A).id, "--final")
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()


class MergeRaceTest(SpecTestCase):
    """Two tickets of the same spec reaching `merging` at once."""

    def setUp(self) -> None:
        super().setUp()
        self.add_spec()
        self.add_child(A)
        self.add_child(E)
        spec.create(self.ctx, SPEC)
        self.cfg.data["concurrency"] = 2
        for n, rel in ((A, "a.py"), (E, "e.py")):
            job = self.start(self.job(n))
            self.write_plan(job)
            job = self.advance(job)
            self.commit(job.worktree, rel, "x = 1\n", f"C1: {rel}")
            self.commit(
                job.worktree,
                f"tests/test_{rel}",
                "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        pass\n",
                "C1: test",
            )
            self.write_build(job, evidence=f"C1: tests/test_{rel}::test_sub — ok")
            job = self.advance(job)
            self.write_checks(job)
            job = self.advance(job)
            self.write_review(job)
            self.assertEqual(self.advance(job).stage, "merging")

    def test_only_one_merge_per_base_is_offered_and_started(self) -> None:
        offered = [a for a in machine.next_actions(self.ctx) if a["action"] == "merge"]
        self.assertEqual([a["issue"] for a in offered], [A])
        machine.start(self.ctx, self.job(A))
        self.assertEqual(machine.next_actions(self.ctx), [])
        with self.assertRaisesRegex(FactoryError, "another merge into spec/"):
            machine.start(self.ctx, self.job(E))

    def test_rejected_push_releases_claim_and_retry_succeeds(self) -> None:
        e = self.job(E)
        stale = self.git(self.root, "rev-parse", f"origin/{e['base']}").strip()
        machine.start(self.ctx, self.job(A))
        machine.merge(self.ctx, self.job(A))
        # E prepared its merge against the old spec head: simulate the race by merging
        # E's worktree against the stale ref, then pushing after A already landed.
        e = self.job(E)
        e["claim"] = {"action": "merge", "at": "now"}
        e.save()
        import lib.git as libgit

        real_fetch = libgit.fetch
        libgit.fetch = lambda root, *refs: None  # E does not see A's push: stale base
        try:
            self.git(e.worktree, "update-ref", f"refs/remotes/origin/{e['base']}", stale)
            self.git(self.root, "update-ref", f"refs/remotes/origin/{e['base']}", stale)
            with self.assertRaisesRegex(FactoryError, "claim released"):
                machine.merge(self.ctx, self.job(E))
        finally:
            libgit.fetch = real_fetch
        e = self.job(E)
        self.assertEqual((e.stage, e["claim"]), ("merging", None))
        self.assertIn("will retry", e.file("events.log").read_text())
        [a] = machine.next_actions(self.ctx)
        self.assertEqual((a["issue"], a["action"]), (E, "merge"))
        machine.start(self.ctx, self.job(E))
        out = machine.merge(self.ctx, self.job(E))
        self.assertIn("merging -> done", out)
        self.assertIn("building -> final-review", out)
