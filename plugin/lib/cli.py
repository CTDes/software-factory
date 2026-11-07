"""Command-line entry points for bin/job and bin/gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from lib import config, events, gate, history, jobs, machine, vault, wiki
from lib.github import connect
from lib.util import EXIT_CONDITION, EXIT_OK, EXIT_USAGE, FactoryError, UsageError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _ctx() -> machine.Ctx:
    cfg = config.load()
    return machine.Ctx(cfg, connect(cfg.root))


def _table(rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in rows
    )


def _summary(cfg: config.Config) -> str:
    rows = [["JOB", "KIND", "STAGE", "ROUND", "RISK", "PR", "CLAIM", "REASON"]]
    for j in jobs.all_jobs(cfg):
        rows.append(
            [
                j.id,
                j["kind"],
                j.stage,
                str(j["round"]),
                j.get("risk") or "-",
                f"#{j['pr']}" if j.get("pr") else "-",
                j["claim"]["action"] if j.get("claim") else "-",
                (j.get("reason") or "-")[:60],
            ]
        )
    return _table(rows) if len(rows) > 1 else "no jobs"


def _status(job: jobs.Job) -> str:
    lines = [f"{job.id} · #{job['issue']} · {job['title']}"]
    for key in (
        "kind",
        "stage",
        "round",
        "risk",
        "surfaces",
        "spec",
        "base",
        "branch",
        "worktree",
        "pr",
        "agent",
        "claim",
        "feedback",
        "reason",
        "updated_at",
    ):
        lines.append(f"  {key:<10} {job.get(key)}")
    log = job.file("events.log")
    if log.exists():
        lines.append("  events:")
        lines += [f"    {line}" for line in log.read_text(encoding="utf-8").splitlines()[-10:]]
    return "\n".join(lines)


def job_main(argv: Sequence[str] | None = None) -> int:
    p = _Parser(prog="factory-job", description="Software factory state machine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue")
    c = sub.add_parser("create")
    c.add_argument("issue", type=int)
    sp = sub.add_parser("spec")
    sp.add_argument("subcmd", choices=["create"])
    sp.add_argument("issue", type=int)
    n = sub.add_parser("next")
    n.add_argument("--json", action="store_true")
    n.add_argument("--only", metavar="id|issue", help="offer actions for this job only")
    for name in ("start", "advance", "merge"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("rework").add_argument("ref", metavar="id|issue")
    sub.add_parser("recover")
    st = sub.add_parser("status")
    st.add_argument("id", nargs="?")
    sub.add_parser("summary")
    hi = sub.add_parser(
        "history", help="write docs/history/<job>.md into this checkout (backfill, uncommitted)"
    )
    hi.add_argument("refs", nargs="*", metavar="id|issue", help="default: every job with a PR")
    va = sub.add_parser("vault", help="build the project wiki (Obsidian vault / Quartz content)")
    va.add_argument("out", help="folder to (re)build; must be empty or a previous vault")
    va.add_argument("--title", help="wiki title (default: the repository folder name)")
    of = sub.add_parser("office", help="link this repository to a factory-office")
    of.add_argument("subcmd", choices=["link", "unlink", "status", "flush", "backfill", "wiki"])
    of.add_argument("token", nargs="?", help="the office token (link only)")
    of.add_argument("--url", help=f"the office (default {events.DEFAULT_OFFICE})")
    args = p.parse_args(argv)

    if args.cmd == "office":
        return _office_main(args.subcmd, args.token, args.url)
    try:
        ctx = _ctx()
        cfg = ctx.cfg
        if args.cmd == "queue":
            out = machine.queue(ctx)
            print("\n".join(out) if out else "queue: nothing new")
            print(_summary(cfg))
        elif args.cmd == "create":
            print(machine.create(ctx, args.issue))
        elif args.cmd == "spec":
            from lib import spec

            print(spec.create(ctx, args.issue))
        elif args.cmd == "next":
            actions = machine.next_actions(ctx, only=args.only)
            if args.json:
                print(json.dumps(actions, indent=2, ensure_ascii=False))
            elif not actions:
                print("no actions")
            else:
                for a in actions:
                    what = (
                        f"{a['agent']} ({a['model']}) as {a['name']}"
                        if a["kind"] == "agent"
                        else a["command"]
                    )
                    print(f"{a['job']}\t{a['action']}\t{what}")
        elif args.cmd == "start":
            print(machine.start(ctx, jobs.resolve(cfg, args.id)))
        elif args.cmd == "advance":
            print(machine.advance(ctx, jobs.resolve(cfg, args.id)))
        elif args.cmd == "merge":
            print(machine.merge(ctx, jobs.resolve(cfg, args.id)))
        elif args.cmd == "rework":
            print(machine.rework(ctx, jobs.resolve(cfg, args.ref)))
        elif args.cmd == "recover":
            problems = machine.recover(ctx)
            for line in problems:
                print(f"PROBLEM {line}")
            print("recover: ok" if not problems else f"recover: {len(problems)} problem(s)")
            return EXIT_CONDITION if problems else EXIT_OK
        elif args.cmd == "status":
            targets = [jobs.resolve(cfg, args.id)] if args.id else jobs.all_jobs(cfg)
            print("\n\n".join(_status(j) for j in targets) or "no jobs")
        elif args.cmd == "summary":
            print(_summary(cfg))
        elif args.cmd == "vault":
            from pathlib import Path

            notes = vault.build(
                cfg, ctx.gh.all_issues(), ctx.gh.all_prs(), Path(args.out).resolve(), args.title
            )
            print(f"vault: {len(notes)} notes in {args.out}")
        elif args.cmd == "history":
            targets = (
                [jobs.resolve(cfg, r) for r in args.refs]
                if args.refs
                else [j for j in jobs.all_jobs(cfg) if j.get("pr") or j.stage == "done"]
            )
            if not targets:
                print("history: no jobs with a PR")
            for j in targets:
                path = history.write(cfg, j)
                if path is None:
                    raise FactoryError(
                        "history is off: 'history_dir' is empty in factory/config.json"
                    )
                print(f"{j.id} -> {path.relative_to(cfg.root)}")
    except FactoryError as exc:
        print(f"factory-job: {exc}", file=sys.stderr)
        return exc.code
    finally:
        _auto_flush()
    return EXIT_OK


def _auto_flush() -> None:
    """Best effort, silent: an office that is down must not change any command's outcome."""
    try:
        cfg = config.load()
        if events.sink(cfg) is not None:
            events.flush(cfg, automatic=True)
            if wiki.is_dirty(cfg):
                wiki.publish(cfg, connect(cfg.root), automatic=True)
    except Exception:
        pass


