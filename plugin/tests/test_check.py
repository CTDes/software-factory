"""factory-init --check: requirements (fail blocks) and setup state (todo guides), writes nothing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))

from lib import check  # noqa: E402

LABELS = ["ready-for-agent", "spec", "needs-info", "ready-for-human", "factory:working"]
REAL_CHECKS = "#!/usr/bin/env bash\nset -euo pipefail\npython3 -m unittest\n"


def git(cwd: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


class VersionTest(unittest.TestCase):
    def test_parses_git_and_gh_version_lines(self) -> None:
        self.assertEqual(check.parse_version("git version 2.50.1 (Apple Git-155)"), (2, 50, 1))
        self.assertEqual(check.parse_version("gh version 2.103.3 (2026-10-26)"), (2, 103, 3))
        self.assertEqual(check.parse_version("git version 2.39"), (2, 39))
        self.assertIsNone(check.parse_version("no digits"))

    def test_python_below_minimum_fails(self) -> None:
        self.assertTrue(check.check_python((3, 9, 18)).startswith("fail"))
        self.assertTrue(check.check_python((3, 10, 0)).startswith("ok"))


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="check-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.tmp = tmp
        gitconfig = tmp / "gitconfig"
        gitconfig.write_text("[user]\n\tname = T\n\temail = t@example.com\n")
        self.claude_dir = tmp / "claude"
        self.claude_dir.mkdir()
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "CLAUDE_CONFIG_DIR": str(self.claude_dir),
        }
        self.origin = tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.repo = tmp / "repo"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        git(self.repo, self.env, "remote", "add", "origin", str(self.origin))
        self.gh: dict[str, Any] = {
            "auth": True,
            "repo": {"nameWithOwner": "me/app", "viewerPermission": "WRITE"},
            "labels": [],
            "branch": {"protected": False},
            "rules": [],
        }

    # ------------------------------------------------ fixtures

    def write_fake_gh(self) -> None:
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        script = bindir / "gh"
        script.write_text(
            f"""#!{sys.executable}
import json, sys
state = json.loads({json.dumps(json.dumps(self.gh))})
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("gh version 2.60.0 (2024-01-01)")
elif args[:2] == ["auth", "status"]:
    sys.exit(0 if state["auth"] else 1)
elif args[:2] == ["repo", "view"]:
    if state["repo"] is None:
        sys.exit("no git remotes found")
    print(json.dumps(state["repo"]))
elif args[:2] == ["label", "list"]:
    print(json.dumps([{{"name": n}} for n in state["labels"]]))
elif args[:1] == ["api"] and "/rules/branches/" in args[1]:
    print(json.dumps(state["rules"]))
elif args[:1] == ["api"] and "/branches/" in args[1]:
    print(json.dumps(state["branch"]))
else:
    sys.exit("unexpected gh call: " + " ".join(args))
