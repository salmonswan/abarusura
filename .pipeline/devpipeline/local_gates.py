"""`devpipeline gates`: run the CI `run` and `gates` jobs on this machine. Reuses the CLI handlers."""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import load_config, package_dir
from .results import GateResult, read_results, write_result

INTRO = ("devpipeline gates: stages are run (build, lint, test, e2e), scanners (gitleaks, osv-scanner, semgrep, syft), "
         "checks, verdict. Flags: --skip-run, --base REF (default origin/main), --pr-body-file PATH, --keep, --no-resource-check, --verbose.")
TOOL_VERSION_ARGS = {"gitleaks": ["version"], "osv-scanner": ["--version"], "semgrep": ["--version"], "syft": ["version"]}


def tool_dirs() -> list[Path]:
    dirs = [Path(sys.executable).parent]
    try:
        checkout_tools = package_dir() / ".tools" / "bin"
        if checkout_tools.is_dir():
            dirs.append(checkout_tools)
    except Exception:
        pass
    dirs.append(Path.home() / ".local" / "bin")
    dirs += [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    return dirs


def find_tool(name: str, dirs: list[Path] | None = None) -> tuple[Path | None, list[Path]]:
    """(path or None, the folders looked in). Order: next to the interpreter, dev-pipeline .tools/bin, ~/.local/bin, PATH."""
    dirs = tool_dirs() if dirs is None else dirs
    for d in dirs:
        p = d / name
        if p.is_file() and os.access(p, os.X_OK):
            return p, dirs
    return None, dirs


def missing_gate(gate: str, tool: str, dirs: list[Path]) -> GateResult:
    looked = ", ".join(str(d) for d in dict.fromkeys(dirs))
    return GateResult(gate, "error", 0, [], f"{tool} not found; looked in: {looked}")


def locked_versions(lock: Path) -> dict[str, str]:
    out = {}
    for line in lock.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and not line.startswith("#") and parts[0] != "pip":
            out[parts[0]] = parts[1]
        elif len(parts) >= 3 and parts[0] == "pip":
            out[parts[1]] = parts[2]
    return out


def tool_version(path: Path, name: str) -> str | None:
    try:
        r = subprocess.run([str(path), *TOOL_VERSION_ARGS[name]], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\d+\.\d+\.\d+", r.stdout + r.stderr)
    return m.group(0) if m else None


def _git(repo: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def build_trusted(repo: Path, base: str, dest: Path, cli_error) -> None:
    """The same copy the workflow step 'Take the pipeline from the base branch' makes."""
    (dest / "docs").mkdir(parents=True, exist_ok=True)
    arc = subprocess.run(["git", "-C", str(repo), "archive", base, ".pipeline"], capture_output=True)
    if arc.returncode != 0:
        raise cli_error(f"{base} has no .pipeline folder; adopt the pipeline on the base branch first")
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arc.stdout, check=True)
    for name in ("pipeline.yml", ".pipeline-baseline.json", "docs/standards.yml"):
        r = _git(repo, "show", f"{base}:{name}")
        if r.returncode != 0:
            raise cli_error(f"{base} has no {name}; CI needs it on the base branch too")
        (dest / name).write_text(r.stdout)
    r = _git(repo, "show", f"{base}:docs/standards-review.yml")  # optional: no file means no reviews
    if r.returncode == 0:
        (dest / "docs" / "standards-review.yml").write_text(r.stdout)


def gate_summary(results: dict) -> str:
    """One line with the gate count by status, naming every gate that is not passed."""
    by: dict[str, list[str]] = {}
    for gate, r in sorted(results.items()):
        by.setdefault(r.status, []).append(gate)
    parts = [f"{len(by.pop('passed', []))} passed"]
    parts += [f"{len(g)} {status} ({', '.join(g)})" for status, g in sorted(by.items())]
    return "Gates: " + ", ".join(parts)


class Runner:
    def __init__(self, args, repo: Path, trusted: Path, handlers: dict, cli_error):
        self.args, self.repo, self.trusted, self.handlers, self.cli_error = args, repo, trusted, handlers, cli_error
        self.cfg = load_config(repo, trusted)
        self.results = self.cfg.results_dir
        self.shown: dict[str, tuple] = {}
        self.cfg_dir = trusted / ".pipeline" / "scanner-config"
        if not self.cfg_dir.is_dir():
            self.cfg_dir = package_dir() / "scanner-config"

    def emit(self) -> None:
        for gate, r in read_results(self.results).items():
            key = (r.status, r.message)
            if self.shown.get(gate) != key:
                self.shown[gate] = key
                print(f"{gate}: {r.status}" + (f" - {r.message}" if r.message else ""), flush=True)

    def call(self, name: str, quiet_emit: bool = False, **kw) -> int:
        ns = argparse.Namespace(trusted=str(self.trusted), **kw)
        with contextlib.redirect_stdout(io.StringIO()):
            code = self.handlers[name](ns, self.repo)
        if not quiet_emit:
            self.emit()
        return code

    def scan(self, gate: str, tool: str, parse_fn) -> None:
        path, dirs = find_tool(tool)
        if path is None:
            write_result(missing_gate(gate, tool, dirs), self.results)
        else:
            try:
                parse_fn(path)
            except OSError as e:
                write_result(GateResult(gate, "error", 0, [], f"{tool} could not run: {e}"), self.results)
        self.emit()

    def run_scanners(self) -> None:
        from . import scanners
        cfg, res, repo = self.cfg_dir, self.results, self.repo
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": repo}

        def gitleaks(p):
            subprocess.run([str(p), "detect", "--redact", "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(cfg),
                            "--config", str(cfg / "gitleaks.toml"), "--report-format", "json",
                            "--report-path", str(res / "gitleaks.json"), "--exit-code", "0", "--source", str(repo)], **quiet)
            n = len([l for l in _git(repo, "ls-files").stdout.splitlines() if l])
            write_result(scanners.parse_gitleaks(res / "gitleaks.json", n), res)

        def osv(p):
            with open(res / "osv.json", "w") as out, open(res / "osv.err", "w") as err:
                code = subprocess.run([str(p), "--config", str(cfg / "osv-scanner.toml"), "--format", "json", "-r", "."],
                                      stdout=out, stderr=err, cwd=repo).returncode
            write_result(scanners.parse_osv(res / "osv.json", code, res / "osv.err"), res)

        def semgrep(p):
            subprocess.run([str(p), "--metrics=off", "--disable-nosem", "--x-ignore-semgrepignore-files",
                            "--config", str(cfg / "semgrep-rules.yml"), "--config", "p/owasp-top-ten", "--config", "p/typescript",
                            "--json", "-o", str(res / "semgrep.json"), "--exclude", ".pipeline", "--exclude", "results",
                            "--exclude", "node_modules", "."], **quiet)
            write_result(scanners.parse_semgrep(res / "semgrep.json", root=repo), res)

        def syft(p):
            subprocess.run([str(p), ".", "-o", f"cyclonedx-json={res / 'sbom.json'}"], **quiet)
            write_result(scanners.parse_sbom(res / "sbom.json"), res)

        lock = self.trusted / ".pipeline" / "tools.lock"
        locked = locked_versions(lock if lock.is_file() else package_dir() / "tools.lock")
        for gate, tool, fn in (("secrets", "gitleaks", gitleaks), ("dependencies", "osv-scanner", osv),
                               ("sast", "semgrep", semgrep), ("sbom", "syft", syft)):
            path, _ = find_tool(tool)
            if path is not None:
                v = tool_version(path, tool)
                warn = f" (tools.lock pins {locked[tool]}; CI result may differ)" if tool in locked and v != locked[tool] else ""
                print(f"{tool} version {v or 'unknown'}{warn}", flush=True)
            self.scan(gate, tool, fn)


def run_gates(args, repo: Path, handlers: dict, cli_error) -> int:
    print(INTRO, flush=True)
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}")
    if r.returncode != 0:
        raise cli_error(f"base ref {args.base} not found in {repo}; pass --base REF (for example origin/main) or run `git fetch`")
    print(f"Judging against {args.base} at {r.stdout.strip()[:12]}", flush=True)
    body = ""
    if args.pr_body_file:
        bp = Path(args.pr_body_file)
        if not bp.is_file():
            raise cli_error(f"{bp} not found; pass --pr-body-file PATH (an empty file is fine)")
        body = bp.read_text()
    else:
        print("No --pr-body-file: journey-change reasons and review ticks in the PR body are not checked locally.", flush=True)
    st = _git(repo, "status", "--porcelain")
    if any(l and not l.startswith("??") for l in st.stdout.splitlines()):
        print("Warning: uncommitted changes to tracked files. They are scanned, but not part of the journey and protected checks.", flush=True)

    trusted = Path(tempfile.mkdtemp(prefix="devpipeline-trusted-"))
    try:
        build_trusted(repo, args.base, trusted, cli_error)
        run = Runner(args, repo, trusted, handlers, cli_error)
        from .resources import check_resources
        refused = check_resources(run.cfg, repo, args)
        if refused:
            return refused
        shutil.rmtree(run.results, ignore_errors=True)
        run.results.mkdir(parents=True)
        (run.results / "pr_body.md").write_text(body)
        if args.skip_run:
            print("Skipping the run stage (--skip-run): build, lint, tests and e2e will show as error.", flush=True)
        else:
            for key in ("build", "lint", "test", "e2e"):
                if getattr(args, "verbose", False):
                    print(f"running {key} ...", flush=True)
                    run.call("exec", key=key, no_resource_check=True)
                    continue
                log = run.results / f"exec-{key}.log"
                print(f"running {key} ... ", end="", flush=True)
                run.call("exec", key=key, no_resource_check=True, log_file=str(log), quiet_emit=True)
                ex = run.results / f"exec-{key}.exit"
                code = ex.read_text().strip() if ex.is_file() else "?"
                print(f"exit {code} (log: {log})", flush=True)
                run.emit()
        run.call("ingest", dir=str(run.results))
        run.run_scanners()
        body_file = str(run.results / "pr_body.md")
        run.call("check-journeys")
        run.call("check-journey-change", base=args.base, pr_body_file=body_file)
        run.call("check-protected", base=args.base)
        run.call("standards", standards_cmd="check-rendered", write=False)
        run.call("record", gate="pinned_deps", exit_code=None)
        run.call("record", gate="test_workers", exit_code=None)
        run.call("resolve", pr_body_file=body_file)
        print(gate_summary(read_results(run.results)), flush=True)
        code = handlers["verdict"](argparse.Namespace(trusted=str(trusted)), repo)
        run.call("report")
        print(f"Report: {run.results / 'report.md'}", flush=True)
        if args.keep:
            print(f"Trusted folder kept: {trusted}", flush=True)
        return code
    finally:
        if not args.keep:
            shutil.rmtree(trusted, ignore_errors=True)
