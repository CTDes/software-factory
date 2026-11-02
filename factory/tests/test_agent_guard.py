"""factory/hooks/agent_guard.py: what each agent may run and write."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "hooks" / "agent_guard.py"


class AgentGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="guard-")).resolve()
        (self.root / "factory" / "jobs" / "001-x").mkdir(parents=True)
        wt = self.root / ".claude" / "worktrees" / "001-x"
        (wt / "tests").mkdir(parents=True)
        (wt / "tests" / "test_old.py").write_text("x")
        (wt / "src.py").write_text("x")
        (self.root / "factory" / "config.json").write_text(
            json.dumps({"protected_paths": ["factory/**", ".github/**", ".claude/**", "tests/**"]})
        )
        self.wt = wt

    def run_guard(self, agent: str, tool: str, **tool_input: str) -> tuple[int, str]:
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        env.pop("FACTORY_ROOT", None)
        proc = subprocess.run(
            [sys.executable, str(GUARD), agent],
            input=json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)}),
            capture_output=True,
            text=True,
            env=env,
        )
        return proc.returncode, proc.stderr

    def assertBlocked(self, agent: str, tool: str, **kw: str) -> None:
        code, err = self.run_guard(agent, tool, **kw)
        self.assertEqual(code, 2, f"expected block for {agent} {tool} {kw}")
        self.assertIn("BLOCKED", err)

    def assertAllowed(self, agent: str, tool: str, **kw: str) -> None:
        code, err = self.run_guard(agent, tool, **kw)
        self.assertEqual(code, 0, f"expected allow for {agent} {tool} {kw}: {err}")

    def test_nobody_runs_gh_or_pushes(self) -> None:
        for agent in ("builder", "reviewer", "planner"):
            for cmd in (
                "gh pr list",
                "cd /x && gh issue comment 1 --body hi",
                "/opt/homebrew/bin/gh api user",
                "git push origin HEAD",
                "git -C . push",
                "git -c push.default=current push",
                "git 'push' origin main",
                "git remote set-url origin evil",
            ):
                with self.subTest(agent=agent, cmd=cmd):
                    self.assertBlocked(agent, "Bash", command=cmd)

    def test_builder_may_run_toolchain_and_local_git(self) -> None:
        for cmd in (
            f"cd {self.wt} && factory/checks.sh",
            f"git -C {self.wt} commit -m 'C1: x'",
            "git merge origin/spec/010-x",
            "git log --oneline | head",
            "python3 -m unittest",
            "echo ghost",
        ):
            with self.subTest(cmd=cmd):
                self.assertAllowed("builder", "Bash", command=cmd)

    def test_reviewer_bash_is_read_only_git(self) -> None:
        for cmd in (
            "git diff origin/main...HEAD",
            f"cd {self.wt} && git log --oneline origin/main..HEAD",
            f"git -C {self.wt} show HEAD:src.py",
            "git merge-base origin/main HEAD",
        ):
            with self.subTest(cmd=cmd):
                self.assertAllowed("reviewer", "Bash", command=cmd)
        for cmd in (
            "python3 -m unittest",
            "git commit -am x",
            "git diff > /tmp/x",
            "git diff $(rm -rf /)",
            "git log | sh",
            "cat src.py",
        ):
            with self.subTest(cmd=cmd):
                self.assertBlocked("reviewer", "Bash", command=cmd)

    def test_planner_has_no_shell(self) -> None:
        self.assertBlocked("planner", "Bash", command="ls")

    def test_write_locations(self) -> None:
        job_file = str(self.root / "factory/jobs/001-x/plan.md")
        wt_file = str(self.wt / "src.py")
        main_file = str(self.root / "src.py")
        for agent in ("planner", "reviewer", "builder"):
            self.assertAllowed(agent, "Write", file_path=job_file)
            self.assertBlocked(agent, "Write", file_path=main_file)
            self.assertBlocked(agent, "Edit", file_path="/etc/hosts")
        self.assertAllowed("builder", "Edit", file_path=wt_file)
        self.assertBlocked("planner", "Write", file_path=wt_file)
        self.assertBlocked("reviewer", "Edit", file_path=wt_file)
        self.assertBlocked("builder", "Write", file_path="relative/path.py")
        self.assertBlocked(
            "builder", "Write", file_path=str(self.wt / ".." / ".." / ".." / "src.py")
        )

    def test_builder_cannot_modify_existing_protected_files_but_can_add(self) -> None:
        self.assertBlocked("builder", "Edit", file_path=str(self.wt / "tests" / "test_old.py"))
        self.assertBlocked("builder", "Write", file_path=str(self.wt / "tests" / "test_old.py"))
        self.assertAllowed("builder", "Write", file_path=str(self.wt / "tests" / "test_new.py"))

    def test_other_tools_pass_through(self) -> None:
        self.assertAllowed("planner", "Read", file_path="/etc/hosts")
        self.assertAllowed("reviewer", "Grep", pattern="x")


if __name__ == "__main__":
    unittest.main()
