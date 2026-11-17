"""Parsers that turn scanner and test output into GateResult.

A parser never raises on a bad or missing report. It returns status `error`,
because "could not judge" must fail the verdict and must not crash the run.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .results import GateResult

HIGH_CVSS = 7.0


def _error(gate: str, message: str) -> GateResult:
    return GateResult(gate, "error", 0, [], message)


def _load_json(path: Path, gate: str):
    path = Path(path)
    if not path.is_file():
        return None, _error(gate, f"report {path} not found; the scanner did not run or wrote elsewhere")
    try:
        return json.loads(path.read_text()), None
    except ValueError:
        return None, _error(gate, f"report {path} is not valid JSON; the scanner may have crashed")


def _status(findings: list[dict]) -> str:
    return "failed" if any(f.get("blocking") for f in findings) else "passed"


# gitleaks
def parse_gitleaks(report: Path, tracked_files: int) -> GateResult:
    if tracked_files <= 0:
        return _error("secrets", "no tracked files, so nothing was scanned; check the checkout and the working folder")
    data, err = _load_json(report, "secrets")
    if err:
        return err
    if not isinstance(data, list):
        return _error("secrets", f"report {report} is not a list of findings")
    findings = [{
        "fingerprint": f.get("Fingerprint") or f"{f.get('File')}:{f.get('RuleID')}:{f.get('StartLine')}",
        "summary": f"{f.get('RuleID')} in {f.get('File')}:{f.get('StartLine')}",
        "blocking": True,
    } for f in data]
    return GateResult("secrets", _status(findings), tracked_files, findings, "")


# osv-scanner
_OSV_SCANNED = re.compile(r"Scanned .* file and found (\d+) packages?\b")


def _osv_packages(log: Path | None) -> tuple[int, str]:
    """Packages scanned, from osv-scanner's stderr. osv lists only vulnerable sources in its JSON,
    so a clean run is only provable from this log. Returns (count, error message)."""
    if log is None:
        return 0, "no osv-scanner log was given, so the number of packages scanned is unknown; pass --log results/osv.err"
    log = Path(log)
    if not log.is_file():
        return 0, f"osv-scanner log {log} not found; it holds the proof that packages were scanned"
    counts = [int(m.group(1)) for m in _OSV_SCANNED.finditer(log.read_text(errors="replace"))]
    if not counts:
        return 0, f"{log} has no 'Scanned ... file and found N packages' line, so nothing was proven scanned"
    if sum(counts) == 0:
        return 0, f"osv-scanner found 0 packages in {len(counts)} file(s); the lockfiles may be empty"
    return sum(counts), ""


def parse_osv(report: Path, exit_code: int, log: Path | None = None) -> GateResult:
    gate = "dependencies"
    if exit_code == 128:
        return _error(gate, "osv-scanner found no lockfile or package source to scan; commit a lockfile or check the working folder")
    if exit_code not in (0, 1):
        return _error(gate, f"osv-scanner exited with {exit_code}, which is a tool failure and not a scan result")
    packages, log_err = _osv_packages(log)
    if log_err:
        return _error(gate, log_err)
    data, err = _load_json(report, gate)
    if err:
        return err
    if not isinstance(data, dict) or "results" not in data:
        return _error(gate, f"report {report} has no results field")
    findings = []
    for res in data["results"]:
        for pkg in res.get("packages", []):
            name, version = pkg["package"]["name"], pkg["package"]["version"]
            vulns = {v["id"]: v for v in pkg.get("vulnerabilities", [])}
            groups = pkg.get("groups") or [{"ids": [i], "max_severity": ""} for i in vulns]
            for g in groups:
                vid = g["ids"][0]
                raw = str(g.get("max_severity", "")).strip()
                try:
                    score = float(raw)
                except ValueError:
                    score = None
                blocking = score is None or score >= HIGH_CVSS
                summary = vulns.get(vid, {}).get("summary", "")
                shown = "no score" if score is None else f"CVSS {score}"
                findings.append({
                    "fingerprint": f"{vid}:{name}@{version}",
                    "summary": f"{vid} in {name}@{version} ({shown}) {summary}".strip(),
                    "blocking": blocking,
                })
    if exit_code == 1 and not findings:
        return _error(gate, "osv-scanner exited 1 (vulnerabilities found) but the report lists none")
    return GateResult(gate, _status(findings), packages, findings, "")


# semgrep
def _source_text(root: Path, rel: str, start: int, end: int) -> str | None:
    try:
        lines = (root / rel).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return "\n".join(lines[max(start - 1, 0):max(end, start)])


_BUNDLED_RULE = re.compile(r"^.*\.(pipeline\.[^.]+)$")


def _rule_id(check_id: str) -> str:
    """Semgrep prefixes a local rule file's ids with its folder path. Drop it so ids match on any machine."""
    m = _BUNDLED_RULE.match(check_id)
    return m.group(1) if m else check_id


