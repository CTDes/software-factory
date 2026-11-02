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
        self.assertIn("kept     CLAUDE.md", res.stdout)
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "# mine\n")
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


if __name__ == "__main__":
    unittest.main()
