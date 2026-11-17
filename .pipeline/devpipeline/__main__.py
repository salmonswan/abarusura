"""CLI entry: python -m devpipeline [--repo PATH] <subcommand>."""
from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys
from pathlib import Path

from .config import ConfigError, app_root, load_config


def default_repo() -> tuple[Path, bool]:
    """(folder, found_via_git)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return Path(out.stdout.strip()), True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd(), False


def _cfg(args, repo: Path):
    return load_config(repo, Path(args.trusted).resolve() if getattr(args, "trusted", None) else None)


class CliError(Exception):
    """An expected failure: printed as one line, exit 2."""


def _not_implemented(name: str):
    def run(args, repo: Path) -> int:
        _cfg(args, repo)
        raise CliError(f"subcommand {name} is not implemented yet")
    return run


def _check_journeys(args, repo: Path) -> int:
    from .journeys import check_journeys
    from .results import write_result
    from .results import read_results
    cfg = _cfg(args, repo)
    result = check_journeys(cfg, e2e=read_results(cfg.results_dir).get("e2e"))
    write_result(result, cfg.results_dir)
    print(f"journeys: {result.status} ({result.scanned} scanned)")
    return 0


def _check_journey_change(args, repo: Path) -> int:
    from .journey_change import check_journey_change
    from .results import write_result
    cfg = _cfg(args, repo)
    body_path = Path(args.pr_body_file)
    if not body_path.is_file():
        raise CliError(f"{body_path} not found; pass --pr-body-file PATH (an empty file is fine)")
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{args.base}...HEAD"],
                          capture_output=True, text=True)
    if diff.returncode != 0:
        why = " ".join(diff.stderr.split())[:150]
        raise CliError(f"git diff {args.base}...HEAD failed in {repo}: {why}; fix --base or --repo")
    files = [l for l in diff.stdout.splitlines() if l.strip()]
    result = check_journey_change(files, body_path.read_text(), cfg)
    write_result(result, cfg.results_dir)
    print(f"journey_change: {result.status} ({result.scanned} changed files)")
    return 0


def _parse(args, repo: Path) -> int:
    from . import scanners
    from .results import write_result
    cfg = _cfg(args, repo)
    report = Path(args.report)
    tool = args.tool
    if tool == "gitleaks":
        if args.tracked_files is None:
            raise CliError("parse gitleaks needs --tracked-files N (from `git ls-files | wc -l`)")
        result = scanners.parse_gitleaks(report, args.tracked_files)
    elif tool == "osv":
        if args.exit_code is None:
            raise CliError("parse osv needs --exit-code N (the osv-scanner exit code)")
        result = scanners.parse_osv(report, args.exit_code, Path(args.log) if args.log else None)
    elif tool == "semgrep":
        result = scanners.parse_semgrep(report, root=repo)
    elif tool == "junit":
        if args.gate not in ("tests", "e2e"):
            raise CliError("parse junit needs --gate tests or --gate e2e")
        exit_code = args.exit_code
        if exit_code is None:
            f = cfg.results_dir / f"exec-{'test' if args.gate == 'tests' else 'e2e'}.exit"
            try:
                exit_code = int(f.read_text().strip()) if f.is_file() else None
            except ValueError:
                raise CliError(f"{f} does not hold a number; rerun `devpipeline exec` to rewrite it")
        result = scanners.parse_junit(report, args.gate, exit_code)
    else:
        result = scanners.parse_sbom(report)
    write_result(result, cfg.results_dir)
    print(f"{result.gate}: {result.status} ({result.scanned} scanned)" + (f" - {result.message}" if result.message else ""))
    return 0


def _comment_blocks(text: str) -> tuple[str, str]:
    """The comment lines at the top and at the bottom of a YAML file. yaml.safe_dump drops comments,
    so `standards suggest --write` puts these back around the new content."""
    lines = text.splitlines(keepends=True)
    is_note = lambda l: not l.strip() or l.lstrip().startswith("#")
    i = 0
    while i < len(lines) and is_note(lines[i]):
        i += 1
    if i == len(lines):
        return "".join(lines), ""
    j = len(lines)
    while j > i and is_note(lines[j - 1]):
        j -= 1
    tail = "".join(lines[j:])
    if tail and not tail.startswith("\n"):
        tail = "\n" + tail
    return "".join(lines[:i]), tail


def _standards(args, repo: Path) -> int:
    import yaml
    from . import standards as st
    from .config import package_dir
    from .results import GateResult, write_result
    cfg = _cfg(args, repo)
    cat_dir = package_dir() / "catalogue"
    md_path = repo / "docs" / "standards.md"
    if args.standards_cmd == "suggest":
        profile = st.parse_profile(repo / "docs" / "project-profile.md")
        doc = {"standards": [{"id": i, "reason": r} for i, r in st.suggest_standards(profile)]}
        if not args.write:
            print(yaml.safe_dump(doc, sort_keys=False).rstrip())
            return 0
        target = repo / "docs" / "standards.yml"
        head, tail = "", ""
        if target.is_file():
            text = target.read_text()
            head, tail = _comment_blocks(text)
            try:
                old = yaml.safe_load(text) or {}
            except yaml.YAMLError:
                raise CliError(f"{target} is not valid YAML, so --write will not replace it; fix or delete it first")
            if isinstance(old, dict):
                for keep in ("overrides", "not_applicable"):
                    if old.get(keep):
                        doc[keep] = old[keep]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(head + yaml.safe_dump(doc, sort_keys=False) + tail)
        print(f"wrote {target} with {len(doc['standards'])} standards; run `devpipeline standards render` next and commit both")
        return 0
    std_file = cfg.standards_file
    if args.standards_cmd == "check-rendered" and getattr(args, "trusted", None):
        # standards.md must match the standards.yml in the same commit. A PR that changes standards.yml
        # is caught by protected_files, so the doc check reads the PR's copy, not the base branch's.
        std_file = repo / std_file.relative_to(Path(args.trusted).resolve())
    chosen, overrides = st.load_standards_file(std_file)
    na = st.load_not_applicable(std_file)
    catalogue = st.load_catalogue(cat_dir)
    st.resolve_items([c for c, _ in chosen], overrides, catalogue, {}, "", repo, na)  # checks the keys
    fresh = st.render_markdown(chosen, None, catalogue, overrides, na)
    if args.standards_cmd == "render":
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(fresh)
        print(f"wrote {md_path}")
        return 0
    if not md_path.is_file():
        res = GateResult("standards_doc", "failed", 1, [{"fingerprint": "standards_doc:missing", "summary": f"{md_path} is missing", "blocking": True}],
                         f"{md_path} is missing; run `devpipeline standards render` and commit it")
    elif md_path.read_text() != fresh:
        res = GateResult("standards_doc", "failed", 1, [{"fingerprint": "standards_doc:stale", "summary": f"{md_path} is out of date", "blocking": True}],
                         f"{md_path} is out of date; run `devpipeline standards render` and commit it")
    else:
        res = GateResult("standards_doc", "passed", 1, [], "")
    write_result(res, cfg.results_dir)
    print(f"standards_doc: {res.status}")
    return 0


def _resolve(args, repo: Path) -> int:
    import json
    from dataclasses import asdict
    from . import standards as st
    from .config import package_dir
    from .results import read_results
    cfg = _cfg(args, repo)
    body = ""
    if args.pr_body_file:
        bp = Path(args.pr_body_file)
        if not bp.is_file():
            raise CliError(f"{bp} not found; pass --pr-body-file PATH (an empty file is fine)")
        body = bp.read_text()
    chosen, overrides = st.load_standards_file(cfg.standards_file)
    catalogue = st.load_catalogue(package_dir() / "catalogue")
    statuses = st.resolve_items([c for c, _ in chosen], overrides, catalogue, read_results(cfg.results_dir), body, repo,
                                st.load_not_applicable(cfg.standards_file),
                                st.load_reviews(cfg.standards_file.parent / "standards-review.yml"))
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    out = [{"id": s.item.id, "standard": s.item.standard, "text": s.item.text, "check_type": s.item.check_type,
            "ref": s.item.ref, "status": s.status, "evidence": s.evidence, "expired": s.expired} for s in statuses]
    (cfg.results_dir / "standards_items.json").write_text(json.dumps(out, indent=2) + "\n")
    counts = {k: sum(1 for s in statuses if s.status == k) for k in ("passed", "failed", "not_covered", "not_applicable")}
    print(f"standards items: {counts}")
    return 0


def _items_path(cfg) -> Path:
    return cfg.results_dir / "standards_items.json"


def _baseline(args, repo: Path) -> int:
    from .baseline import build_baseline, save_baseline
    from .results import read_results
    from .standards import load_items
    cfg = _cfg(args, repo)
    statuses = load_items(_items_path(cfg))
    if statuses is None:
        raise CliError(f"{_items_path(cfg)} not found; run `devpipeline resolve` first, or pass --repo PATH")
    b = build_baseline(read_results(cfg.results_dir), statuses)
    save_baseline(b, cfg.baseline_file)
    print(f"wrote {cfg.baseline_file}: {sum(len(v) for v in b.findings.values())} findings, "
          f"{len(b.failed_items)} failed items, {b.not_covered_count} not_covered. Review it and commit it.")
    return 0


def _verdict(args, repo: Path) -> int:
    import json
    from .baseline import load_baseline
    from .results import read_results
    from .standards import load_items
    from .verdict import decide
    cfg = _cfg(args, repo)
    statuses = load_items(_items_path(cfg))
    if statuses is None:
        ok, reasons = False, [f"{_items_path(cfg)} not found; run `devpipeline resolve` before `verdict`"]
    else:
        ok, reasons = decide(read_results(cfg.results_dir), statuses, load_baseline(cfg.baseline_file))
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    from .verdict import is_protected_reason
    protected_only = (not ok) and all(is_protected_reason(r) for r in reasons)
    (cfg.results_dir / "verdict.json").write_text(
        json.dumps({"ok": ok, "reasons": reasons, "protected_only": protected_only}, indent=2) + "\n")
    print("Verdict: " + ("PASS" if ok else "FAIL"))
    for r in reasons:
        print(f"- {r}")
    if protected_only:
        print("Only protected files block this PR. The gates check passes; the owner confirms at the merge guard.")
    return 0 if ok or protected_only else 1


def _report(args, repo: Path) -> int:
    import json
    from .baseline import load_baseline
    from .journeys import load_journeys
    from .report import render_report
    from .results import read_results
    from .standards import load_items
    cfg = _cfg(args, repo)
    vpath = cfg.results_dir / "verdict.json"
    if not vpath.is_file():
        raise CliError(f"{vpath} not found; run `devpipeline verdict` first (it exits 1 on FAIL, so run it with `|| true` before report), or pass --repo PATH")
    try:
        v = json.loads(vpath.read_text())
        v["ok"], v["reasons"]
    except (ValueError, KeyError, TypeError):
        raise CliError(f"{vpath} is not a valid verdict file; rerun `devpipeline verdict` to rewrite it")
    journeys, _ = load_journeys(cfg.journeys_dir)
    md = render_report(read_results(cfg.results_dir), load_items(_items_path(cfg)) or [], journeys, v["ok"], v["reasons"],
                       load_baseline(cfg.baseline_file))
    out = cfg.results_dir / "report.md"
    out.write_text(md)
    print(f"wrote {out}")
    return 0


def _merge(args, repo: Path) -> int:
    from .merge_guard import merge_pr
    try:
        app_dir = load_config(repo).app_dir
    except ConfigError as e:
        if "not found" not in e.message:
            raise
        app_dir = "."

    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, cwd=repo)
        except FileNotFoundError:
            raise CliError("the gh command was not found; install GitHub CLI and run `gh auth login`")
    return merge_pr(args.pr, run, sys.stdin.isatty(), input, app_dir)


RECORD_GATES = ("build", "lint", "pinned_deps", "test_workers")
EXEC_KEYS = ("build", "lint", "test", "e2e")
HEAVY_KEYS = ("test", "e2e")


def _record(args, repo: Path) -> int:
    from .results import GateResult, write_result
    cfg = _cfg(args, repo)
    if args.gate not in RECORD_GATES:
        raise CliError(f"cannot record gate {args.gate}; choose one of {', '.join(RECORD_GATES)}")
    if args.gate == "pinned_deps":
        from .checks import check_pinned_deps
        result = check_pinned_deps(repo, cfg.app_dir)
    elif args.gate == "test_workers":
        from .worker_caps import check_test_workers
        result = check_test_workers(repo, cfg)
    else:
        if args.exit_code is None:
            raise CliError(f"record {args.gate} needs --exit-code N (the command's exit code)")
        ok = args.exit_code == 0
        result = GateResult(args.gate, "passed" if ok else "failed", 1,
                            [] if ok else [{"fingerprint": f"{args.gate}:exit", "summary": f"{args.gate} command exited {args.exit_code}", "blocking": True}],
                            "" if ok else f"{args.gate} command exited {args.exit_code}")
    write_result(result, cfg.results_dir)
    print(f"{result.gate}: {result.status}" + (f" - {result.message}" if result.message else ""))
    return 0


def _exec(args, repo: Path) -> int:
    from .results import GateResult, write_result
    cfg = _cfg(args, repo)
    if args.key not in EXEC_KEYS:
        raise CliError(f"cannot run {args.key}; choose one of {', '.join(EXEC_KEYS)}")
    from .resources import check_resources, heavy_lock, on_ci
    refused = check_resources(cfg, repo, args)
    if refused:
        return refused
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    cmd = cfg.commands[args.key]
    workdir = app_root(cfg)
    if not workdir.is_dir():
        raise CliError(f"app_dir {cfg.app_dir} not found at {workdir}; fix app_dir in pipeline.yml or create the folder")
    heavy = args.key in HEAVY_KEYS and not on_ci()
    with heavy_lock() if heavy else contextlib.nullcontext():
        log = getattr(args, "log_file", None)
        if log:
            # Local gates: the command's own output goes to a log file, so the gate lines stay readable.
            with open(log, "w") as fh:
                fh.write(f"$ {cmd}\n")
                fh.flush()
                code = subprocess.run(cmd, shell=True, cwd=workdir, stdout=fh, stderr=subprocess.STDOUT).returncode
        else:
            print(f"$ {cmd}", flush=True)
            code = subprocess.run(cmd, shell=True, cwd=workdir).returncode
    (cfg.results_dir / f"exec-{args.key}.exit").write_text(f"{code}\n")
    if args.key in ("build", "lint"):
        ns = argparse.Namespace(gate=args.key, exit_code=code)
        return _record(ns, repo)
    print(f"{args.key} command exited {code}; run `parse junit` to judge its report")
    return 0


def _config(args, repo: Path) -> int:
    cfg = _cfg(args, repo)
    print(cfg.app_dir)
    return 0


def _init(args, repo: Path) -> int:
    from .scaffold import init_project
    skipped = init_project(repo)
    print(f"initialised {repo}")
    for p in skipped:
        print(f"kept existing file: {p}")
    print("next: edit pipeline.yml and docs/project-profile.md, run `devpipeline standards suggest --write`, then commit")
    return 0


def _sync(args, repo: Path) -> int:
    from .scaffold import sync_project
    for p in sync_project(repo):
        print(f"updated {p}")
    return 0


def _check_protected(args, repo: Path) -> int:
    from .protected import check_protected, scripts_changed
    from .results import write_result
    cfg = _cfg(args, repo)

    def git(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    diff = git("diff", "--name-only", f"{args.base}...HEAD")
    if diff.returncode != 0:
        why = " ".join(diff.stderr.split())[:150]
        raise CliError(f"git diff {args.base}...HEAD failed in {repo}: {why}; fix --base or --repo")
    files = [l for l in diff.stdout.splitlines() if l.strip()]
    pj_path = "package.json" if cfg.app_dir == "." else f"{cfg.app_dir}/package.json"
    base_pj, head_pj = git("show", f"{args.base}:{pj_path}"), git("show", f"HEAD:{pj_path}")
    changed = scripts_changed(base_pj.stdout if base_pj.returncode == 0 else None,
                              head_pj.stdout if head_pj.returncode == 0 else None)
    result = check_protected(files, changed, cfg)
    write_result(result, cfg.results_dir)
    print(f"protected_files: {result.status}" + (f" - {result.message}" if result.message else ""))
    return 0


def _read_exit(path: Path):
    try:
        return int(path.read_text().strip()), ""
    except OSError:
        return None, f"{path} is missing; the run job did not get that far"
    except ValueError:
        return None, f"{path} does not hold a number"


def _ingest(args, repo: Path) -> int:
    """Turn the run job's artifact into gate results. Reads only fixed file names."""
    from . import scanners
    from .results import GateResult, write_result
    cfg = _cfg(args, repo)
    d = Path(args.dir)
    if not d.is_dir():
        raise CliError(f"{d} is not a folder; pass the downloaded run artifact folder")
    for key in ("build", "lint"):
        code, err = _read_exit(d / f"exec-{key}.exit")
        if code is None:
            res = GateResult(key, "error", 0, [], err)
        else:
            ok = code == 0
            res = GateResult(key, "passed" if ok else "failed", 1,
                             [] if ok else [{"fingerprint": f"{key}:exit", "summary": f"{key} command exited {code}", "blocking": True}],
                             "" if ok else f"{key} command exited {code}")
        write_result(res, cfg.results_dir)
        print(f"{res.gate}: {res.status}")
    for key, gate in (("test", "tests"), ("e2e", "e2e")):
        code, err = _read_exit(d / f"exec-{key}.exit")
        res = GateResult(gate, "error", 0, [], err) if code is None else scanners.parse_junit(d / f"junit-{gate}.xml", gate, code)
        write_result(res, cfg.results_dir)
        print(f"{res.gate}: {res.status}" + (f" - {res.message}" if res.message else ""))
    return 0


