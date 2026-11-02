"""Pure units: globs, contracts parsing, evidence lines, issue line parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sets sys.path)
from lib import contracts, issue
from lib.util import matches_any


class GlobTest(unittest.TestCase):
    def test_double_star(self) -> None:
        self.assertTrue(matches_any("factory/bin/job", ["factory/**"]))
        self.assertTrue(matches_any("tests/a/b/test_x.py", ["tests/**"]))
        self.assertFalse(matches_any("src/tests/x.py", ["tests/**"]))
        self.assertTrue(matches_any("src/tests/x.py", ["**/tests/**"]))
        self.assertTrue(matches_any("x.py", ["**/*.py"]))

    def test_single_star_does_not_cross_dirs(self) -> None:
        self.assertTrue(matches_any("docs/a.md", ["docs/*.md"]))
        self.assertFalse(matches_any("docs/adr/a.md", ["docs/*.md"]))


class ContractTest(unittest.TestCase):
    def _doc(self, text: str) -> Path:
        d = Path(tempfile.mkdtemp())
        p = d / "plan.md"
        p.write_text(text)
        return p

    def test_unknown_and_duplicated_keys(self) -> None:
        with self.assertRaisesRegex(
            contracts.ContractError, r"plan.md:2: unknown header key 'MOOD'"
        ):
            contracts.parse(self._doc("DECISION: ACCEPT\nMOOD: happy\n"), contracts.PLAN)
        with self.assertRaisesRegex(contracts.ContractError, r"plan.md:2: duplicated"):
            contracts.parse(self._doc("DECISION: ACCEPT\nDECISION: REJECT\n"), contracts.PLAN)

    def test_header_must_start_at_line_one(self) -> None:
        with self.assertRaisesRegex(
            contracts.ContractError, r"plan.md:1: missing required header line 'DECISION"
        ):
            contracts.parse(self._doc("\nDECISION: ACCEPT\n"), contracts.PLAN)

    def test_surfaces_syntax(self) -> None:
        ok = self._doc("DECISION: REJECT\nRISK: low\nSURFACES: ui, api\n\n## Motivo\n\nx\n")
        self.assertEqual(contracts.surfaces(contracts.read_plan(ok)), ["ui", "api"])
        bad = self._doc("DECISION: REJECT\nRISK: low\nSURFACES: UI & api\n")
        with self.assertRaisesRegex(contracts.ContractError, "plan.md:3: SURFACES"):
            contracts.read_plan(bad)

    def test_required_sections_per_decision(self) -> None:
        p = self._doc("DECISION: NEEDS-INFO\nRISK: low\nSURFACES: none\n\n## Alcance\n\nx\n")
        with self.assertRaisesRegex(contracts.ContractError, "## Pregunta"):
            contracts.read_plan(p)
        p = self._doc(
            "DECISION: ACCEPT\nRISK: low\nSURFACES: none\n\n## Alcance\n\nx\n\n"
            "## Criterios de aceptación\n\nwords only\n\n## Seams\n\nx\n"
        )
        with self.assertRaisesRegex(contracts.ContractError, "has no criteria"):
            contracts.read_plan(p)

    def test_evidence_lines(self) -> None:
        ev, bad = contracts.parse_evidence(
            "C1: tests/test_a.py::test_x — shows x\n- C2: `tests/b.py::TestB` - shows y\nC3 is covered somewhere\n"
        )
        self.assertEqual(
            [(e.criterion, e.path, e.name) for e in ev],
            [("C1", "tests/test_a.py", "test_x"), ("C2", "tests/b.py", "TestB")],
        )
        self.assertEqual(bad, ["C3 is covered somewhere"])


class IssueLinesTest(unittest.TestCase):
    def test_parent_and_blocked_by(self) -> None:
        body = "Something\n\nParent: #10\nBlocked by: #11, #12\n"
        self.assertEqual(issue.parent_of(body), 10)
        self.assertEqual(issue.blocked_by(body), [11, 12])
        self.assertIsNone(issue.parent_of("no parent"))


if __name__ == "__main__":
    unittest.main()
