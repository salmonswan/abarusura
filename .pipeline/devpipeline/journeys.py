"""Journey docs: parsing and the journeys gate."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import PipelineConfig
from .results import GateResult

LABELS = ("User", "Steps", "Expect", "Failure paths", "Covered by")
_LABEL_RE = re.compile(r"^(User|Steps|Expect|Failure paths|Covered by):\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+")


class JourneyFormatError(Exception):
    def __init__(self, path: Path, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass
class Journey:
    name: str
    path: Path
    user: str
    steps: list[str] = field(default_factory=list)
    expect: list[str] = field(default_factory=list)
    failure_paths: list[str] = field(default_factory=list)
    covered_by: list[str] = field(default_factory=list)


def parse_journey(path: Path) -> Journey:
    path = Path(path)
    lines = path.read_text().splitlines()
    first = next((l for l in lines if l.strip()), "")
    m = re.match(r"^#\s*Journey:\s*(.+?)\s*$", first)
    if not m:
        raise JourneyFormatError(path, "first line must be `# Journey: <name>`")
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines[lines.index(first) + 1:]:
        lm = _LABEL_RE.match(line)
        if lm:
            current = lm.group(1)
            sections.setdefault(current, [])
            if lm.group(2).strip():
                sections[current].append(lm.group(2).strip())
        elif current and line.strip():
            sections[current].append(_BULLET_RE.sub("", line).strip())
    for label in LABELS:
        if not sections.get(label):
            raise JourneyFormatError(path, f"missing or empty section `{label}:`")
    covered = [p.strip() for chunk in sections["Covered by"] for p in chunk.split(",") if p.strip()]
    return Journey(
        name=m.group(1), path=path, user=" ".join(sections["User"]), steps=sections["Steps"],
        expect=sections["Expect"], failure_paths=sections["Failure paths"], covered_by=covered)


def load_journeys(journeys_dir: Path) -> tuple[list[Journey], list[tuple[Path, str]]]:
    """Returns (parsed journeys, [(path, error message)]). Files starting with _ are templates."""
    journeys, errors = [], []
    if journeys_dir.is_dir():
        for p in sorted(journeys_dir.glob("*.md")):
            if p.name.startswith("_"):
                continue
            try:
                journeys.append(parse_journey(p))
            except JourneyFormatError as e:
                errors.append((p, e.message))
    return journeys, errors


def journey_state(j: Journey, e2e: GateResult | None) -> str:
    """passed, failed or not run, judged from the e2e test cases of the journey's Covered by files."""
    cases = []
    for f in (e2e.findings if e2e else []):
        file = f.get("file", "")
        if file and any(ref == file or ref.endswith("/" + file) for ref in j.covered_by):
            cases.append(f)
    if any(not c.get("passed") and not c.get("skipped") for c in cases):
        return "failed"
    return "passed" if any(c.get("passed") for c in cases) else "not run"


def check_journeys(cfg: PipelineConfig, e2e: GateResult | None = None) -> GateResult:
    journeys, errors = load_journeys(cfg.journeys_dir)
    scanned = len(journeys) + len(errors)
    if scanned == 0:
        return GateResult("journeys", "error", 0, [],
                          f"no journey files found in {cfg.journeys_dir}; files starting with _ are templates and do not count")
    findings = []
    root = cfg.repo_root
    for p, msg in errors:
        rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
        findings.append({"fingerprint": f"journeys:{rel}:format", "summary": f"{rel}: {msg}", "blocking": True})
    for j in journeys:
        rel = j.path.relative_to(root).as_posix() if j.path.is_relative_to(root) else str(j.path)
        for cov in j.covered_by:
            if not cov.startswith(cfg.e2e_dir + "/"):
                findings.append({
                    "fingerprint": f"journeys:{rel}:{cov}",
                    "summary": f"journey '{j.name}' ({rel}) is covered by {cov}, which is not under {cfg.e2e_dir}/ where journey tests must live",
                    "blocking": True})
            elif not (root / cov).is_file():
                findings.append({
                    "fingerprint": f"journeys:{rel}:{cov}",
                    "summary": f"journey '{j.name}' ({rel}) is covered by {cov}, which does not exist", "blocking": True})
    if e2e is not None:
        for j in journeys:
            state = journey_state(j, e2e)
            if state != "passed":
                rel = j.path.relative_to(root).as_posix() if j.path.is_relative_to(root) else str(j.path)
                findings.append({
                    "fingerprint": f"journeys:{rel}:not-run",
                    "summary": f"journey '{j.name}' ({rel}) has no passing journey test: {', '.join(j.covered_by)} did not run, was skipped or failed",
                    "blocking": True})
    status = "failed" if findings else "passed"
    return GateResult("journeys", status, scanned, findings, "")