def _flush_line(r: events.FlushResult) -> str:
    parts = [f"sent {r.sent}", f"pending {r.pending}"]
    if r.dropped:
        parts.append(f"dropped {r.dropped} malformed")
    if r.skipped:
        parts.append(f"skipped: {r.skipped}")
    if r.error:
        parts.append(f"error: {r.error}")
    return "events: " + ", ".join(parts)


def _office_main(subcmd: str, token: str | None, url: str | None) -> int:
    try:
        cfg = config.load()
        if subcmd == "status":
            print("\n".join(events.status(cfg)))
            print(wiki.status_line(cfg))
            return EXIT_OK
        if subcmd == "wiki":
            published = wiki.publish(cfg, connect(cfg.root))
            print(published.line())
            return EXIT_CONDITION if published.error or published.skipped else EXIT_OK
        if subcmd == "unlink":
            print(events.unlink(cfg))
            return EXIT_OK
        if subcmd == "link":
            if not token:
                raise UsageError("usage: factory-job office link <token> [--url URL]")
            for line in events.link(cfg, token, url, [j.data for j in jobs.all_jobs(cfg)]):
                print(line)
            print(wiki.publish(cfg, connect(cfg.root)).line())
        elif subcmd == "backfill":
            print(
                f"history: queued {events.backfill(cfg, [j.data for j in jobs.all_jobs(cfg)])} events"
            )
        result = events.flush(cfg)
        print(_flush_line(result))
        return EXIT_CONDITION if result.error or result.skipped else EXIT_OK
    except FactoryError as exc:
        print(f"factory-job: {exc}", file=sys.stderr)
        return exc.code


def gate_main(argv: Sequence[str] | None = None) -> int:
    p = _Parser(
        prog="factory-gate",
        description="Run checks.sh from origin/<base_branch> and verify the diff",
    )
    p.add_argument("id")
    p.add_argument("--final", action="store_true", help="spec final gate: diff against base_branch")
    args = p.parse_args(argv)
    try:
        cfg = config.load()
        job = jobs.resolve(cfg, args.id)
        if args.final:
            if job["kind"] != "spec" or job.stage != "final-review":
                raise FactoryError(f"{job.id}: `gate --final` runs on a spec in 'final-review'")
        elif job.stage != "gate":
            raise FactoryError(f"{job.id}: gate runs in stage 'gate', job is in '{job.stage}'")
        result = gate.run_gate(cfg, job, final=args.final)
    except FactoryError as exc:
        print(f"factory-gate: {exc}", file=sys.stderr)
        return EXIT_USAGE  # 1 is reserved for a FAIL verdict
    verdict = "PASS" if result.passed else "FAIL"
    print(f"{job.id} GATE {verdict} → {job.round_dir() / 'checks.md'}")
    return EXIT_OK if result.passed else EXIT_CONDITION
