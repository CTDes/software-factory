"""Command-line entry points for bin/job and bin/gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from lib import config, gate, jobs, machine
from lib.github import connect
from lib.util import EXIT_CONDITION, EXIT_OK, EXIT_USAGE, FactoryError


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
    p = _Parser(prog="job", description="Software factory state machine")
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
    args = p.parse_args(argv)

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
            raise FactoryError("`job spec create` arrives in phase 5")
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
    except FactoryError as exc:
        print(f"job: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


def gate_main(argv: Sequence[str] | None = None) -> int:
    p = _Parser(
        prog="gate", description="Run checks.sh from origin/<base_branch> and verify the diff"
    )
    p.add_argument("id")
    p.add_argument("--final", action="store_true", help="spec final gate: diff against base_branch")
    args = p.parse_args(argv)
    try:
        cfg = config.load()
        job = jobs.resolve(cfg, args.id)
        if args.final:
            raise FactoryError("`gate --final` arrives with the spec level (phase 5)")
        if job.stage != "gate":
            raise FactoryError(f"{job.id}: gate runs in stage 'gate', job is in '{job.stage}'")
        result = gate.run_gate(cfg, job)
    except FactoryError as exc:
        print(f"gate: {exc}", file=sys.stderr)
        return EXIT_USAGE  # 1 is reserved for a FAIL verdict
    verdict = "PASS" if result.passed else "FAIL"
    print(f"{job.id} GATE {verdict} → {job.round_dir() / 'checks.md'}")
    return EXIT_OK if result.passed else EXIT_CONDITION
