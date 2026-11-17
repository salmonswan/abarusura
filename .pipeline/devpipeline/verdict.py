"""Final pass or fail. Rules run in a fixed order and each failure adds a reason."""
from __future__ import annotations

from .baseline import SCANNER_GATES, Baseline, is_baselinable
from .results import GateResult
from .standards import ItemStatus

CORE_GATES = ("build", "lint", "tests", "e2e", "journeys", "journey_change", "standards_doc", "protected_files", "test_workers")
OTHER_GATES = ("sbom",)
PROTECTED_PREFIX = "gate protected_files is failed"


def is_protected_reason(reason: str) -> bool:
    """A reason only the owner can clear, at the merge guard. It does not fail the `gates` check."""
    return reason.startswith(PROTECTED_PREFIX)


NO_BASELINE = "no baseline file; run `devpipeline baseline update` and commit it"


def _detail(res: GateResult) -> str:
    """Message plus the first few blocking findings, so the reason says what to fix."""
    parts = [res.message] if res.message else []
    blocking = [f for f in res.findings if f.get("blocking")]
    parts += [t for t in (f.get("summary", f["fingerprint"]) for f in blocking[:3]) if t not in res.message]
    if len(blocking) > 3:
        parts.append(f"{len(blocking) - 3} more")
    return ": " + "; ".join(parts) if parts else ""


def decide(results: dict[str, GateResult], statuses: list[ItemStatus], base: Baseline | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    reported: set[str] = set()

    # Rule 1: core gates must be passed. Never baselined.
    for gate in CORE_GATES:
        res = results.get(gate)
        if res is None:
            reasons.append(f"gate {gate} did not run")
        elif res.status != "passed":
            reasons.append(f"gate {gate} is {res.status}{_detail(res)}")
        else:
            continue
        reported.add(gate)

    # Rule 2: any other gate that errored or is missing. Never baselined.
    for gate in SCANNER_GATES + OTHER_GATES:
        res = results.get(gate)
        if res is None:
            reasons.append(f"gate {gate} did not run")
        elif res.status == "error":
            detail = f": {res.message}" if res.message else ""
            reasons.append(f"gate {gate} is error{detail}")
        else:
            continue
        reported.add(gate)
    for gate, res in results.items():
        if gate not in reported and res.status == "error":
            reasons.append(f"gate {gate} is error" + (f": {res.message}" if res.message else ""))
            reported.add(gate)

    if base is None:
        reasons.append(NO_BASELINE)
        return False, reasons

    # Rule 3: scanner gates, a blocking finding that is not in the baseline.
    for gate in SCANNER_GATES:
        res = results.get(gate)
        if res is None or gate in reported:
            continue
        known = base.findings.get(gate, set())
        blocking = [f for f in res.findings if f.get("blocking")]
        new = [f for f in blocking if f["fingerprint"] not in known]
        for f in new:
            reasons.append(f"new {gate} finding: {f.get('summary', '')} [{f['fingerprint']}]")
        if res.status == "failed" and not blocking:
            reasons.append(f"gate {gate} is failed with no finding to compare against the baseline")
        if new or (res.status == "failed" and not blocking):
            reported.add(gate)

    # Rule 4: a failed line item that is not in the baseline.
    for s in statuses:
        if s.status != "failed" or (s.item.id in base.failed_items and is_baselinable(s)):
            continue
        if s.item.check_type == "tool" and s.item.ref in reported:
            continue
        reasons.append(f"line item {s.item.id} failed: {s.evidence}")

    # Rule 5: not_covered items may not grow.
    n = sum(1 for s in statuses if s.status == "not_covered" and not s.expired)
    if n > base.not_covered_count:
        reasons.append(f"not_covered items grew from {base.not_covered_count} to {n}")

    return not reasons, reasons