def _gh_in(cmd, cwd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"the {cmd[0]} command was not found")


def _clean(args, repo: Path) -> int:
    from .config import load_config
    from .resources import clean
    try:
        results = load_config(repo).results_dir
        if results.name not in ("results", "test-results", "playwright-report"):
            print(f"note: results_dir {results} is not on the clean list; delete it by hand if you want it gone")
    except ConfigError:
        pass
    return clean(repo, args.yes, run=_gh_in)


def _guard(args, repo: Path) -> int:
    import json
    from .guard import check_call
    try:
        data = json.loads(args.call if args.call is not None else sys.stdin.read())
    except ValueError:
        raise CliError('guard reads {"tool": NAME, "input": {...}} as JSON on stdin or after --call; this was not valid JSON')
    if not isinstance(data, dict) or not isinstance(data.get("tool"), str):
        raise CliError('guard needs a JSON object with a "tool" name: {"tool": NAME, "input": {...}}')
    payload = data.get("input", {})
    if not isinstance(payload, dict):
        raise CliError('guard: "input" must be a JSON object')
    why = check_call(data["tool"], payload)
    if why:
        print(" ".join(why.split()))
        return 1
    return 0


def _piece(args, repo: Path) -> int:
    from .pieces import PieceError, clean_pieces, drop_piece, find_piece, list_pieces, open_pr, piece_status, start_piece
    try:
        if args.action == "list":
            return list_pieces()
        if args.action == "clean":
            return clean_pieces(_gh_in, args.yes)
        if args.action == "drop":
            return drop_piece(repo, args.name, args.yes)
        if args.action in ("pr", "status"):
            p = find_piece(repo, args.name)

            def run(cmd):
                try:
                    return subprocess.run(cmd, capture_output=True, text=True, cwd=p.path)
                except FileNotFoundError:
                    raise CliError(f"the {cmd[0]} command was not found; install it (gh needs `gh auth login`)") from None
            if args.action == "status":
                return piece_status(p, run, args.wait, max_wait=args.max_wait)

            def gates(copy: Path, body: Path) -> int:
                from .local_gates import run_gates
                ns = argparse.Namespace(repo=str(copy), trusted=None, base=p.base, skip_run=False, pr_body_file=str(body),
                                        no_resource_check=args.no_resource_check, keep=False, verbose=False)
                return run_gates(ns, copy, HANDLERS, CliError)
            return open_pr(p, Path(args.body_file), run, gates, dry_run=args.dry_run)
        p = start_piece(repo, args.name, Path(args.fence_file), args.base, _cfg(args, repo), args=args)
    except PieceError as e:
        raise CliError(e.message) from None
    print(p.path)
    return 0


