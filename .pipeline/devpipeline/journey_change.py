"""Gate 4: app code changed with no journey change and no reason in the PR."""
from __future__ import annotations

import re
from functools import lru_cache

from .config import PipelineConfig
from .results import GateResult

REASON_LABEL = "Journey not changed because:"


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif pattern[i] == "*":
            out.append("[^/]*"); i += 1
        elif pattern[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(pattern[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(_glob_regex(p).match(path) for p in patterns)


def _reason(pr_body: str) -> str:
    """Text after the label: rest of the line plus following lines up to a heading."""
    lines = pr_body.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(REASON_LABEL):
            parts = [line.strip()[len(REASON_LABEL):]]
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("#"):
                    break
                parts.append(nxt)
            return " ".join(p.strip() for p in parts).strip()
    return ""


def check_journey_change(changed_files: list[str], pr_body: str, cfg: PipelineConfig) -> GateResult:
    if not changed_files:
        return GateResult("journey_change", "passed", 0, [], "no changes against base")
    jdir = cfg.journeys_dir.relative_to(cfg.repo_root).as_posix().rstrip("/") + "/"
    app_changed = [f for f in changed_files if matches_any(f, cfg.app_paths)]
    journey_changed = [f for f in changed_files
                       if f.startswith(jdir) and f.endswith(".md") and not f.rsplit("/", 1)[-1].startswith("_")]
    n = len(changed_files)
    reason = _reason(pr_body)
    if not app_changed or journey_changed or reason:
        if journey_changed:
            note = "journey files changed: " + ", ".join(journey_changed)
        elif app_changed:
            note = f"no journey change; reason given: {reason}"
        else:
            note = ""
        return GateResult("journey_change", "passed", n, [], note)
    return GateResult(
        "journey_change", "failed", n,
        [{"fingerprint": "journey_change:app-without-journey", "summary": f"app code changed ({app_changed[0]}) with no journey change", "blocking": True}],
        f"app code changed with no journey change; update a journey in {jdir} or fill in '{REASON_LABEL}' in the PR body")
