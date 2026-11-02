"""Spec level (DESIGN.md · Máquinas de estados · Spec).

A spec is a parent issue (labels `spec` + `queue`) whose children are the open issues with a
`Parent: #<spec>` line. `job spec create` validates the child graph, creates `spec/<id>` from
origin/<base_branch> and one ticket job per child. Tickets build on top of the spec branch and
fast-forward into it (`job merge`). When every ticket is done the spec runs a final gate and a
final review over `<base_branch>...spec/<id>` and ends in one PR to the base branch.
"""

from __future__ import annotations

from typing import Any

from lib import contracts, git, prompts
from lib import issue as issue_md
from lib.jobs import TERMINAL, Job, all_jobs, by_issue, job_id, new_ticket
from lib.machine import (
    Ctx,
    Effect,
    Transition,
    _archive_build,
    _comment,
    _escalate,
    _label,
    _rel,
    _remove_worktree,
    apply,
    say,
)
from lib.util import FactoryError, atomic_write, now

# ---------------------------------------------------------------- graph


def children_of(ctx: Ctx, number: int) -> list[dict[str, Any]]:
    return [d for d in ctx.gh.list_open_issues() if issue_md.parent_of(d["body"]) == number]


def validate_graph(
    ctx: Ctx, spec_number: int, children: list[dict[str, Any]], known: set[int] | None = None
) -> dict[int, list[int]]:
    """Return {child: blockers}. Fails on missing queue label, blockers outside the spec, cycles.

    `known` holds issue numbers already in the spec (for children added later).
    """
    queue = ctx.cfg.label("queue")
    members = {c["number"] for c in children} | (known or set())
    graph: dict[int, list[int]] = {}
    problems: list[str] = []
    for c in children:
        n = c["number"]
        if queue not in c["labels"]:
            problems.append(f"child #{n} lacks the '{queue}' label")
        blockers = issue_md.blocked_by(c["body"])
        outside = [b for b in blockers if b not in members]
        if outside:
            problems.append(
                f"child #{n} is blocked by {', '.join(f'#{b}' for b in outside)}, outside spec #{spec_number}"
            )
        if n in blockers:
            problems.append(f"child #{n} blocks itself")
        graph[n] = blockers
    cycle = _find_cycle(graph)
    if cycle:
        problems.append("cycle in 'Blocked by': " + " -> ".join(f"#{n}" for n in cycle))
    if problems:
        raise FactoryError(
            f"spec #{spec_number}: invalid ticket graph:\n- " + "\n- ".join(problems)
        )
    return graph


def _find_cycle(graph: dict[int, list[int]]) -> list[int] | None:
    state: dict[int, int] = {}  # 1 = visiting, 2 = done
    stack: list[int] = []

    def visit(n: int) -> list[int] | None:
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if m not in graph:
                continue
            if state.get(m) == 1:
                return [*stack[stack.index(m) :], m]
            if state.get(m) is None:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        state[n] = 2
        return None

    for n in sorted(graph):
        if state.get(n) is None:
            found = visit(n)
            if found:
                return found
    return None


