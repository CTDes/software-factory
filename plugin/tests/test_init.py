"""factory-init: writes what is missing, merges settings and .gitignore, is idempotent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp(prefix="init-")).resolve()
        subprocess.run(["git", "init", "-q", "-b", "trunk", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("node_modules/\n")
        (self.repo / "CLAUDE.md").write_text("# mine\n")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(npm test)"]}, "theme": "dark"})
        )

    def run_init(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PLUGIN / "bin" / "factory-init"), *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )

    def test_creates_missing_files_and_keeps_existing(self) -> None:
        res = self.run_init("--base", "trunk")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.repo / "CLAUDE.md").read_text().startswith("# mine\n"))
        cfg = json.loads((self.repo / "factory/config.json").read_text())
        self.assertEqual(cfg["base_branch"], "trunk")
        self.assertTrue(os.access(self.repo / "factory/checks.sh", os.X_OK))
        self.assertIn("branches: [trunk]", (self.repo / ".github/workflows/checks.yml").read_text())
        for rel in (".worktreeinclude", "GLOSSARY.md", "docs/architecture.md"):
            self.assertTrue((self.repo / rel).exists(), rel)

    def test_merges_gitignore_and_settings(self) -> None:
        self.run_init()
        gi = (self.repo / ".gitignore").read_text()
        self.assertIn("node_modules/", gi)
        self.assertIn("factory/jobs/", gi)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["theme"], "dark")
        self.assertIn("Bash(npm test)", settings["permissions"]["allow"])
        self.assertIn("Bash(factory-job *)", settings["permissions"]["allow"])
        self.assertTrue(settings["enabledPlugins"]["software-factory@ctdes-factory"])
        self.assertEqual(
            settings["extraKnownMarketplaces"]["ctdes-factory"]["source"]["repo"],
            "CTDes/software-factory",
        )
        self.assertTrue(settings["extraKnownMarketplaces"]["ctdes-factory"]["autoUpdate"])

    def test_idempotent(self) -> None:
        self.run_init()
        before = {
            p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file() and ".git/" not in str(p)
        }
        res = self.run_init()
        self.assertNotIn("created", res.stdout)
        self.assertNotIn("updated", res.stdout)
        after = {
            p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file() and ".git/" not in str(p)
        }
        self.assertEqual(before, after)

    def test_template_checks_sh_fails_until_edited(self) -> None:
        self.run_init()
        res = subprocess.run(
            [str(self.repo / "factory/checks.sh")], cwd=self.repo, capture_output=True
        )
        self.assertNotEqual(res.returncode, 0)

    # ------------------------------------------------ existing CLAUDE.md

    def test_appends_factory_section_to_existing_claude_md(self) -> None:
        res = self.run_init()
        self.assertIn("updated  CLAUDE.md (+software factory section)", res.stdout)
        text = (self.repo / "CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# mine\n"))
        self.assertIn("## Software factory", text)
        self.assertIn("`factory/checks.sh`", text)
        self.assertIn("protected_paths", text)

    def test_leaves_claude_md_that_already_mentions_checks_sh(self) -> None:
        mine = "# mine\n\nValidate with `factory/checks.sh`.\n"
        (self.repo / "CLAUDE.md").write_text(mine)
        res = self.run_init()
        self.assertIn("kept     CLAUDE.md", res.stdout)
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), mine)

    def test_new_claude_md_comes_from_the_template(self) -> None:
        (self.repo / "CLAUDE.md").unlink()
        res = self.run_init()
        self.assertIn("created  CLAUDE.md", res.stdout)
        self.assertEqual((self.repo / "CLAUDE.md").read_text().count("factory/checks.sh"), 1)

    # ------------------------------------------------ existing CI

    def test_warns_about_existing_workflows(self) -> None:
        wf = self.repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: ci\n")
        (wf / "release.yaml").write_text("name: release\n")
        res = self.run_init()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("created  .github/workflows/checks.yml", res.stdout)
        self.assertIn("warn     existing workflows: ci.yml, release.yaml", res.stdout)

    def test_no_workflow_warning_without_other_workflows(self) -> None:
        res = self.run_init()
        self.assertNotIn("existing workflows", res.stdout)
        res = self.run_init()  # checks.yml itself does not count
        self.assertNotIn("existing workflows", res.stdout)

    # ------------------------------------------------ labels

    def fake_gh(self, labels: dict[str, int]) -> Path:
        """Put a fake `gh` first on PATH. `labels`: existing label -> open issues carrying it."""
        bindir = Path(tempfile.mkdtemp(prefix="gh-"))
        log = bindir / "calls.log"
        script = bindir / "gh"
        script.write_text(
            f"""#!{sys.executable}
import json, sys
labels = {labels!r}
args = sys.argv[1:]
with open({str(log)!r}, "a") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:2] == ["label", "list"]:
    print(json.dumps([{{"name": n}} for n in labels]))
elif args[:2] == ["issue", "list"]:
    name = args[args.index("--label") + 1]
    print(json.dumps([{{"number": i + 1}} for i in range(labels.get(name, 0))]))
elif args[:2] == ["label", "create"]:
    if "--force" not in args and args[2] in labels:
        sys.exit("label already exists")
else:
    sys.exit("unexpected gh call")
"""
        )
        script.chmod(0o755)
        self.gh_log = log
        self.env_path = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
        return log

    def run_init_gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PLUGIN / "bin" / "factory-init"), *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": self.env_path},
        )

    def gh_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.gh_log.read_text().splitlines()]

    def test_labels_creates_only_missing_and_never_forces(self) -> None:
        self.fake_gh({"spec": 0, "bug": 3})
        res = self.run_init_gh("--labels")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        created = [c[2] for c in self.gh_calls() if c[:2] == ["label", "create"]]
        self.assertNotIn("spec", created)
        self.assertIn("ready-for-agent", created)
        self.assertEqual(len(created), 4)
        self.assertFalse(any("--force" in c for c in self.gh_calls()))
        self.assertIn("kept     label spec (already exists)", res.stdout)
        self.assertIn("label    ready-for-agent", res.stdout)

    def test_labels_warns_when_existing_queue_or_spec_label_has_open_issues(self) -> None:
        self.fake_gh({"spec": 2, "ready-for-agent": 1, "needs-info": 5})
        res = self.run_init_gh("--labels")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("warn     label spec already has 2 open issue(s)", res.stdout)
        self.assertIn("warn     label ready-for-agent already has 1 open issue(s)", res.stdout)
        self.assertNotIn("warn     label needs-info", res.stdout)

    def test_labels_no_warning_for_existing_label_without_open_issues(self) -> None:
        self.fake_gh({"spec": 0})
        res = self.run_init_gh("--labels")
        self.assertNotIn("warn     label", res.stdout)


if __name__ == "__main__":
    unittest.main()
