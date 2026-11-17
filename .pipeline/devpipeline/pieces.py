"""Piece copies: capped git worktrees of a repo, one per omp agent task. Local only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .journey_change import matches_any
from .merge_guard import PROTECTED_CHECK, check_state, latest_runs
from .resources import check_resources
from .results import read_results

NAME_RULE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class PieceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ResourcesShort(PieceError):
    """check_resources refused and already printed why."""


@dataclass
class Piece:
    name: str
    repo: Path
    path: Path
    branch: str
    base: str
    fence: list[str]
    pr: int | None = None


def pieces_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".cache" / "devpipeline" / "pieces"


def _record_path(path: Path) -> Path:
    return path.parent / (path.name + ".piece.json")


def save_piece(p: Piece, home: Path | None = None) -> None:
    d = pieces_dir(home)
    d.mkdir(parents=True, exist_ok=True)
    data = {**asdict(p), "repo": str(p.repo), "path": str(p.path)}
    _record_path(p.path).write_text(json.dumps(data, indent=2) + "\n")


def load_pieces(home: Path | None = None) -> list[Piece]:
    out = []
    for f in sorted(pieces_dir(home).glob("*.piece.json")):
        try:
            d = json.loads(f.read_text())
            out.append(Piece(d["name"], Path(d["repo"]), Path(d["path"]), d["branch"], d["base"],
                             list(d["fence"]), d.get("pr")))
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise PieceError(f"{f} is not a valid piece record ({type(e).__name__}); delete it or fix it") from e
    return out


def _copy_path(repo: Path, name: str, home: Path | None) -> Path:
    return pieces_dir(home) / f"{Path(repo).resolve().name}-{name}"


def find_piece(repo: Path, name: str, home: Path | None = None) -> Piece:
    rec = _record_path(_copy_path(repo, name, home))
    if rec.is_file():
        for p in load_pieces(home):
            if _record_path(p.path) == rec:
                return p
    raise PieceError(f"no piece named {name} for {Path(repo).resolve()}; run `devpipeline piece list` to see the pieces")


def _git(repo: Path, *a: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    except FileNotFoundError:
        raise PieceError("git was not found; install git") from None


def _why(r: subprocess.CompletedProcess) -> str:
    lines = (r.stderr or r.stdout).strip().splitlines()
    return lines[-1] if lines else f"exit {r.returncode}"


def _read_fence(fence_file: Path) -> list[str]:
    try:
        text = Path(fence_file).read_text()
    except OSError as e:
        raise PieceError(f"{fence_file} could not be read ({e.strerror}); pass --fence-file PATH") from None
    globs = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not globs:
        raise PieceError(f"{fence_file} has no globs; list the files the piece may change, one glob per line")
    return globs


def start_piece(repo: Path, name: str, fence_file: Path, base: str, cfg, home: Path | None = None,
                args=None) -> Piece:
    repo = Path(repo).resolve()
    if not NAME_RULE.match(name):
        raise PieceError(f"piece name {name!r} is not allowed; use 1 to 40 letters, digits, - and _")
    branch = f"piece/{name}"
    path = _copy_path(repo, name, home)
    if _record_path(path).exists() or path.exists():
        raise PieceError(f"a piece named {name} already exists for {repo.name}; use another name or run `devpipeline piece drop {name}`")
    if _git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0:
        raise PieceError(f"branch {branch} already exists in {repo}; run `devpipeline piece drop {name}` or delete the branch")
    fence = _read_fence(fence_file)
    active = load_pieces(home)
    if len(active) >= cfg.max_piece_copies:
        names = ", ".join(f"{p.name} ({p.repo.name})" for p in active)
        raise PieceError(f"{len(active)} of {cfg.max_piece_copies} piece copies in use: {names}; "
                         f"drop one with `devpipeline piece drop NAME --yes` or raise resources.max_piece_copies")
    if check_resources(cfg, repo, args) is not None:
        raise ResourcesShort("not making a piece copy: the machine is short of resources (see above)")
    if _git(repo, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").returncode != 0:
        raise PieceError(f"base {base} not found in {repo}; fetch it first or pass --base REF")
    path.parent.mkdir(parents=True, exist_ok=True)
    r = _git(repo, "worktree", "add", "-b", branch, str(path), base)
    if r.returncode != 0:
        raise PieceError(f"git worktree add failed in {repo}: {_why(r)}")
    p = Piece(name, repo, path, branch, base, fence, None)
    save_piece(p, home)
    return p


def drop_piece(repo: Path, name: str, yes: bool, home: Path | None = None, pr_done: bool = False) -> int:
    p = find_piece(repo, name, home)
    print(f"piece {p.name}: copy {p.path}, branch {p.branch}, record {_record_path(p.path)}")
    if p.pr and not pr_done:
        print(f"PR #{p.pr} is left open; dropping the copy does not close it")
    if not yes:
        print(f"nothing was removed. Run `devpipeline piece drop {p.name} --yes` to remove the copy, branch and record.")
        return 0
    if p.path.is_dir():
        st = _git(p.path, "status", "--porcelain")
        if st.returncode != 0:
            raise PieceError(f"git status failed in {p.path}: {_why(st)}")
        if st.stdout.strip():
            raise PieceError(f"commit or discard the changes in {p.path} first")
        r = _git(p.repo, "worktree", "remove", str(p.path))
        if r.returncode != 0:
            raise PieceError(f"git worktree remove failed for {p.path}: {_why(r)}")
    else:
        _git(p.repo, "worktree", "prune")
    r = _git(p.repo, "branch", "-D", p.branch)
    if r.returncode != 0 and _git(p.repo, "rev-parse", "--verify", "-q", f"refs/heads/{p.branch}").returncode == 0:
        raise PieceError(f"could not delete branch {p.branch}: {_why(r)}")
    _record_path(p.path).unlink(missing_ok=True)
    print(f"removed piece {p.name}")
    return 0


def pr_state(p: Piece, run) -> str | None:
    """OPEN, MERGED or CLOSED from gh. None when the piece has no PR. "unknown" when gh failed.
    run(cmd, cwd) runs a command in the piece copy."""
    if not p.pr:
        return None
    r = run(["gh", "pr", "view", str(p.pr), "--json", "state"], p.path)
    if r.returncode != 0:
        return "unknown"
    try:
        state = str(json.loads(r.stdout)["state"]).upper()
    except (ValueError, KeyError, TypeError):
        return "unknown"
    return state if state in ("OPEN", "MERGED", "CLOSED") else "unknown"


def clean_pieces(run, yes: bool, home: Path | None = None) -> int:
    """Remove copies whose PR merged or closed. Everything else is kept, and the line says why."""
    items = load_pieces(home)
    if not items:
        print("no pieces")
        return 0
    removable, failed = [], 0
    for p in items:
        state = pr_state(p, run)
        tag = f"{p.name} ({p.repo.name})"
        if state is None:
            print(f"keep {tag}: no PR yet")
        elif state == "unknown":
            print(f"keep {tag}: PR state unknown (gh could not read PR #{p.pr})")
        elif state == "OPEN":
            print(f"keep {tag}: PR #{p.pr} is still open")
        else:
            print(f"{'remove' if yes else 'would remove'} {tag}: PR #{p.pr} is {state}")
            removable.append(p)
    if not yes:
        print(f"nothing was removed. Run `devpipeline piece clean --yes` to remove {len(removable)} {'copy' if len(removable) == 1 else 'copies'}." if removable
              else "nothing to remove")
        return 0
    for p in removable:
        try:
            drop_piece(p.repo, p.name, True, home, pr_done=True)
        except PieceError as e:
            failed += 1
            print(f"kept {p.name}: {e.message}", file=sys.stderr)
    return 1 if failed else 0


def list_pieces(home: Path | None = None) -> int:
    items = load_pieces(home)
    if not items:
        print("no pieces")
    for p in items:
        print(f"{p.name}  {p.repo.name}  {p.branch}  " + (f"PR #{p.pr}" if p.pr else "no PR"))
    return 0


LOCKFILES = {"package-lock.json": "package.json", "pnpm-lock.yaml": "package.json", "yarn.lock": "package.json",
             "poetry.lock": "pyproject.toml", "uv.lock": "pyproject.toml"}


def fence_violations(changed: list[str], fence: list[str]) -> list[str]:
    """Changed files outside the fence. A lockfile is fine when its manifest, in the same folder, is inside."""
    out = []
    for f in changed:
        if matches_any(f, fence):
            continue
        d, _, base = f.rpartition("/")
        manifest = LOCKFILES.get(base)
        if manifest and matches_any(f"{d}/{manifest}" if d else manifest, fence):
            continue
        out.append(f)
    return out


def _title(body_file: Path, name: str) -> str:
    for line in Path(body_file).read_text().splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return name


def _changed_files(p: Piece) -> list[str]:
    st = _git(p.path, "status", "--porcelain")
    if st.returncode != 0:
        raise PieceError(f"git status failed in {p.path}: {_why(st)}")
    if any(ln and not ln.startswith("??") for ln in st.stdout.splitlines()):
        raise PieceError(f"commit your changes first: {p.path} has uncommitted changes to tracked files")
    d = _git(p.path, "diff", "--name-only", f"{p.base}...HEAD")
    if d.returncode != 0:
        raise PieceError(f"git diff against {p.base} failed in {p.path}: {_why(d)}")
    return [ln for ln in d.stdout.splitlines() if ln.strip()]


def _gh_failed(cmd: list[str], r: subprocess.CompletedProcess) -> int:
    excerpt = " ".join((r.stderr or "").split())[:300]
    print(f"{' '.join(cmd[:3])} failed (exit {r.returncode}): {excerpt}", file=sys.stderr)
    return 2


def open_pr(p: Piece, body_file: Path, run, gates, dry_run: bool = False, home: Path | None = None) -> int:
    body_file = Path(body_file)
    if not body_file.is_file():
        raise PieceError(f"{body_file} not found; pass --body-file PATH with the PR text")
    changed = _changed_files(p)
    if not changed:
        raise PieceError(f"{p.branch} has no commits against {p.base}; commit the work first")
    bad = fence_violations(changed, p.fence)
    if bad:
        print(f"refused: {len(bad)} changed file(s) are outside the fence of piece {p.name}:")
        for f in bad:
            print(f"  {f}")
        print("Undo those changes, or start a new piece with a wider fence.")
        return 1
    code = gates(p.path, body_file)
    if code != 0:
        print(f"refused: the local gates did not pass (exit {code}); fix them before pushing")
        return 1
    push = ["git", "push", "-u", "origin", p.branch]
    create = ["gh", "pr", "create", "--head", p.branch, "--body-file", str(body_file), "--title", _title(body_file, p.name)]
    if dry_run:
        print("dry run: checks and gates passed. Not run:")
        print("  " + " ".join(push))
        if not p.pr:
            print("  " + " ".join(create))
        return 0
    r = run(push)
    if r.returncode != 0:
        return _gh_failed(push, r)
    if p.pr:
        print(f"pushed {p.branch}; PR #{p.pr} is updated")
        return 0
    r = run(create)
    if r.returncode != 0:
        return _gh_failed(create, r)
    view = ["gh", "pr", "view", p.branch, "--json", "number"]
    r = run(view)
    if r.returncode != 0:
        return _gh_failed(view, r)
    try:
        p.pr = int(json.loads(r.stdout)["number"])
    except (ValueError, KeyError, TypeError):
        raise PieceError("gh pr view did not return a PR number; the PR was made, run `gh pr view` to find it") from None
    save_piece(p, home)
    print(f"pushed {p.branch}; opened PR #{p.pr}")
    return 0


def _artifact_dir(tmp: Path) -> Path:
    """The artifact is the contents of results/. Accept it at the root or inside a folder."""
    for sub in (".", "pipeline-results", "results"):
        if (tmp / sub / "verdict.json").is_file() or any((tmp / sub).glob("*.json")):
            return tmp / sub
    return tmp


def _print_failure(p: Piece, run, head: str, gate_names: list[str], protected_only: bool) -> None:
    lst = ["gh", "run", "list", "--branch", p.branch, "--workflow", "pipeline", "--json", "databaseId,headSha", "-L", "5"]
    r = run(lst)
    run_id = None
    if r.returncode == 0:
        try:
            run_id = next((x["databaseId"] for x in json.loads(r.stdout) if x.get("headSha") == head), None)
        except (ValueError, KeyError, TypeError):
            run_id = None
    else:
        _gh_failed(lst, r)
    if run_id is None:
        print(f"could not find the pipeline run for commit {head[:12]}; look at the PR checks: {', '.join(gate_names)}")
        return
    with tempfile.TemporaryDirectory(prefix="devpipeline-status-") as tmp:
        dl = ["gh", "run", "download", str(run_id), "-n", "pipeline-results", "-D", tmp]
        r = run(dl)
        if r.returncode != 0:
            _gh_failed(dl, r)
            print(f"could not read the results of run {run_id}; failing checks: {', '.join(gate_names)}")
            return
        d = _artifact_dir(Path(tmp))
        results = read_results(d)
        if protected_only:
            prot = results.get("protected_files")
            files = [f.get("summary", "") for f in (prot.findings if prot else [])]
            print("Only protected files are red. The owner confirms these at the merge guard:")
            for f in files:
                print(f"  {f}")
            return
        reasons = []
        try:
            reasons = list(json.loads((d / "verdict.json").read_text()).get("reasons", []))
        except (OSError, ValueError, AttributeError):
            pass
        if not reasons:
            reasons = [f"gate {g} is {r_.status}" + (f": {r_.message}" if r_.message else "")
                       for g, r_ in results.items() if r_.status != "passed"]
        if not reasons:
            reasons = [f"check {n} failed; the results hold no reason" for n in gate_names]
        for line in reasons:
            print(f"- {line}")


def piece_status(p: Piece, run, wait: bool, sleep=time.sleep, interval: int = 30, max_wait: int = 1800) -> int:
    if not p.pr:
        raise PieceError(f"piece {p.name} has no PR yet; run `devpipeline piece pr {p.name} --body-file PATH` first")
    cmd = ["gh", "pr", "view", str(p.pr), "--json", "statusCheckRollup,headRefOid"]
    waited = 0
    while True:
        r = run(cmd)
        if r.returncode != 0:
            return _gh_failed(cmd, r)
        try:
            info = json.loads(r.stdout)
            checks = info["statusCheckRollup"] or []
            head = info["headRefOid"] or ""
        except (ValueError, KeyError, TypeError):
            print(f"could not read the PR {p.pr} data from gh; update gh or check the PR number", file=sys.stderr)
            return 2
        states = [check_state(c) for c in latest_runs(checks)]
        bad = [n for n, s, _ in states if s == "bad" and n != PROTECTED_CHECK]
        pending = [n for n, s, _ in states if s == "pending"]
        waiting = bool(pending) or not states
        if not waiting or not wait:
            break
        if waited >= max_wait:
            print(f"PR #{p.pr}: gave up after {waited}s (--max-wait); still pending: {', '.join(pending) or 'no checks yet'}")
            return 4
        print(f"PR #{p.pr}: waiting for {', '.join(pending) or 'checks to start'} ...", flush=True)
        sleep(interval)
        waited += interval
    if bad and waiting:
        print(f"PR #{p.pr}: failed checks: {', '.join(bad)}; still pending: {', '.join(pending) or 'no checks yet'}")
        return 4
    if bad:
        print(f"PR #{p.pr}: failed checks: {', '.join(bad)}")
        _print_failure(p, run, head, bad, False)
        return 1
    if waiting:
        print(f"PR #{p.pr}: still pending: {', '.join(pending) or 'no checks yet'}")
        return 4
    if any(s == "bad" for _, s, _ in states):
        print(f"PR #{p.pr}: needs the owner (only {PROTECTED_CHECK} is red)")
        _print_failure(p, run, head, [PROTECTED_CHECK], True)
        return 3
    print(f"PR #{p.pr}: green")
    return 0