def _graph_text(graph: dict[int, list[int]], titles: dict[int, str]) -> str:
    lines = ["| Ticket | Bloqueado por |", "| --- | --- |"]
    for n in sorted(graph):
        blockers = ", ".join(f"#{b}" for b in graph[n]) or "—"
        lines.append(f"| #{n} {titles.get(n, '')} | {blockers} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- create / sync


def _new_spec(ctx: Ctx, data: dict[str, Any]) -> Job:
    cfg = ctx.cfg
    jid = job_id(int(data["number"]), str(data["title"]))
    return Job(
        cfg,
        {
            "id": jid,
            "kind": "spec",
            "issue": int(data["number"]),
            "title": data["title"],
            "spec": None,
            "tickets": [],
            "blocked_by": [],
            "stage": "building",
            "round": 0,
            "risk": None,
            "surfaces": [],
            "models": {
                "builder": cfg.model("builder", "high"),
                "reviewer": cfg.model("final_reviewer"),
            },
            "base": cfg["base_branch"],
            "branch": f"{cfg['spec_branch_prefix']}{jid}",
            "worktree": f"{cfg['worktrees_dir']}/{jid}",
            "pr": None,
            "agent": None,
            "reason": None,
            "claim": None,
            "feedback": None,
            "contract_failures": 0,
            "created_at": now(),
            "pushed_at": None,
            "updated_at": now(),
        },
    )


def _add_tickets(
    ctx: Ctx, spec: Job, children: list[dict[str, Any]], graph: dict[int, list[int]]
) -> list[str]:
    out = []
    for c in sorted(children, key=lambda d: d["number"]):
        full = ctx.gh.issue(c["number"])
        ticket = new_ticket(ctx.cfg, full, spec=spec)
        ticket["blocked_by"] = graph[c["number"]]
        ticket.dir.mkdir(parents=True, exist_ok=False)
        atomic_write(ticket.file("issue.md"), issue_md.render(full))
        ticket.log_event("(new)", "intake", f"created from #{c['number']} for spec {spec.id}")
        ticket.save()
        spec["tickets"] = [*spec["tickets"], ticket.id]
        out.append(f"{ticket.id} created (intake, spec {spec.id})")
    return out


def create(ctx: Ctx, number: int) -> str:
    cfg = ctx.cfg
    existing = by_issue(cfg, number)
    if existing:
        raise FactoryError(f"issue #{number} already has job {existing.id} ({existing.stage})")
    data = ctx.gh.issue(number)
    if data["state"] != "OPEN":
        raise FactoryError(f"issue #{number} is not open")
    for key in ("spec", "queue"):
        if cfg.label(key) not in data["labels"]:
            raise FactoryError(f"issue #{number} lacks the '{cfg.label(key)}' label")
    children = children_of(ctx, number)
    if not children:
        raise FactoryError(f"spec #{number} has no open child issues with 'Parent: #{number}'")
    graph = validate_graph(ctx, number, children)
    spec = _new_spec(ctx, data)
    titles = {c["number"]: c["title"] for c in children}

    # effects first: branch on the remote, comment on the spec issue
    git.fetch(cfg.root)
    base_ref = git.remote_ref(cfg["base_branch"])
    if git.rev_parse(cfg.root, git.remote_ref(spec["branch"])) is None:
        git.push_new_branch(cfg.root, base_ref, spec["branch"])
    ctx.gh.comment(
        number,
        say(
            spec,
            f"spec aceptada en la fábrica. Rama de integración `{spec['branch']}` creada desde "
            f"`{cfg['base_branch']}`.\n\n{_graph_text(graph, titles)}",
        ),
    )
    ctx.gh.add_label(number, cfg.label("in_progress"))

    spec.dir.mkdir(parents=True, exist_ok=False)
    atomic_write(spec.file("issue.md"), issue_md.render(data))
    spec.log_event("(new)", "building", f"spec created from #{number} with {len(children)} tickets")
    out = [f"{spec.id} created (building)"]
    out += _add_tickets(ctx, spec, children, graph)
    spec.save()
    return "\n".join(out)


def tickets_of(spec: Job) -> list[Job]:
    return [j for j in all_jobs(spec.cfg) if j.get("spec") == spec.id]


def sync(ctx: Ctx) -> list[str]:
    """Called by `job queue`: add new children to building specs, finish specs whose tickets are done."""
    out: list[str] = []
    for spec in [j for j in all_jobs(ctx.cfg) if j["kind"] == "spec" and j.stage not in TERMINAL]:
        if spec.stage == "building":
            known = {t["issue"] for t in tickets_of(spec)}
            new = [c for c in children_of(ctx, spec["issue"]) if c["number"] not in known]
            if new:
                try:
                    graph = validate_graph(ctx, spec["issue"], new, known=known)
                except FactoryError as exc:
                    out.append(f"{spec.id}: new children not added: {exc}")
                else:
                    added = _add_tickets(ctx, spec, new, graph)
                    titles = {c["number"]: c["title"] for c in new}
                    ctx.gh.comment(
                        spec["issue"],
                        say(spec, "tickets nuevos incorporados:\n\n" + _graph_text(graph, titles)),
                    )
                    spec.log_event("building", "building", f"incorporated {len(added)} new tickets")
                    spec.save()
                    out += added
            out += maybe_finish_building(ctx, spec.id)
        elif spec.stage == "ready" and spec.get("pr"):
            if ctx.gh.pr(spec["pr"])["state"] == "MERGED":
                out.append(apply(ctx, spec, _done(ctx, spec)))
    return out


def maybe_finish_building(ctx: Ctx, spec_id: str | None) -> list[str]:
    """building -> final-review once every ticket of the spec is done."""
    if not spec_id:
        return []
    from lib import jobs

    try:
        spec = jobs.load(ctx.cfg, spec_id)
    except FactoryError:
        return []  # ticket jobs built by hand in tests may point at a spec that has no job
    if spec.stage != "building":
        return []
    tickets = tickets_of(spec)
    if not tickets or any(t.stage != "done" for t in tickets):
        return []
    cfg = ctx.cfg

    def make_worktree() -> None:
        git.fetch(cfg.root)
        if not spec.worktree.is_dir():
            git.worktree_add(
                cfg.root, spec.worktree, spec["branch"], git.remote_ref(spec["branch"])
            )
            git.copy_worktreeinclude(cfg.root, spec.worktree)
        spec.round_dir(1).mkdir(parents=True, exist_ok=True)

    t = Transition(
        "final-review", f"all {len(tickets)} tickets done", [make_worktree], {"round": 1}
    )
    return [apply(ctx, spec, t)]


# ---------------------------------------------------------------- actions


def action_for(ctx: Ctx, spec: Job) -> dict[str, Any] | None:
    base: dict[str, Any] = {
        "job": spec.id,
        "issue": spec["issue"],
        "stage": spec.stage,
        "cwd": str(spec.worktree),
    }
    rd = spec.round_dir()
    if spec.stage == "final-review":
        if not (rd / "checks.md").exists():
            return {
                **base,
                "action": "final-gate",
                "kind": "script",
                "command": f"factory/bin/gate {spec.id} --final",
            }
        if not (rd / "review.md").exists():
            return {
                **base,
                "action": "final-review",
                "kind": "agent",
                "agent": "reviewer",
                "model": spec["models"]["reviewer"],
                "name": f"reviewer-{spec.id}-r{spec['round']}",
                "prompt": prompts.review(spec, final=True),
            }
        return None
    if spec.stage == "final-build":
        return {
            **base,
            "action": "final-build",
            "kind": "agent",
            "agent": "builder",
            "model": spec["models"]["builder"],
            "name": f"builder-{spec.id}",
            "prompt": prompts.build(spec),
        }
    return None


# ---------------------------------------------------------------- advance


def advance(ctx: Ctx, spec: Job) -> str:
    stage = spec.stage
    if stage == "building":
        done = maybe_finish_building(ctx, spec.id)
        if done:
            return done[0]
        pending = [t.id for t in tickets_of(spec) if t.stage != "done"]
        raise FactoryError(f"{spec.id}: building; tickets not done yet: {', '.join(pending)}")
    if stage == "final-review":
        return _from_final_review(ctx, spec)
    if stage == "final-build":
        try:
            t = _from_final_build(ctx, spec)
        except contracts.ContractError as exc:
            from lib.machine import MAX_CONTRACT_FAILURES

            spec["contract_failures"] = int(spec.get("contract_failures") or 0) + 1
            spec.log_event(stage, stage, f"contract failure {spec['contract_failures']}: {exc}")
            if spec["contract_failures"] < MAX_CONTRACT_FAILURES:
                spec.save()
                raise FactoryError(
                    f"{exc}\n(contract failure {spec['contract_failures']}/{MAX_CONTRACT_FAILURES - 1}: "
                    "send this error back to the same agent once)"
                ) from exc
            t = _escalate(
                ctx, spec, "un agente incumplió el contrato de fichero dos veces", str(exc)
            )
        return apply(ctx, spec, t)
    if stage in ("ready", "needs-human"):
        if stage == "ready" and spec.get("pr") and ctx.gh.pr(spec["pr"])["state"] == "MERGED":
            return apply(ctx, spec, _done(ctx, spec))
        raise FactoryError(
            f"{spec.id}: in '{stage}' waiting for a human (merge the PR, or comment and run `job rework`)"
        )
    raise FactoryError(f"{spec.id}: no transition from '{stage}'")


def _back_to_final_build(spec: Job, reason: str, feedback_rel: str) -> Transition:
    return Transition(
        "final-build", reason, [_archive_build(spec)], {"feedback": feedback_rel, "agent": None}
    )


def _from_final_review(ctx: Ctx, spec: Job) -> str:
    cfg, rd = ctx.cfg, spec.round_dir()
    checks_path = rd / "checks.md"
    if not checks_path.exists():
        raise FactoryError(
            f"{spec.id}: {checks_path} not found; run `gate {spec.id} --final` first"
        )
    checks = contracts.read_checks(checks_path)
    if checks["GATE"] == "FAIL":
        if spec["round"] < cfg["max_rounds"]:
            return apply(
                ctx,
                spec,
                _back_to_final_build(
                    spec, f"FINAL GATE FAIL round {spec['round']}", _rel(spec, checks_path)
                ),
            )
        return apply(
            ctx,
            spec,
            _escalate(ctx, spec, f"el gate final sigue en rojo tras {spec['round']} rondas"),
        )
    review_path = rd / "review.md"
    if not review_path.exists():
        # gate passed; the final review is the next action. Release the claim, no transition.
        spec["claim"] = None
        spec.log_event(spec.stage, spec.stage, f"final gate PASS round {spec['round']}")
        spec.save()
        return f"{spec.id} final-review (final gate PASS; final review pending)"
    review = contracts.read_review(review_path, security="security" in (spec.get("surfaces") or []))
    if review["VERDICT"] == "CHANGES":
        if spec["round"] < cfg["max_rounds"]:
            return apply(
                ctx,
                spec,
                _back_to_final_build(
                    spec, f"FINAL CHANGES round {spec['round']}", _rel(spec, review_path)
                ),
            )
        return apply(
            ctx,
            spec,
            _escalate(ctx, spec, f"la review final pide cambios tras {spec['round']} rondas"),
        )
    return apply(ctx, spec, _to_ready(ctx, spec))


def _summary(spec: Job) -> str:
    rows = ["| Ticket | Estado | Rondas | Escalados |", "| --- | --- | --- | --- |"]
    total_esc = 0
    for t in sorted(tickets_of(spec), key=lambda j: j["issue"]):
        log = t.file("events.log")
        esc = (
            sum(
                1
                for line in log.read_text(encoding="utf-8").splitlines()
                if "\tneeds-human\t" in line
            )
            if log.exists()
            else 0
        )
        total_esc += esc
        rows.append(f"| #{t['issue']} {t['title']} | {t.stage} | {t['round']} | {esc} |")
    rows.append("")
    rows.append(f"Rondas finales de la spec: {spec['round']}. Escalados en tickets: {total_esc}.")
    return "\n".join(rows)


def _to_ready(ctx: Ctx, spec: Job) -> Transition:
    cfg, n = ctx.cfg, spec["issue"]
    summary = _summary(spec)
    updates: dict[str, Any] = {"agent": None, "reason": "PASS"}

    def open_pr() -> None:
        pr = ctx.gh.find_pr(spec["branch"]) or ctx.gh.create_pr(
            head=spec["branch"],
            base=cfg["base_branch"],
            title=spec["title"],
            body=f"Closes #{n}\n\n{issue_md.FACTORY_PREFIX} {spec.id} · spec construida por la fábrica.\n\n{summary}",
            draft=False,
        )
        updates["pr"] = pr["number"]

    effects: list[Effect] = [
        open_pr,
        _label(ctx, n, cfg.label("needs_human")),
        _comment(ctx, n, say(spec, f"spec lista para probar y mergear.\n\n{summary}")),
    ]
    return Transition("ready", "FINAL PASS", effects, updates)


def _from_final_build(ctx: Ctx, spec: Job) -> Transition:
    build = contracts.read_build(spec.file("build.md"))
    if build["STATUS"] == "BLOCKED":
        return _escalate(ctx, spec, "el builder final está bloqueado", build.section("Bloqueo"))
    wt = spec.worktree
    if not git.is_clean(wt):
        raise contracts.ContractError(
            spec.file("build.md"), 1, "STATUS: READY but the worktree has uncommitted changes"
        )
    git.fetch(ctx.cfg.root)
    if git.commits_ahead(wt, git.remote_ref(spec["branch"])) < 1:
        raise contracts.ContractError(
            spec.file("build.md"),
            1,
            f"STATUS: READY but there are no new commits on {spec['branch']}",
        )
    new_round = int(spec["round"]) + 1
    updates: dict[str, Any] = {"round": new_round, "agent": None}

    def push() -> None:
        git.push_branch(wt, spec["branch"])
        updates["pushed_at"] = now()
        (spec.dir / f"round-{new_round}").mkdir(parents=True, exist_ok=True)

    return Transition("final-review", "READY", [push], updates)


def _done(ctx: Ctx, spec: Job) -> Transition:
    cfg, n = ctx.cfg, spec["issue"]
    effects: list[Effect] = [
        _remove_worktree(ctx, spec, delete_branch=True),
        lambda: git.delete_remote_branch(cfg.root, spec["branch"]),
    ]
    effects += [
        _label(ctx, n, cfg.label(k), add=False) for k in ("in_progress", "needs_human", "queue")
    ]
    return Transition("done", f"PR #{spec['pr']} merged", effects, {"claim": None, "agent": None})
