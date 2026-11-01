"""bin/gate: checks.sh from origin/main, protected paths, evidence."""

from __future__ import annotations

import unittest

from helpers import FactoryTestCase
from lib import contracts, gate


class GateTest(FactoryTestCase):
    def _gate_job(self):  # type: ignore[no-untyped-def]
        return self.to_gate()

    def _run(self, job):  # type: ignore[no-untyped-def]
        result = gate.run_gate(self.cfg, self.job(job["issue"]))
        doc = contracts.read_checks(job.round_dir() / "checks.md")
        return result, doc

    def _recommit(self, job, rel: str, content: str) -> None:  # type: ignore[no-untyped-def]
        self.commit(job.worktree, rel, content, "more")

    def test_passes_on_clean_worktree(self) -> None:
        job = self._gate_job()
        result, doc = self._run(job)
        self.assertTrue(result.passed, (job.round_dir() / "checks.md").read_text())
        self.assertEqual((doc["GATE"], doc["PROTECTED"]), ("PASS", "none"))

    def test_cli_exit_codes(self) -> None:
        job = self._gate_job()
        ok = self.run_cli("gate", job.id)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        # different size than before: same-size rewrites within a second can hit a stale .pyc
        self._recommit(
            job,
            "mod.py",
            "def add(a, b):\n    return a - b - 1\n\n\ndef sub(a, b):\n    return a - b\n",
        )
        bad = self.run_cli("gate", job.id)
        self.assertEqual(bad.returncode, 1, bad.stderr)

    def test_fails_with_broken_test(self) -> None:
        job = self._gate_job()
        self._recommit(
            job,
            "mod.py",
            "def add(a, b):\n    return a * b * 10\n\n\ndef sub(a, b):\n    return a - b\n",
        )
        result, doc = self._run(job)
        self.assertFalse(result.passed)
        self.assertEqual(doc["GATE"], "FAIL")
        self.assertIn("FAILED", (job.round_dir() / "checks.md").read_text())

    def test_fails_when_protected_file_modified(self) -> None:
        job = self._gate_job()
        self._recommit(job, "tests/test_mod.py", "import unittest\n")  # weakening an existing test
        result, doc = self._run(job)
        self.assertFalse(result.passed)
        self.assertEqual(doc["PROTECTED"], "tests/test_mod.py")

    def test_fails_when_protected_file_deleted_or_renamed(self) -> None:
        job = self._gate_job()
        self.git(job.worktree, "mv", "tests/test_mod.py", "test_mod_moved.py")
        self.git(job.worktree, "commit", "--quiet", "-m", "move")
        result, doc = self._run(job)
        self.assertFalse(result.passed)
        self.assertIn("tests/test_mod.py", doc["PROTECTED"])

    def test_passes_when_only_adding_file_matching_protected_glob(self) -> None:
        job = self._gate_job()  # build_feature already adds tests/test_sub.py
        result, doc = self._run(job)
        self.assertTrue(result.passed)
        self.assertEqual(doc["PROTECTED"], "none")

    def test_fails_when_evidence_file_missing(self) -> None:
        job = self._gate_job()
        self.write_build(job, evidence="C1: tests/test_nope.py::test_sub — does not exist")
        result, _ = self._run(job)
        self.assertFalse(result.passed)
        self.assertIn("file not found", "\n".join(result.evidence_problems))

    def test_fails_when_evidence_name_missing(self) -> None:
        job = self._gate_job()
        self.write_build(job, evidence="C1: tests/test_sub.py::test_imaginary — not there")
        result, _ = self._run(job)
        self.assertFalse(result.passed)
        self.assertIn("does not appear", "\n".join(result.evidence_problems))

    def test_fails_when_plan_criterion_has_no_evidence(self) -> None:
        job = self._gate_job()
        plan = job.file("plan.md")
        plan.write_text(
            plan.read_text().replace(
                "- C1: sub(3, 1) == 2", "- C1: sub(3, 1) == 2\n- C2: sub is exported"
            )
        )
        result, _ = self._run(job)
        self.assertFalse(result.passed)
        self.assertIn("C2 — no evidence", "\n".join(result.evidence_problems))

    def test_rejects_evidence_outside_worktree(self) -> None:
        job = self._gate_job()
        self.write_build(job, evidence="C1: ../../../../etc/hosts::localhost — escape")
        result, _ = self._run(job)
        self.assertFalse(result.passed)
        self.assertIn("relative to the worktree", "\n".join(result.evidence_problems))

    def test_uses_checks_sh_from_origin_main_not_from_branch(self) -> None:
        job = self._gate_job()
        self._recommit(
            job, "factory/checks.sh", "#!/usr/bin/env bash\necho BRANCH-CHECKS\nexit 0\n"
        )
        self._recommit(
            job, "mod.py", "def add(a, b):\n    return 0\n\n\ndef sub(a, b):\n    return a - b\n"
        )
        result, doc = self._run(job)
        text = (job.round_dir() / "checks.md").read_text()
        self.assertIn("MAIN-CHECKS", text)
        self.assertNotIn("BRANCH-CHECKS", text)
        self.assertNotEqual(result.returncode, 0)  # main's checks ran the (broken) tests
        self.assertEqual(doc["GATE"], "FAIL")
        self.assertIn("factory/checks.sh", doc["PROTECTED"])

    def test_timeout_is_a_failure(self) -> None:
        job = self._gate_job()
        self.cfg.data["checks_timeout_s"] = 1
        self.write(
            self.root, "factory/checks.sh", "#!/usr/bin/env bash\nsleep 5\n", executable=True
        )
        self.git(self.root, "commit", "--quiet", "-am", "slow checks")
        self.git(self.root, "push", "--quiet", "origin", "main")
        result, doc = self._run(job)
        self.assertTrue(result.timed_out)
        self.assertEqual(doc["GATE"], "FAIL")

    def test_gate_refuses_job_not_in_gate_stage(self) -> None:
        job = self.to_build()
        res = self.run_cli("gate", job.id)
        self.assertEqual(res.returncode, 2)
        self.assertIn("stage 'gate'", res.stderr)

    def test_full_cycle_gate_then_advance(self) -> None:
        job = self._gate_job()
        self.assertEqual(self.run_cli("gate", job.id).returncode, 0)
        res = self.run_cli("job", "advance", job.id)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("gate -> review", res.stdout)


if __name__ == "__main__":
    unittest.main()
