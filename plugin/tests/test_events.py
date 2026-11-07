"""Optional event emitter (DESIGN.md · Events): outbox, delivery, backfill. Local HTTP sink only."""

from __future__ import annotations

import io
import json
import os
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

from helpers import FactoryTestCase
from lib import cli, events, jobs, machine


class Sink:
    """An office on 127.0.0.1 that records every POST and answers with ``status``.

    With ``token`` set it answers 401 to any other bearer token, like factory-office.
    """

    def __init__(self, token: str | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = 200
        self.token = token
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if not self.path.endswith("/events"):  # e.g. the wiki upload (test_wiki.py)
                    self.send_response(404)
                    self.end_headers()
                    return
                if sink.token and self.headers.get("Authorization") != f"Bearer {sink.token}":
                    self.send_response(401)
                    self.end_headers()
                    return
                sink.requests.append(
                    {"auth": self.headers.get("Authorization"), "body": json.loads(body)}
                )
                self.send_response(sink.status)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/events"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def events(self) -> list[dict[str, Any]]:
        return [e for r in self.requests for e in r["body"]["events"]]


class EventShape(unittest.TestCase):
    def test_event_id_is_deterministic_and_field_sensitive(self) -> None:
        a = events.event_id(
            "o/r", "012-x", "2026-11-02T10:00:00+01:00", "intake", "build", "ACCEPT"
        )
        self.assertEqual(
            a,
            events.event_id(
                "o/r", "012-x", "2026-11-02T10:00:00+01:00", "intake", "build", "ACCEPT"
            ),
        )
        self.assertNotEqual(
            a,
            events.event_id(
                "o/r", "012-x", "2026-11-02T10:00:01+01:00", "intake", "build", "ACCEPT"
            ),
        )
        self.assertEqual(len(a), 32)

    def test_make_event_carries_snapshot_with_event_time(self) -> None:
        job = {
            "id": "012-x",
            "kind": "ticket",
            "issue": 12,
            "spec": None,
            "stage": "build",
            "updated_at": "old",
        }
        e = events.make_event("o/r", "mac", "T1", "intake", "build", "ACCEPT", job)
        self.assertEqual(e["schema"], 1)
        self.assertEqual(
            (e["repo"], e["machine"], e["job_id"], e["issue"]), ("o/r", "mac", "012-x", 12)
        )
        self.assertEqual(
            (e["from"], e["to"], e["reason"], e["ts"]), ("intake", "build", "ACCEPT", "T1")
        )
        self.assertEqual(e["job"]["stage"], "build")
        self.assertEqual(e["job"]["updated_at"], "T1")
        self.assertEqual(job["updated_at"], "old")
        self.assertIsNone(
            events.make_event("o/r", "m", "T", "a", "b", "r", job, snapshot=False)["job"]
        )

    def test_repo_from_remote(self) -> None:
        cases = {
            "git@github.com:CTDes/software-factory.git": "CTDes/software-factory",
            "git@github.com-ctdes:CTDes/software-factory.git": "CTDes/software-factory",
            "https://github.com/CTDes/factory-sandbox": "CTDes/factory-sandbox",
            "https://github.com/CTDes/factory-sandbox.git/\n": "CTDes/factory-sandbox",
            "ssh://git@host:22/team/api.git": "team/api",
        }
        for url, expected in cases.items():
            self.assertEqual(events.repo_from_remote(url), expected, url)
        self.assertIsNone(events.repo_from_remote("nonsense"))

    def test_parse_log_line(self) -> None:
        self.assertEqual(
            events.parse_log_line("T\tintake\tbuild\tACCEPT risk=low\tx\n"),
            ("T", "intake", "build", "ACCEPT risk=low\tx"),
        )
        self.assertIsNone(events.parse_log_line("garbage"))


class EmitterTestCase(FactoryTestCase):
    with_sink: ClassVar[bool] = True

    def setUp(self) -> None:
        super().setUp()
        self.sink = Sink()
        self.addCleanup(self.sink.close)
        if self.with_sink:
            os.environ[events.URL_ENV] = self.sink.url
            os.environ[events.TOKEN_ENV] = "s3cret"
            os.environ[events.MACHINE_ENV] = "test-mac"

    def outbox(self) -> list[dict[str, Any]]:
        path = events.outbox_path(self.cfg)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Disabled(EmitterTestCase):
    with_sink = False

    def test_no_url_means_no_outbox_and_no_requests(self) -> None:
        self.new_job(12)
        self.assertFalse(events.outbox_path(self.cfg).exists())
        result = events.flush(self.cfg)
        self.assertEqual(result.sent, 0)
        self.assertIn("not linked", result.skipped or "")
        self.assertEqual(self.sink.requests, [])

    def test_backfill_without_url_fails_clearly(self) -> None:
        with self.assertRaisesRegex(Exception, "office link"):
            events.backfill(self.cfg, [])


class Recording(EmitterTestCase):
    def test_transition_is_queued_with_log_line_and_snapshot(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "ACCEPT", risk="low", surfaces="api")
        job = self.advance(job)
        queued = self.outbox()
        self.assertEqual(
            [(e["from"], e["to"], e["reason"]) for e in queued][:2],
            [("(new)", "intake", "created from #12"), ("intake", "intake", "start plan")],
        )
        self.assertEqual(queued[1]["job"]["claim"]["action"], "plan")
        self.assertEqual((queued[2]["from"], queued[2]["to"]), ("intake", "build"))
        last = queued[-1]
        self.assertEqual(last["machine"], "test-mac")
        self.assertEqual(last["job"]["stage"], "build")
        self.assertEqual(last["job"]["risk"], "low")
        self.assertIsNone(last["job"]["claim"])
        ts, frm, to, reason = job.file("events.log").read_text().splitlines()[-1].split("\t", 3)
        self.assertEqual(
            (last["ts"], last["from"], last["to"], last["reason"]), (ts, frm, to, reason)
        )

    def test_unwritable_outbox_never_breaks_a_transition(self) -> None:
        events_dir = self.cfg.jobs_dir / "_events"
        events_dir.parent.mkdir(parents=True, exist_ok=True)
        events_dir.write_text("not a directory")
        out = machine.create(self.ctx, self._issue(12))
        self.assertIn("012-", out)
        self.assertEqual(self.job(12).stage, "intake")

    def _issue(self, n: int) -> int:
        self.add_issue(n)
        return n


class Delivery(EmitterTestCase):
    def test_flush_sends_with_token_and_empties_outbox(self) -> None:
        self.new_job(12)
        self.new_job(13)
        result = events.flush(self.cfg)
        self.assertEqual((result.sent, result.pending, result.error), (2, 0, None))
        self.assertEqual(self.sink.requests[0]["auth"], "Bearer s3cret")
        self.assertEqual([e["issue"] for e in self.sink.events()], [12, 13])
        self.assertEqual(self.outbox(), [])

    def test_failed_flush_keeps_events_and_backs_off_automatic_flushes(self) -> None:
        self.new_job(12)
        self.sink.status = 500
        result = events.flush(self.cfg)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.pending, 1)
        self.sink.status = 200
        before = len(self.sink.requests)
        auto = events.flush(self.cfg, automatic=True)
        self.assertIn("backoff", auto.skipped or "")
        self.assertEqual(len(self.sink.requests), before)
        manual = events.flush(self.cfg)
        self.assertEqual((manual.sent, manual.pending), (1, 0))
        self.assertIsNone(events.flush(self.cfg, automatic=True).skipped)

    def test_collector_down_is_an_error_not_an_exception(self) -> None:
        self.new_job(12)
        os.environ[events.URL_ENV] = "http://127.0.0.1:9/events"
        result = events.flush(self.cfg)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.pending, 1)

    def test_batches_and_partial_failure_keep_unsent_tail(self) -> None:
        job = self.new_job(12)
        for i in range(5):
            events.record(self.cfg, job.data, f"T{i}", "build", "build", f"r{i}")
        original = events.BATCH
        events.BATCH = 2
        self.addCleanup(setattr, events, "BATCH", original)
        calls = {"n": 0}
        real_post = events._post

        def flaky(target: events.Sink, batch: list[dict[str, Any]]) -> None:
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("boom")
            real_post(target, batch)

        events._post = flaky  # type: ignore[assignment]
        self.addCleanup(setattr, events, "_post", real_post)
        result = events.flush(self.cfg)
        self.assertEqual((result.sent, result.pending), (2, 4))
        self.assertEqual([e["reason"] for e in self.outbox()][:2], ["r1", "r2"])

    def test_malformed_lines_are_dropped(self) -> None:
        self.new_job(12)
        with events.outbox_path(self.cfg).open("a") as fh:
            fh.write("{not json\n\n")
        self.new_job(13)
        result = events.flush(self.cfg)
        self.assertEqual((result.sent, result.dropped, result.pending), (2, 1, 0))

    def test_events_appended_during_flush_are_kept(self) -> None:
        job = self.new_job(12)
        real_post = events._post

        def post_then_append(target: events.Sink, batch: list[dict[str, Any]]) -> None:
            real_post(target, batch)
            events.record(self.cfg, job.data, "LATE", "intake", "intake", "late")

        events._post = post_then_append  # type: ignore[assignment]
        self.addCleanup(setattr, events, "_post", real_post)
        result = events.flush(self.cfg)
        self.assertEqual(result.sent, 1)
        self.assertEqual([e["reason"] for e in self.outbox()], ["late"])

    def test_every_factory_job_command_flushes(self) -> None:
        self.new_job(12)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.job_main(["summary"]), 0)
        self.assertEqual(len(self.sink.events()), 1)
        self.assertEqual(self.outbox(), [])

    def test_office_cli_status_and_flush(self) -> None:
        self.new_job(12)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.job_main(["office", "status"]), 0)
        self.assertIn("pending    1", out.getvalue())
        self.assertIn("(from environment)", out.getvalue())
        self.assertNotIn("s3cret", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.job_main(["office", "flush"]), 0)
        self.assertIn("sent 1", out.getvalue())


