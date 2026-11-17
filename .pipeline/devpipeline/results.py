"""Gate results: one JSON file per gate in the results folder."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

GATE_STATUSES = ("passed", "failed", "error")


@dataclass
class GateResult:
    gate: str
    status: str
    scanned: int = 0
    findings: list[dict] = field(default_factory=list)
    message: str = ""


def write_result(result: GateResult, results_dir: Path) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{result.gate}.json"
    path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n")
    return path


KNOWN_GATES = ("build", "lint", "tests", "e2e", "journeys", "journey_change", "standards_doc", "protected_files",
               "secrets", "dependencies", "sast", "sbom", "pinned_deps", "test_workers")


def read_results(results_dir: Path) -> dict[str, GateResult]:
    """Read results/<gate>.json for each known gate and nothing else.

    A file whose `gate` field differs from its name is an error result for that gate, so code that
    runs in the job cannot forge or override a gate by dropping extra files into the folder.
    """
    out: dict[str, GateResult] = {}
    results_dir = Path(results_dir)
    for gate in KNOWN_GATES:
        path = results_dir / f"{gate}.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or data.get("status") not in GATE_STATUSES:
                raise ValueError("not a gate result")
        except (OSError, ValueError):
            out[gate] = GateResult(gate, "error", 0, [], f"{path} is not a valid gate result; delete it and rerun")
            continue
        if data.get("gate") != gate:
            out[gate] = GateResult(gate, "error", 0, [],
                                   f"{path} claims gate {data.get('gate')!r}; a result file must be named after its own gate")
            continue
        out[gate] = GateResult(gate=gate, status=data["status"], scanned=data.get("scanned", 0),
                               findings=data.get("findings", []), message=data.get("message", ""))
    return out