def _gates(args, repo: Path) -> int:
    from .local_gates import run_gates
    return run_gates(args, repo, HANDLERS, CliError)


# name -> handler(args, repo) -> exit code. Later tasks replace entries.
HANDLERS: dict = {"check-journeys": _check_journeys, "check-journey-change": _check_journey_change, "piece": _piece,
            "parse": _parse, "standards": _standards, "resolve": _resolve,
            "baseline": _baseline, "verdict": _verdict, "report": _report, "merge": _merge,
            "record": _record, "exec": _exec, "init": _init, "sync": _sync,
            "check-protected": _check_protected, "ingest": _ingest, "gates": _gates, "clean": _clean, "guard": _guard, "config": _config}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="devpipeline")
    p.add_argument("--repo", help="project folder (default: git top level of the working folder)")
    p.add_argument("--trusted", help="folder holding the base branch copies of pipeline.yml, .pipeline-baseline.json and docs/standards.yml")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check-journeys", help="journeys gate")
    pa = sub.add_parser("parse", help="turn a scanner or test report into results/<gate>.json")
    pa.add_argument("tool", choices=["gitleaks", "osv", "semgrep", "junit", "sbom"])
    pa.add_argument("report", help="path of the report file")
    pa.add_argument("--exit-code", type=int, help="osv or junit: the command's exit code")
    pa.add_argument("--log", help="osv: the scanner's stderr file (proves how many packages were scanned)")
    pa.add_argument("--tracked-files", type=int, help="gitleaks: number of tracked files")
    pa.add_argument("--gate", help="junit: tests or e2e")
    sd = sub.add_parser("standards", help="suggest, render or check the standards doc")
    sd.add_argument("standards_cmd", choices=["suggest", "render", "check-rendered"])
    sd.add_argument("--write", action="store_true", help="suggest: save the suggestion to docs/standards.yml (without this flag nothing is written)")
    rs = sub.add_parser("resolve", help="resolve every standards line item to passed, failed or not_covered")
    rs.add_argument("--pr-body-file", help="file holding the PR body (for review checklist ticks)")
    bl = sub.add_parser("baseline", help="record today's findings as the baseline")
    bl.add_argument("baseline_cmd", choices=["update"])
    sub.add_parser("verdict", help="final pass or fail; exits 1 when not ok")
    sub.add_parser("report", help="write results/report.md")
    mg = sub.add_parser("merge", help="merge a PR only when its checks are green (merge guard)")
    mg.add_argument("pr", type=int, help="PR number")
    rc = sub.add_parser("record", help="record build, lint, pinned_deps or test_workers as a gate result")
    rc.add_argument("gate")
    rc.add_argument("--exit-code", type=int)
    ex = sub.add_parser("exec", help="run commands.<key> from pipeline.yml (build, lint, test, e2e)")
    ex.add_argument("key")
    ex.add_argument("--no-resource-check", action="store_true", help="do not check free RAM and disk first")
    cf = sub.add_parser("config", help="print one setting from pipeline.yml (app-dir)")
    cf.add_argument("key", choices=["app-dir"])
    sub.add_parser("init", help="add the pipeline to a project (never overwrites existing files)")
    sub.add_parser("sync", help="refresh .pipeline/ and the workflow from the template repo")
    cp = sub.add_parser("check-protected", help="gate: the PR changes files that decide how it is judged")
    cp.add_argument("--base", required=True, help="base ref, for example origin/main")
    ig = sub.add_parser("ingest", help="turn the run job's artifact folder into build, lint, tests and e2e results")
    ig.add_argument("dir")
    gt = sub.add_parser("gates", help="run the CI run and gates jobs on this machine")
    gt.add_argument("--base", default="origin/main", help="base ref to judge against (default origin/main)")
    gt.add_argument("--skip-run", action="store_true", help="do not run build, lint, tests and e2e")
    gt.add_argument("--pr-body-file", help="file holding the PR body")
    gt.add_argument("--no-resource-check", action="store_true", help="do not check free RAM and disk first")
    gt.add_argument("--keep", action="store_true", help="keep the temporary trusted folder")
    gt.add_argument("--verbose", action="store_true", help="show the build, lint, test and e2e output instead of writing it to results/exec-KEY.log")
    cl = sub.add_parser("clean", help="list the disk space the pipeline owns; delete it with --yes")
    cl.add_argument("--yes", action="store_true", help="delete the listed items (without this nothing is deleted)")
    pc = sub.add_parser("piece", help="capped repo copies for agents: start, list, drop, clean, pr, status")
    pa = pc.add_subparsers(dest="action", required=True)
    ps = pa.add_parser("start", help="make a copy on branch piece/NAME")
    ps.add_argument("name", help="letters, digits, - and _")
    ps.add_argument("--fence-file", required=True, help="file listing the globs the piece may change, one per line")
    ps.add_argument("--base", default="origin/main", help="ref to branch from (default origin/main; must exist locally)")
    ps.add_argument("--no-resource-check", action="store_true", help="do not check free RAM and disk first")
    pa.add_parser("list", help="list every piece copy on this machine")
    pd = pa.add_parser("drop", help="remove a copy, its branch and its record")
    pd.add_argument("name")
    pd.add_argument("--yes", action="store_true", help="remove it (without this nothing is removed)")
    pk = pa.add_parser("clean", help="remove every copy whose PR is merged or closed")
    pk.add_argument("--yes", action="store_true", help="remove them (without this nothing is removed)")
    pp = pa.add_parser("pr", help="check the fence, run the gates, push, open or update the PR")
    pp.add_argument("name")
    pp.add_argument("--body-file", required=True, help="file holding the PR body; a first line starting with '# ' is the title")
    pp.add_argument("--dry-run", action="store_true", help="do every check, print the push and create commands, run neither")
    pp.add_argument("--no-resource-check", action="store_true", help="do not check free RAM and disk first")
    pt = pa.add_parser("status", help="read CI back for the piece's PR: exit 0 green, 1 failed, 3 needs owner, 4 pending")
    pt.add_argument("name")
    pt.add_argument("--wait", action="store_true", help="poll until the checks are done")
    pt.add_argument("--max-wait", type=int, default=1800, help="with --wait, give up after this many seconds (default 1800; exit 4)")
    gd = sub.add_parser("guard", help='decide if an agent tool call may run: reads {"tool": NAME, "input": {...}} on stdin; exit 0 allow, 1 refuse')
    gd.add_argument("--call", help="the same JSON, given here instead of on stdin")
    jc = sub.add_parser("check-journey-change", help="gate: app code changed with no journey change")
    jc.add_argument("--base", required=True, help="base ref, for example origin/main")
    jc.add_argument("--pr-body-file", required=True, help="file holding the PR body")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.repo:
        repo, explicit = Path(args.repo).resolve(), True
    else:
        repo, explicit = default_repo()
    try:
        if args.command in ("init", "sync"):
            if not explicit:
                raise CliError(f"{args.command} needs --repo PATH or a git repository as the working folder; it will not write into {repo}")
            if repo == Path.home().resolve():
                raise CliError(f"{args.command} refuses to write into the home folder {repo}; pass --repo PATH for a project")
        handler = HANDLERS.get(args.command) or _not_implemented(args.command)
        return handler(args, repo)
    except (ConfigError, CliError) as e:
        print(getattr(e, "message", None) or str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"{e.filename or 'file error'}: {e.strerror}; check the path or pass --repo PATH", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