class Backfill(EmitterTestCase):
    def test_backfill_ids_match_live_events_and_only_last_has_snapshot(self) -> None:
        job = self.start(self.new_job(12))
        self.write_plan(job, "ACCEPT")
        self.advance(job)
        live = self.outbox()
        events.outbox_path(self.cfg).unlink()
        queued = events.backfill(self.cfg, [j.data for j in jobs.all_jobs(self.cfg)])
        copies = self.outbox()
        self.assertEqual(queued, len(live))
        self.assertEqual([e["id"] for e in copies], [e["id"] for e in live])
        self.assertEqual([e["job"] is not None for e in copies], [False, False, True])
        self.assertEqual(copies[-1]["job"]["stage"], "build")


class Linking(EmitterTestCase):
    with_sink = False

    def setUp(self) -> None:
        super().setUp()
        self.office = Sink(token="office-secret")
        self.addCleanup(self.office.close)
        self.base = self.office.url[: -len("/events")]

    def office_cli(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.job_main(["office", *argv])
        return code, out.getvalue() + err.getvalue()

    def test_link_checks_saves_privately_and_sends_history(self) -> None:
        self.new_job(12)
        code, out = self.office_cli("link", "office-secret", "--url", self.base + "/")
        self.assertEqual(code, 0, out)
        self.assertIn("linked", out)
        self.assertIn("queued 1", out)
        path = events.link_path(self.cfg)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())["url"], self.office.url)
        self.assertEqual([e["issue"] for e in self.office.events()], [12])
        self.assertEqual(self.office.requests[0]["body"], {"events": []})  # the link check

    def test_linked_repo_sends_new_transitions_on_every_command(self) -> None:
        self.office_cli("link", "office-secret", "--url", self.base)
        self.new_job(13)
        with redirect_stdout(io.StringIO()):
            cli.job_main(["summary"])
        self.assertEqual([e["issue"] for e in self.office.events()], [13])
        self.assertEqual(self.office.requests[-1]["auth"], "Bearer office-secret")

    def test_wrong_token_or_no_office_does_not_link(self) -> None:
        code, out = self.office_cli("link", "wrong", "--url", self.base)
        self.assertEqual(code, 1)
        self.assertIn("rejected the token", out)
        code, out = self.office_cli("link", "office-secret", "--url", "http://127.0.0.1:9")
        self.assertEqual(code, 1)
        self.assertIn("cannot reach", out)
        self.assertFalse(events.link_path(self.cfg).exists())
        self.assertIsNone(events.sink(self.cfg))

    def test_status_never_prints_the_token(self) -> None:
        self.office_cli("link", "office-secret", "--url", self.base)
        code, out = self.office_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("(from link.json)", out)
        self.assertIn("token accepted", out)
        self.assertNotIn("office-secret", out)
        self.office.token = "rotated"
        self.assertIn("rejected the token", self.office_cli("status")[1])

    def test_environment_takes_precedence(self) -> None:
        self.office_cli("link", "office-secret", "--url", self.base)
        os.environ[events.URL_ENV] = "http://127.0.0.1:9/events"
        target = events.sink(self.cfg)
        assert target is not None
        self.assertEqual(target.source, "env")

    def test_unlink_forgets_link_and_pending_events(self) -> None:
        self.office_cli("link", "office-secret", "--url", self.base)
        self.office.status = 500
        self.new_job(14)
        self.assertEqual(events.pending(self.cfg), 1)
        code, out = self.office_cli("unlink")
        self.assertEqual(code, 0)
        self.assertIn("dropped 1", out)
        self.assertFalse(events.link_path(self.cfg).exists())
        self.assertEqual(events.pending(self.cfg), 0)
        self.assertEqual(self.office_cli("unlink")[1].strip(), "not linked")

    def test_link_needs_a_token(self) -> None:
        self.assertEqual(self.office_cli("link")[0], 2)

    def test_events_url(self) -> None:
        self.assertEqual(events.events_url("http://h:8765"), "http://h:8765/events")
        self.assertEqual(events.events_url("http://h:8765/events/"), "http://h:8765/events")
        with self.assertRaisesRegex(Exception, "http"):
            events.events_url("h:8765")


if __name__ == "__main__":
    unittest.main()
