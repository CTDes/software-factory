"""The project wiki built by `factory-job vault` (DESIGN.md · Wiki)."""

from __future__ import annotations

import unittest

from helpers import QUEUE, FactoryTestCase
from lib import vault
from lib.util import FactoryError

ROADMAP = """# Roadmap

Text tools.

## Milestones

### M0 · Bootstrap (by hand) — status: done (PR #3)

### M1 · Text statistics — status: in progress (spec #20)

**Depends on:** M0, see #21.

### M2 · Slugs — status: planned
"""


class VaultTestCase(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.out = self.tmp / "wiki"
        self.add_issue(20, title="Text statistics", body="The spec.", labels=[QUEUE, "spec"])
        self.add_issue(21, title="Char count", body="Count.\n\nParent: #20\n", labels=[QUEUE])
        self.add_issue(
            22,
            title="Text stats <dict>",
            body="Uses #21.\n\nParent: #20\nBlocked by: #21\n",
            labels=[QUEUE, "factory:working"],
        )
        self.add_issue(23, title="Typo", body="Fix it.", labels=["ready-for-human"])

    def build(self) -> list[str]:
        return vault.build(self.cfg, self.gh.all_issues(), self.gh.all_prs(), self.out, "textkit")

    def note(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")


class Structure(VaultTestCase):
    def test_writes_index_board_specs_and_tickets(self) -> None:
        notes = self.build()
        for rel in ("index.md", "board.md", "specs/20.md", "tickets/21.md", "tickets/23.md"):
            self.assertIn(rel, notes)
            self.assertTrue((self.out / rel).is_file(), rel)
        self.assertTrue((self.out / vault.MARKER).exists())

    def test_spec_lists_tickets_and_their_dependency_graph(self) -> None:
        self.build()
        spec = self.note("specs/20.md")
        self.assertIn('title: "#20 Text statistics"', spec)
        self.assertIn("| [#21 Char count](../tickets/21.md) | queued | via spec | - |", spec)
        self.assertIn("```mermaid", spec)
        self.assertIn('t22["#22 Text stats #lt;dict>"]', spec)
        self.assertIn("t21 --> t22", spec)

    def test_ticket_links_its_spec_and_blockers(self) -> None:
        self.build()
        t = self.note("tickets/22.md")
        self.assertIn("**Status:** working", t)
        self.assertIn("**Spec:** [#20 Text statistics](../specs/20.md)", t)
        self.assertIn("**Blocked by:** [#21](21.md)", t)
        self.assertIn("# #22 Text stats &lt;dict>", t)

    def test_board_groups_by_status(self) -> None:
        self.build()
        board = self.note("board.md")
        self.assertLess(board.index("## Working (1)"), board.index("## Needs human (1)"))
        self.assertIn("## Queued (2)", board)
        self.assertIn("| [#23 Typo](tickets/23.md) | ticket | - | - | - |", board)


class Milestones(VaultTestCase):
    def test_roadmap_milestones_link_their_spec(self) -> None:
        self.write(self.root, "docs/roadmap.md", ROADMAP)
        self.build()
        index = self.note("index.md")
        self.assertIn(
            "| M1 · Text statistics | in progress | [#20 · queued](specs/20.md) | - |", index
        )
        self.assertIn("| M0 · Bootstrap (by hand) | done | - | #3 |", index)
        self.assertIn("| M2 · Slugs | planned | - | - |", index)
        self.assertIn("**Milestone:** M1", self.note("specs/20.md"))
        roadmap = self.note("docs/roadmap.md")
        self.assertIn("see [#21](../tickets/21.md)", roadmap)


class Safety(VaultTestCase):
    def test_html_is_escaped_outside_code_only(self) -> None:
        self.add_issue(
            24,
            title="XSS",
            body="<script>alert(1)</script>\n\n```html\n<b>kept</b>\n```\n\nand `<i>` too",
        )
        self.build()
        t = self.note("tickets/24.md")
        self.assertIn("&lt;script>alert(1)&lt;/script>", t)
        self.assertNotIn("<script>", t)
        self.assertIn("<b>kept</b>", t)
        self.assertIn("`<i>`", t)

    def test_script_link_targets_are_defused(self) -> None:
        body = "[a](javascript:alert(1)) [b]( JavaScript:x) ![c](data:text/html,x)\n[d]: vbscript:y"
        self.add_issue(27, title="Links", body=body + "\n\n`[e](javascript:kept)`")
        self.build()
        t = self.note("tickets/27.md")
        self.assertNotRegex(t.split("`[e]")[0], r"(?i)\]\(\s*javascript:|data:text|vbscript:")
        self.assertIn("[a](#unsafe-javascript-alert(1))", t)
        self.assertIn("[d]: #unsafe-vbscript-y", t)
        self.assertIn("`[e](javascript:kept)`", t)

    def test_issue_refs_are_not_linked_inside_code(self) -> None:
        self.add_issue(25, title="Refs", body="See #21 but not `#21` nor #999.")
        self.build()
        t = self.note("tickets/25.md")
        self.assertIn("See [#21](21.md) but not `#21` nor #999.", t)

    def test_refuses_a_folder_it_did_not_make(self) -> None:
        self.write(self.out, "notes.md", "mine")
        with self.assertRaisesRegex(FactoryError, "not empty"):
            self.build()
        self.assertTrue((self.out / "notes.md").exists())

    def test_rebuild_removes_stale_notes(self) -> None:
        self.build()
        self.write(self.out, "tickets/99.md", "stale")
        self.build()
        self.assertFalse((self.out / "tickets/99.md").exists())


class DocsAndHistory(VaultTestCase):
    def test_documents_keep_their_paths_and_history_is_not_a_document(self) -> None:
        self.write(self.root, "docs/adr/0001-x.md", "# ADR 1\n\nAbout #20.\n")
        self.write(self.root, "GLOSSARY.md", "# Glossary\n")
        self.write(self.root, "docs/history/021-char-count.md", "---\nissue: 21\n---\n\n# x\n")
        notes = self.build()
        self.assertIn("docs/adr/0001-x.md", notes)
        self.assertIn("GLOSSARY.md", notes)
        self.assertNotIn("docs/history/021-char-count.md", notes)
        self.assertIn("About [#20](../../specs/20.md).", self.note("docs/adr/0001-x.md"))
        self.assertIn("[adr/0001-x](docs/adr/0001-x.md)", self.note("index.md"))

    def test_history_records_are_linked_both_ways(self) -> None:
        self.write(
            self.root,
            "docs/history/021-char-count.md",
            '---\njob: "021-char-count"\nissue: 21\ntitle: "Char count"\npr: 1000\n'
            'stage: "ready"\nrounds: 2\nupdated: "2026-11-07T10:00:00+01:00"\n---\n\n'
            "# #21 Char count\n\n## Plan\n\n<img src=x onerror=alert(1)>\n",
        )
        self.gh.create_pr("factory/021-char-count", "main", "Char count", "Ticket", draft=True)
        self.build()
        record = self.note("history/021-char-count.md")
        self.assertIn('title: "Record · #21 Char count"', record)
        self.assertIn("Issue note: [#21 Char count](../tickets/21.md)", record)
        self.assertIn("&lt;img src=x", record)
        ticket = self.note("tickets/21.md")
        self.assertIn("**Record:** [021-char-count](../history/021-char-count.md)", ticket)
        self.assertIn("**PR:** [#1000](https://github.com/fake/repo/pull/1000) draft", ticket)
        self.assertIn(
            "[#21 Char count](history/021-char-count.md) · ready · 2 rounds", self.note("index.md")
        )

    def test_closed_with_merged_pr_is_done(self) -> None:
        pr = self.gh.create_pr("factory/023-typo", "main", "Typo", "Closes #23", draft=False)
        self.merge_pr(pr["number"])
        self.gh.close_issue(23)
        self.add_issue(26, title="Won't do", body="no", labels=[])
        self.gh.close_issue(26)
        self.build()
        self.assertIn("**Status:** done", self.note("tickets/23.md"))
        self.assertIn("**Status:** closed", self.note("tickets/26.md"))


class DocLinks(VaultTestCase):
    def test_links_to_repository_files_point_at_the_source(self) -> None:
        self.write(
            self.root,
            "README.md",
            "[license](LICENSE) [design](plugin/DESIGN.md#jobs) [arch](docs/architecture.md)\n"
            "[adr](docs/adr/) [web](https://example.org) [top](#x) `[code](LICENSE)`\n",
        )
        self.write(self.root, "docs/architecture.md", "[up](../README.md) [mod](../mod.py)\n")
        self.write(self.root, "docs/adr/0001-x.md", "# x\n")
        vault.build(
            self.cfg, self.gh.all_issues(), self.gh.all_prs(), self.out, source_url="https://src"
        )
        readme = self.note("README.md")
        self.assertIn("[license](https://src/LICENSE)", readme)
        self.assertIn("[design](https://src/plugin/DESIGN.md#jobs)", readme)
        self.assertIn("[arch](docs/architecture.md)", readme)
        self.assertIn("[adr](docs/adr/)", readme)
        self.assertIn("[web](https://example.org) [top](#x) `[code](LICENSE)`", readme)
        arch = self.note("docs/architecture.md")
        self.assertIn("[up](../README.md) [mod](https://src/mod.py)", arch)

    def test_github_source_from_origin(self) -> None:
        self.git(self.root, "remote", "set-url", "origin", "git@github.com:CTDes/textkit.git")
        sha = self.git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(
            vault.github_source(self.cfg), f"https://github.com/CTDes/textkit/blob/{sha}"
        )
        self.git(self.root, "remote", "set-url", "origin", "git@github.com-work:CTDes/textkit.git")
        self.assertEqual(
            vault.github_source(self.cfg), f"https://github.com/CTDes/textkit/blob/{sha}"
        )
        self.git(self.root, "remote", "set-url", "origin", "/tmp/elsewhere.git")
        self.assertIsNone(vault.github_source(self.cfg))


class Cli(VaultTestCase):
    def test_cli_builds_the_vault(self) -> None:
        res = self.run_cli("job", "vault", str(self.out), "--title", "Demo")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("vault:", res.stdout)
        self.assertIn("# Demo", self.note("index.md"))


class Helpers(unittest.TestCase):
    def test_rel_link(self) -> None:
        self.assertEqual(vault.rel_link("specs/1.md", "tickets/2.md", "x"), "[x](../tickets/2.md)")
        self.assertEqual(vault.rel_link("index.md", "board.md", "b"), "[b](board.md)")

    def test_inline_escapes_link_and_table_syntax(self) -> None:
        self.assertEqual(vault.inline("a [b] | <c>\n d"), "a \\[b\\] \\| &lt;c> d")

    def test_parse_milestones(self) -> None:
        [m0, m1, m2] = vault.parse_milestones(ROADMAP)
        self.assertEqual((m0.key, m0.status, m0.pr), ("M0", "done", 3))
        self.assertEqual((m1.status, m1.spec), ("in progress", 20))
        self.assertEqual((m2.title, m2.spec), ("Slugs", None))


if __name__ == "__main__":
    unittest.main()
