"""Publishing the wiki to the office (DESIGN.md · Wiki publishing). Local HTTP office only."""

from __future__ import annotations

import io
import os
import tarfile
import threading
import time
import urllib.parse
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from helpers import FactoryTestCase
from lib import cli, events, wiki


class Office:
    """Records wiki uploads; answers 204 (or ``status``); accepts events too."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.status = 204
        office = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                url = urllib.parse.urlparse(self.path)
                if url.path == "/wiki":
                    office.uploads.append(
                        {
                            "repo": urllib.parse.parse_qs(url.query)["repo"][0],
                            "auth": self.headers.get("Authorization"),
                            "type": self.headers.get("Content-Type"),
                            "body": body,
                        }
                    )
                    self.send_response(office.status)
                else:
                    self.send_response(200)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def files(self, n: int = -1) -> dict[str, str]:
        with tarfile.open(fileobj=io.BytesIO(self.uploads[n]["body"]), mode="r:gz") as tar:
            return {
                m.name: tar.extractfile(m).read().decode()  # type: ignore[union-attr]
                for m in tar.getmembers()
            }


class WikiTestCase(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.office = Office()
        self.addCleanup(self.office.close)
        os.environ[events.URL_ENV] = self.office.url
        os.environ[events.TOKEN_ENV] = "s3cret"

    def run_job(self, *argv: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            cli.job_main(list(argv))
        return out.getvalue()


class Publish(WikiTestCase):
    def test_manual_publish_sends_the_vault_as_tar_gz(self) -> None:
        self.add_issue(12, title="Reading time")
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.job_main(["office", "wiki"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("wiki: sent", out.getvalue())
        [up] = self.office.uploads
        self.assertEqual(up["auth"], "Bearer s3cret")
        self.assertEqual(up["type"], "application/gzip")
        self.assertEqual(up["repo"], events.repo_name(self.cfg.root))
        files = self.office.files()
        self.assertIn("index.md", files)
        self.assertIn("# #12 Reading time", files["tickets/12.md"])
        self.assertTrue(all(not name.startswith(("/", "..")) for name in files))

    def test_not_linked_is_skipped(self) -> None:
        del os.environ[events.URL_ENV]
        result = wiki.publish(self.cfg, self.gh)
        self.assertEqual(result.skipped, "not linked to an office")
        self.assertEqual(self.office.uploads, [])

    def test_office_error_keeps_the_mark_and_backs_off(self) -> None:
        self.new_job(12)
        self.office.status = 500
        self.run_job("summary")
        self.assertEqual(len(self.office.uploads), 1)
        self.assertEqual(wiki.is_dirty(self.cfg), "normal")
        self.run_job("summary")  # within the backoff: no new attempt
        self.assertEqual(len(self.office.uploads), 1)


class Automatic(WikiTestCase):
    def test_a_transition_publishes_at_the_end_of_the_command(self) -> None:
        self.add_issue(12)
        self.run_job("create", "12")
        self.assertEqual(len(self.office.uploads), 1)
        self.assertIn("tickets/12.md", self.office.files())
        self.assertIsNone(wiki.is_dirty(self.cfg))

    def test_nothing_changed_means_no_upload(self) -> None:
        self.run_job("summary")
        self.assertEqual(self.office.uploads, [])

    def test_normal_transitions_are_throttled_urgent_ones_are_not(self) -> None:
        self.add_issue(12)
        self.run_job("create", "12")
        self.run_job("start", "12")  # intake -> intake: normal, within THROTTLE_S
        self.assertEqual(len(self.office.uploads), 1)
        self.assertEqual(wiki.is_dirty(self.cfg), "normal")
        job = self.job(12)
        self.write_plan(job, "REJECT")
        self.run_job("advance", "12")  # -> rejected: urgent
        self.assertEqual(len(self.office.uploads), 2)
        self.assertIsNone(wiki.is_dirty(self.cfg))

    def test_throttle_expires(self) -> None:
        self.add_issue(12)
        self.run_job("create", "12")
        stamp = self.cfg.jobs_dir / "_events" / "wiki-published"
        stamp.write_text(f"{time.time() - wiki.THROTTLE_S - 1}\n")
        self.run_job("start", "12")
        self.assertEqual(len(self.office.uploads), 2)

    def test_urgent_mark_is_not_downgraded(self) -> None:
        wiki.mark_dirty(self.cfg, "ready")
        wiki.mark_dirty(self.cfg, "build")
        self.assertEqual(wiki.is_dirty(self.cfg), "urgent")

    def test_status_reports_the_wiki(self) -> None:
        self.add_issue(12)
        self.run_job("create", "12")
        out = self.run_job("office", "status")
        self.assertIn("wiki       published 20", out)


class Pack(WikiTestCase):
    def test_pack_skips_symlinks_and_strips_modes(self) -> None:
        folder = self.tmp / "v"
        self.write(folder, "a.md", "A")
        self.write(folder, "sub/b.md", "B")
        (folder / "link.md").symlink_to(self.root / ".env")
        with tarfile.open(fileobj=io.BytesIO(wiki.pack(folder)), mode="r:gz") as tar:
            members = {m.name: m for m in tar.getmembers()}
        self.assertEqual(sorted(members), ["a.md", "sub/b.md"])
        self.assertEqual(members["a.md"].mode, 0o644)
