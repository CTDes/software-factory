"""Evidence lines in build.md: test names with spaces, and checks at `advance` (0.4.1)."""

from __future__ import annotations

import unittest

from helpers import FactoryTestCase
from lib import contracts, gate, prompts
from lib.util import FactoryError


class EvidenceLineFormat(unittest.TestCase):
    def parse(self, line: str) -> list[tuple[str, str, str]]:
        found, bad = contracts.parse_evidence(line)
        self.assertEqual(bad, [], line)
        return [(e.criterion, e.path, e.name) for e in found]

    def test_bare_and_fully_quoted_forms_still_parse(self) -> None:
        self.assertEqual(
            self.parse("- C1: tests/test_sub.py::test_sub — sub(3, 1) == 2"),
            [("C1", "tests/test_sub.py", "test_sub")],
        )
        self.assertEqual(
            self.parse("C2: `tests/test_sub.py::SubTest.test_sub` -- dotted"),
            [("C2", "tests/test_sub.py", "SubTest.test_sub")],
        )

    def test_names_with_spaces_go_in_backticks(self) -> None:
        line = (
            "- C1: tests/js/hats.test.js::`hatModel: the claim's model wins` — claim beats models"
        )
        self.assertEqual(
            self.parse(line), [("C1", "tests/js/hats.test.js", "hatModel: the claim's model wins")]
        )
        self.assertEqual(
            self.parse("C3: tests/js/a.test.js::`palette: hats [ok]`"),
            [("C3", "tests/js/a.test.js", "palette: hats [ok]")],
        )

    def test_spaces_without_backticks_are_malformed(self) -> None:
        found, bad = contracts.parse_evidence(
            "- C1: tests/js/hats.test.js::hatModel: the claim's model wins — x"
        )
        self.assertEqual(found, [])
        self.assertEqual(len(bad), 1)


JS_TEST = (
    'const test = require("node:test");\n'
    'test("hatModel: the claim\'s model wins over models[role]", () => {});\n'
)


class EvidenceAtAdvance(FactoryTestCase):
    def build_js(self, evidence: str) -> None:
        job = self.to_build(12)
        self.commit(job.worktree, "tests/js/hats.test.js", JS_TEST, "C1: js test")
        self.write_build(job, evidence=evidence)

    def test_js_name_with_spaces_passes_advance_and_gate_evidence(self) -> None:
        self.build_js(
            "- C1: tests/js/hats.test.js::`hatModel: the claim's model wins over models[role]` — x"
        )
        job = self.advance(self.job(12))
        self.assertEqual(job.stage, "gate")
        self.assertEqual(gate.check_evidence(job, job.worktree), [])

    def test_malformed_evidence_is_a_contract_failure_not_a_gate_round(self) -> None:
        self.build_js("- C1: tests/js/hats.test.js::hatModel: the claim's model wins — x")
        before = self.job(12)["round"]
        with self.assertRaisesRegex(FactoryError, "evidence the gate would reject") as caught:
            self.advance(self.job(12))
        self.assertIn("malformed evidence line", str(caught.exception))
        self.assertIn("send this error back to the same agent", str(caught.exception))
        job = self.job(12)
        self.assertEqual(job.stage, "build")
        self.assertEqual(job["round"], before)
        self.assertEqual(job["contract_failures"], 1)

    def test_missing_name_and_uncovered_criterion_come_back_to_the_builder(self) -> None:
        self.build_js("- C2: tests/js/hats.test.js::`no such test` — x")
        with self.assertRaises(FactoryError) as caught:
            self.advance(self.job(12))
        message = str(caught.exception)
        self.assertIn("C1 — no evidence for this plan criterion", message)
        self.assertIn("'no such test' does not appear", message)
        self.assertEqual(self.job(12).stage, "build")

    def test_second_evidence_failure_escalates_like_any_contract_failure(self) -> None:
        self.build_js("- C1: tests/js/hats.test.js::`nope` — x")
        with self.assertRaises(FactoryError):
            self.advance(self.job(12))
        job = self.advance(self.job(12))
        self.assertEqual(job.stage, "needs-human")


class ReviewerPromptSurfaces(FactoryTestCase):
    def test_lists_surfaces_and_says_when_security_review_is_required(self) -> None:
        job = self.to_build(12)
        job["surfaces"] = ["ui"]
        text = prompts.review(job)
        self.assertIn("Surfaces: ui · security review: not required", text)
        job["surfaces"] = ["api", "security"]
        self.assertIn("security review: required, include ## Security", prompts.review(job))


if __name__ == "__main__":
    unittest.main()
