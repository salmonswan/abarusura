"""Baseline of today's findings, so an existing repo can adopt the pipeline in no-new-failures mode."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError
from .results import GateResult
from .standards import ItemStatus

SCANNER_GATES = ("secrets", "dependencies", "sast")


def is_baselinable(item) -> bool:
    """Only a line item that rests on a scanner gate may be baselined. Everything else must pass for real."""
    return item.item.check_type == "tool" and item.item.ref in SCANNER_GATES


@dataclass
class Baseline:
    findings: dict[str, set[str]] = field(default_factory=dict)
    failed_items: set[str] = field(default_factory=set)
    not_covered_count: int = 0


def build_baseline(results: dict[str, GateResult], statuses: list[ItemStatus]) -> Baseline:
    findings = {}
    for gate in SCANNER_GATES:
        res = results.get(gate)
        fps = {f["fingerprint"] for f in (res.findings if res else []) if f.get("blocking")}
        if fps:
            findings[gate] = fps
    return Baseline(
        findings=findings,
        failed_items={s.item.id for s in statuses if s.status == "failed" and is_baselinable(s)},
        not_covered_count=sum(1 for s in statuses if s.status == "not_covered" and not s.expired))


def save_baseline(b: Baseline, path: Path) -> None:
    data = {"findings": {g: sorted(v) for g, v in sorted(b.findings.items())},
            "failed_items": sorted(b.failed_items), "not_covered_count": b.not_covered_count}
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def load_baseline(path: Path) -> Baseline | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        d = json.loads(path.read_text())
        return Baseline(findings={g: set(v) for g, v in d["findings"].items()},
                        failed_items=set(d["failed_items"]), not_covered_count=int(d["not_covered_count"]))
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ConfigError(f"{path} is not a valid baseline file ({type(e).__name__}); run `devpipeline baseline update` to rewrite it") from e