def parse_semgrep(report: Path, root: Path | None = None) -> GateResult:
    gate = "sast"
    data, err = _load_json(report, gate)
    if err:
        return err
    scanned = (data.get("paths") or {}).get("scanned") or [] if isinstance(data, dict) else []
    if not scanned:
        return _error(gate, "semgrep scanned 0 files; check the working folder and the paths it was given")
    root = Path(root) if root else Path.cwd()
    findings, seen = [], {}
    for r in data.get("results", []):
        extra = r.get("extra", {})
        text = _source_text(root, r["path"], r["start"]["line"], r["end"]["line"])
        if text is None:
            lines = extra.get("lines", "")
            text = lines if lines and lines != "requires login" else extra.get("message", "")
        digest = hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:16]
        check_id = _rule_id(r["check_id"])
        fp = f"{check_id}:{r['path']}:{digest}"
        seen[fp] = seen.get(fp, 0) + 1
        if seen[fp] > 1:
            fp = f"{fp}#{seen[fp]}"
        sev = extra.get("severity", "")
        findings.append({
            "fingerprint": fp,
            "summary": f"{check_id} at {r['path']}:{r['start']['line']}",
            "severity": sev,
            "blocking": sev == "ERROR",
        })
    return GateResult(gate, _status(findings), len(scanned), findings, "")


# junit (vitest, playwright)
def parse_junit(path: Path, gate: str, exit_code: int | None = None) -> GateResult:
    path = Path(path)
    if not path.is_file():
        return _error(gate, f"report {path} not found; the test step did not run or wrote elsewhere")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return _error(gate, f"report {path} is not valid XML; the test runner may have crashed")
    findings, ran = [], 0
    for tc in root.iter("testcase"):
        file = tc.get("classname") or ""
        name = tc.get("name") or ""
        skipped = tc.find("skipped") is not None
        failed = tc.find("failure") is not None or tc.find("error") is not None
        if not skipped:
            ran += 1
        findings.append({
            "fingerprint": f"{gate}:{file}:{name}", "summary": name, "file": file, "name": name,
            "passed": not skipped and not failed, "blocking": failed,
            **({"skipped": True} if skipped else {}),
        })
    if ran == 0:
        return _error(gate, f"{path} holds no test that ran ({len(findings)} skipped); a run of zero tests proves nothing")
    status, message = _status(findings), ""
    if exit_code not in (None, 0) and status == "passed":
        status = "failed"
        message = f"the test command exited {exit_code} but the report shows no failed test; the runner may have crashed or misconfigured"
        findings.append({"fingerprint": f"{gate}:exit-code", "summary": message, "blocking": True})
    return GateResult(gate, status, ran, findings, message)


# syft CycloneDX
def parse_sbom(path: Path) -> GateResult:
    data, err = _load_json(path, "sbom")
    if err:
        return err
    comps = data.get("components") if isinstance(data, dict) else None
    if not comps:
        return _error("sbom", f"SBOM {path} lists 0 components; check the working folder and that a lockfile exists")
    return GateResult("sbom", "passed", len(comps), [], "")