"""
        )
        script.chmod(0o755)
        self.env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"

    def guardrails(self) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "~/.claude/hooks/no-git.sh"}],
                    }
                ]
            }
        }
        (self.claude_dir / "settings.json").write_text(json.dumps(settings))

    def factory_files(self, checks_sh: str | None = REAL_CHECKS) -> None:
        cfg = json.loads((PLUGIN / "templates" / "config.json").read_text())
        (self.repo / "factory").mkdir(exist_ok=True)
        (self.repo / "factory" / "config.json").write_text(json.dumps(cfg))
        text = checks_sh or (PLUGIN / "templates" / "checks.sh").read_text()
        (self.repo / "factory" / "checks.sh").write_text(text)

    def publish_base(self) -> None:
        git(self.repo, self.env, "add", "-A")
        git(self.repo, self.env, "commit", "-q", "-m", "setup")
        git(self.repo, self.env, "push", "-q", "origin", "main")

    def run_check(self) -> subprocess.CompletedProcess[str]:
        self.write_fake_gh()
        return subprocess.run(
            [sys.executable, str(PLUGIN / "bin" / "factory-init"), "--check"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env=self.env,
        )

    def lines(self, res: subprocess.CompletedProcess[str], status: str) -> list[str]:
        return [ln for ln in res.stdout.splitlines() if ln.startswith(status)]

    # ------------------------------------------------ requirements

    def test_fully_set_up_repository_is_all_ok(self) -> None:
        self.guardrails()
        self.factory_files()
        self.publish_base()
        self.gh["labels"] = LABELS
        self.gh["branch"] = {
            "protected": True,
            "protection": {"required_status_checks": {"contexts": ["checks"]}},
        }
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        not_ok = [ln for ln in res.stdout.splitlines() if not ln.startswith("ok")]
        self.assertEqual(not_ok, [])

    def test_unauthenticated_gh_fails(self) -> None:
        self.gh["auth"] = False
        res = self.run_check()
        self.assertEqual(res.returncode, 1)
        self.assertIn("gh not authenticated", res.stdout)

    def test_read_only_access_fails(self) -> None:
        self.gh["repo"] = {"nameWithOwner": "me/app", "viewerPermission": "READ"}
        res = self.run_check()
        self.assertEqual(res.returncode, 1)
        self.assertIn("fail     gh has READ access to me/app", res.stdout)

    def test_no_github_repository_fails_and_suggests_gh_repo_create(self) -> None:
        self.gh["repo"] = None
        res = self.run_check()
        self.assertEqual(res.returncode, 1)
        self.assertIn("gh repo create", res.stdout)

    def test_missing_guardrails_hook_only_warns(self) -> None:
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertTrue(any("guardrails" in ln for ln in self.lines(res, "warn")))

    def test_guardrails_hook_on_another_tool_does_not_count(self) -> None:
        settings = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"command": "git"}]}]}}
        (self.claude_dir / "settings.json").write_text(json.dumps(settings))
        res = self.run_check()
        self.assertTrue(any("guardrails" in ln for ln in self.lines(res, "warn")))

    # ------------------------------------------------ setup state

    def test_fresh_repository_lists_todos_without_failing(self) -> None:
        self.guardrails()
        res = self.run_check()
        self.assertEqual(res.returncode, 0, res.stdout)
        todo = "\n".join(self.lines(res, "todo"))
        self.assertIn("factory-init --labels", todo)
        self.assertIn("not on origin/main", todo)
        self.assertIn("https://github.com/me/app/settings/branches", todo)

    def test_template_checks_sh_is_a_todo_locally_and_on_base(self) -> None:
        self.factory_files(checks_sh=None)
        self.publish_base()
        res = self.run_check()
        todo = "\n".join(self.lines(res, "todo"))
        self.assertIn("factory/checks.sh is still the template", todo)
        self.assertIn("on origin/main is still the template", todo)

    def test_real_checks_sh_not_merged_yet(self) -> None:
        self.factory_files(checks_sh=None)
        self.publish_base()
        (self.repo / "factory" / "checks.sh").write_text(REAL_CHECKS)
        res = self.run_check()
        self.assertIn("ok       factory/checks.sh written", res.stdout)
        self.assertIn("on origin/main is still the template", res.stdout)

    def test_missing_labels_are_named(self) -> None:
        self.factory_files()
        self.gh["labels"] = ["spec", "bug"]
        res = self.run_check()
        self.assertIn("todo     labels missing: ready-for-agent, needs-info", res.stdout)

    def test_required_check_from_a_ruleset_counts(self) -> None:
        self.gh["rules"] = [
            {"type": "deletion"},
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": "checks"}]},
            },
        ]
        res = self.run_check()
        self.assertIn("ok       `checks` is a required check on main", res.stdout)

    def test_other_required_checks_do_not_count(self) -> None:
        self.gh["branch"] = {
            "protected": True,
            "protection": {"required_status_checks": {"checks": [{"context": "lint"}]}},
        }
        res = self.run_check()
        self.assertIn("todo     `checks` is not a required check on main", res.stdout)

    def test_check_writes_nothing(self) -> None:
        self.factory_files()
        before = sorted(p for p in self.repo.rglob("*") if ".git" not in p.parts)
        self.run_check()
        after = sorted(p for p in self.repo.rglob("*") if ".git" not in p.parts)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
