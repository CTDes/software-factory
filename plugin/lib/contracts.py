"""File contracts between agents and bin/job (DESIGN.md · File contracts).

Every agent file starts at line 1 with `KEY: value` lines. The header ends at the first
line that is not a header line. Parsing is strict: a missing, duplicated, unknown or
out-of-range key fails with a message naming the file and the line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lib.util import FactoryError

HEADER_RE = re.compile(r"^([A-Z][A-Z_-]*):[ \t]*(.*?)[ \t]*$")
SURFACE = r"[a-z0-9][a-z0-9_-]*"
SURFACES_RE = rf"none|{SURFACE}(?:\s*,\s*{SURFACE})*"


# Section headings are English. The Spanish ones written before 0.2.0 are still accepted,
# so jobs that were in flight during the switch keep parsing. Matching ignores case.
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "Scope": ("Alcance",),
    "Acceptance criteria": ("Criterios de aceptación",),
    "Seams": (),
    "Notes": ("Notas",),
    "Question": ("Pregunta",),
    "Reason": ("Motivo",),
    "Evidence": ("Evidencia",),
    "Blocker": ("Bloqueo",),
    "Standards": ("Estándares",),
    "Spec": (),
    "Architecture": ("Arquitectura",),
    "Security": ("Seguridad",),
}


class ContractError(FactoryError):
    def __init__(self, path: Path, line: int | None, message: str) -> None:
        self.path = path
        self.line = line
        where = f"{path}:{line}" if line else str(path)
        super().__init__(f"{where}: {message}")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    pattern: str  # full-match regex for the value
    hint: str  # shown in errors, e.g. "ACCEPT|NEEDS-INFO|REJECT"


@dataclass
class Document:
    path: Path
    header: dict[str, str]
    header_lines: dict[str, int]
    sections: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> str:
        return self.header[key]

    def section(self, name: str) -> str:
        """Body of `## <name>`, also found under its pre-0.2.0 Spanish alias, ignoring case."""
        wanted = {n.casefold() for n in (name, *SECTION_ALIASES.get(name, ()))}
        for heading, body in self.sections.items():
            if heading.casefold() in wanted:
                return body
        return ""


PLAN = [
    FieldSpec("DECISION", "ACCEPT|NEEDS-INFO|REJECT", "ACCEPT|NEEDS-INFO|REJECT"),
    FieldSpec("RISK", "low|medium|high", "low|medium|high"),
    FieldSpec("SURFACES", SURFACES_RE, "none or a comma-separated list like 'ui, api'"),
]
BUILD = [FieldSpec("STATUS", "READY|BLOCKED", "READY|BLOCKED")]
CHECKS = [
    FieldSpec("GATE", "PASS|FAIL", "PASS|FAIL"),
    FieldSpec("PROTECTED", r"none|\S.*", "none or the list of protected paths touched"),
]
REVIEW = [FieldSpec("VERDICT", "PASS|CHANGES", "PASS|CHANGES")]


def _parse_sections(lines: list[str]) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in lines:
        m = re.match(r"^##[ \t]+(.+?)[ \t]*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current, buf = m.group(1), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def parse(path: Path, specs: list[FieldSpec]) -> Document:
    if not path.exists():
        raise ContractError(path, None, "file not found")
    lines = path.read_text(encoding="utf-8").splitlines()
    header: dict[str, str] = {}
    header_lines: dict[str, int] = {}
    known = {s.key: s for s in specs}
    end = 0
    for i, line in enumerate(lines, start=1):
        m = HEADER_RE.match(line)
        if not m:
            break
        key, value = m.group(1), m.group(2)
        if key not in known:
            raise ContractError(
                path, i, f"unknown header key '{key}' (expected: {', '.join(known)})"
            )
        if key in header:
            raise ContractError(path, i, f"duplicated header key '{key}'")
        if not re.fullmatch(known[key].pattern, value):
            raise ContractError(
                path, i, f"{key}: value {value!r} not allowed (expected {known[key].hint})"
            )
        header[key], header_lines[key] = value, i
        end = i
    for spec in specs:
        if spec.key not in header:
            raise ContractError(
                path,
                end + 1,
                f"missing required header line '{spec.key}: {spec.hint}' "
                f"(the header must start at line 1; it ended at line {end})",
            )
    return Document(path, header, header_lines, _parse_sections(lines[end:]))


def _require_sections(doc: Document, names: list[str], why: str) -> None:
    for name in names:
        if not doc.section(name):
            raise ContractError(doc.path, None, f"missing or empty section '## {name}' ({why})")


CRITERION_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(C\d+)\b")


def criteria_ids(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := CRITERION_RE.match(line))]


def read_plan(path: Path) -> Document:
    doc = parse(path, PLAN)
    decision = doc["DECISION"]
    if decision == "ACCEPT":
        _require_sections(
            doc, ["Scope", "Acceptance criteria", "Seams"], "required with DECISION: ACCEPT"
        )
        if not criteria_ids(doc.section("Acceptance criteria")):
            raise ContractError(
                path, None, "'## Acceptance criteria' has no criteria (lines like '- C1: …')"
            )
    elif decision == "NEEDS-INFO":
        _require_sections(doc, ["Question"], "required with DECISION: NEEDS-INFO")
    else:
        _require_sections(doc, ["Reason"], "required with DECISION: REJECT")
    return doc


def surfaces(doc: Document) -> list[str]:
    value = doc["SURFACES"]
    return [] if value == "none" else [s.strip() for s in value.split(",")]


def read_build(path: Path) -> Document:
    doc = parse(path, BUILD)
    if doc["STATUS"] == "READY":
        _require_sections(doc, ["Evidence"], "required with STATUS: READY")
    else:
        _require_sections(doc, ["Blocker"], "required with STATUS: BLOCKED")
    return doc


def read_checks(path: Path) -> Document:
    return parse(path, CHECKS)


def read_review(path: Path, security: bool) -> Document:
    doc = parse(path, REVIEW)
    required = ["Standards", "Spec", "Architecture"] + (["Security"] if security else [])
    _require_sections(doc, required, "required in every review")
    return doc


# ---------------------------------------------------------------- evidence (build.md)

# `C1: path::name`, `` C1: `path::name` `` or, for test names with spaces (node:test, pytest
# ids…), `` C1: path::`name with spaces` ``; then an optional ` — what it proves`.
EVIDENCE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<id>C\d+):\s*"
    r"(?:`(?P<path1>[^\s`]+?)::(?P<name1>[^\s`]+)`"
    r"|(?P<path2>[^\s`]+?)::`(?P<name2>[^`]+)`"
    r"|(?P<path3>[^\s`]+?)::(?P<name3>[^\s`]+))"
    r"(?:\s+(?:\u2014|\u2013|-{1,2})\s+(?P<desc>.+))?\s*$"
)


@dataclass(frozen=True)
class Evidence:
    criterion: str
    path: str
    name: str
    line: int


def parse_evidence(text: str) -> tuple[list[Evidence], list[str]]:
    """Return (evidence, malformed lines) from the body of '## Evidence'."""
    found: list[Evidence] = []
    bad: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.strip().startswith("<!--"):
            continue
        m = EVIDENCE_RE.match(line)
        if m:
            n = next(k for k in "123" if m.group(f"path{k}"))
            found.append(Evidence(m.group("id"), m.group(f"path{n}"), m.group(f"name{n}"), i))
        else:
            bad.append(line.strip())
    return found, bad
