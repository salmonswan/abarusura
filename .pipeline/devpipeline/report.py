"""Markdown run report. Posted as a PR comment and saved as results/report.md."""
from __future__ import annotations

from .journeys import Journey, journey_state
from .results import GateResult
from .standards import ItemStatus
from .verdict import CORE_GATES, OTHER_GATES
from .baseline import SCANNER_GATES, Baseline

MARKER = "<!-- devpipeline-report -->"
EXPECTED_GATES = CORE_GATES + SCANNER_GATES + OTHER_GATES
STATUSES = ("passed", "failed", "not_covered", "not_applicable")
MAX_WARNINGS = 20


def _warnings(results: dict[str, GateResult], names: list[str]) -> list[str]:
    """Non-blocking findings. Test cases that passed or were skipped are not warnings."""
    out = []
    for name in names:
        res = results.get(name)
        for f in res.findings if res else []:
            if f.get("blocking") or "passed" in f:
                continue
            out.append(f"{name}: {f.get('summary') or f.get('fingerprint', '')}")
    return out


def _stale(results: dict[str, GateResult], base: Baseline | None) -> list[str]:
    """Baselined findings that the scanners no longer report. A gate that errored proves nothing, so it is skipped."""
    out = []
    for gate in SCANNER_GATES:
        res = results.get(gate)
        if base is None or res is None or res.status == "error":
            continue
        seen = {f.get("fingerprint") for f in res.findings}
        out += [f"{gate}: {fp}" for fp in sorted(base.findings.get(gate, set()) - seen)]
    return out


def render_report(results: dict[str, GateResult], statuses: list[ItemStatus], journeys: list[Journey],
                  ok: bool, reasons: list[str], base: Baseline | None = None) -> str:
    out = [MARKER, "", f"Verdict: {'PASS' if ok else 'FAIL'}", ""]

    prot = results.get("protected_files")
    if prot is not None and prot.status == "failed":
        out += ["## Protected files", "",
                "This PR changes files that decide how it is judged. Only the owner can confirm this, at the merge guard:", ""]
        out += [f"- {f['summary']}" for f in prot.findings]
        out.append("")

    out += ["## Reasons", ""]
    out += [f"- {r}" for r in reasons] if reasons else ["None."]
    out.append("")

    out += ["## Gates", "", "| Gate | Status | Scanned | Blocking findings |", "|---|---|---|---|"]
    names = list(EXPECTED_GATES) + sorted(g for g in results if g not in EXPECTED_GATES)
    for name in names:
        res = results.get(name)
        if res is None:
            out.append(f"| {name} | did not run | 0 | 0 |")
        else:
            blocking = sum(1 for f in res.findings if f.get("blocking"))
            out.append(f"| {name} | {res.status} | {res.scanned} | {blocking} |")
    out.append("")

    warns = _warnings(results, names)
    expired = sum(1 for s in statuses if s.expired)
    if expired:
        warns.append(f"{expired} reviewed items expired; review them again")
    if warns:
        out += ["## Warnings", "", "These do not block the PR. A person should look at them.", ""]
        out += [f"- {w}" for w in warns[:MAX_WARNINGS]]
        if len(warns) > MAX_WARNINGS:
            out.append(f"- {len(warns) - MAX_WARNINGS} more")
        out.append("")

    stale = _stale(results, base)
    if stale:
        out += ["## Stale baseline entries", "",
                f"{len(stale)} baselined finding(s) are no longer found. This is not a failure. "
                "Run `devpipeline baseline update` on main to remove them.", ""]
        out += [f"- {x}" for x in stale[:MAX_WARNINGS]]
        if len(stale) > MAX_WARNINGS:
            out.append(f"- {len(stale) - MAX_WARNINGS} more")
        out.append("")

    notes = [f"- {n}: {results[n].message}" for n in names if n in results and results[n].status == "passed" and results[n].message]
    if notes:
        out += ["## Notes", ""] + notes + [""]

    out += ["## Journeys", ""]
    states = {j.name: journey_state(j, results.get("e2e")) for j in journeys}
    out += [f"- {n}: {s}" for n, s in states.items()] if states else ["No journeys found."]
    out.append("")

    out += ["## Standards", ""]
    stds = list(dict.fromkeys(s.item.standard for s in statuses))
    for sid in stds:
        c = {k: sum(1 for s in statuses if s.item.standard == sid and s.status == k) for k in STATUSES}
        out.append(f"- {sid}: {c['passed']} passed, {c['failed']} failed, {c['not_covered']} not_covered, {c['not_applicable']} not_applicable")
    if not stds:
        out.append("No standards items resolved.")
    failed = [s for s in statuses if s.status == "failed"]
    if failed:
        out += ["", "Failed items:", ""]
        out += [f"- {s.item.id}: {s.evidence}" for s in failed]
    out.append("")

    out += ["## Not tested", ""]
    nt = []
    for n, s in states.items():
        if s != "passed":
            nt.append(f"- Journey {n} has no passing journey test ({s}).")
    for sid in stds:
        n = sum(1 for s in statuses if s.item.standard == sid and s.status == "not_covered")
        if n:
            nt.append(f"- {sid}: {n} line items not covered.")
    for name in names:
        res = results.get(name)
        if res is None:
            nt.append(f"- Gate {name} did not run.")
        elif res.status == "error":
            nt.append(f"- Gate {name} could not judge: {res.message or 'no message'}")
    out += nt if nt else ["Nothing listed."]
    out.append("")
    return "\n".join(out)
