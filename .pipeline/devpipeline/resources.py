"""RAM and disk limits, the heavy-suite lock, and `clean`. Local only: GitHub runners set CI and skip all of it."""
from __future__ import annotations

import contextlib
import fcntl
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .config import PipelineConfig

GB = 1024 ** 3
TEMP_PREFIX = "devpipeline-trusted-"
REPO_FOLDERS = ("results", "test-results", "playwright-report")
BROWSER_DIR = re.compile(r"^(?P<kind>.+)-(?P<rev>\d+)$")


def on_ci() -> bool:
    return bool(os.environ.get("CI"))


def lock_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".cache" / "devpipeline" / "heavy.lock"


@contextlib.contextmanager
def heavy_lock(path: Path | None = None):
    """Exclusive lock for the length of the block, so two suites never run at once on this machine.
    Closing the file releases it on every exit path, including an exception or Ctrl-C."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"waiting for another test suite to finish (lock: {path})", flush=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def free_ram_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024 / GB
    except (OSError, ValueError, IndexError):
        pass
    return None


def free_disk_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / GB


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def folder_size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _old_browsers(base: Path) -> list[Path]:
    """Browser folders except the newest revision of each kind."""
    newest: dict[str, int] = {}
    found: list[tuple[str, int, Path]] = []
    try:
        entries = [p for p in base.iterdir() if p.is_dir() and not p.is_symlink()]
    except OSError:
        return []
    for p in entries:
        m = BROWSER_DIR.match(p.name)
        if m:
            rev = int(m["rev"])
            found.append((m["kind"], rev, p))
            newest[m["kind"]] = max(newest.get(m["kind"], 0), rev)
    return [p for kind, rev, p in found if rev < newest[kind]]


PIECE_LABEL = "piece copy ("


def owned_items(repo: Path, home: Path | None = None, tmp: Path | None = None, run=None) -> list[tuple[int, Path, str]]:
    """(bytes, path, why) for everything the pipeline owns on disk, biggest first."""
    home = home or Path.home()
    tmp = tmp or Path(tempfile.gettempdir())
    out: list[tuple[int, Path, str]] = []
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    base = Path(pw) if pw and pw != "0" else home / ".cache" / "ms-playwright"
    for p in _old_browsers(base):
        out.append((folder_size(p), p, "old Playwright browser"))
    if repo.resolve() != home.resolve():
        for name in REPO_FOLDERS:
            p = repo / name
            if p.is_dir() or p.is_symlink():
                out.append((folder_size(p) if not p.is_symlink() else 0, p, "test output"))
    try:
        for p in tmp.glob(TEMP_PREFIX + "*"):
            if p.is_dir() and not p.is_symlink() and p.stat().st_uid == os.getuid():
                out.append((folder_size(p), p, "leftover `gates --keep` folder"))
    except OSError:
        pass
    from .pieces import PieceError, load_pieces, pr_state
    try:
        for pc in load_pieces(home):
            if not pc.path.is_dir():
                continue
            state = pr_state(pc, run) if run else "state not checked"
            pr = f"PR {pc.pr} {state}" if pc.pr else "no PR"
            out.append((folder_size(pc.path), pc.path, f"{PIECE_LABEL}{pc.name}, {pr})"))
    except PieceError as e:
        print(f"piece copies were not listed: {e.message}", file=sys.stderr)
    return sorted(out, key=lambda t: (-t[0], str(t[1])))


def format_items(items: list[tuple[int, Path, str]]) -> list[str]:
    return [f"  {human(size):>9}  {path}  ({why})"
            + ("; only `devpipeline piece clean` removes it" if why.startswith(PIECE_LABEL) else "")
            for size, path, why in items]


def check_resources(cfg: PipelineConfig, repo: Path, args=None) -> int | None:
    """None when fine. Otherwise prints what is short and what could be freed, and returns exit code 2."""
    if on_ci():
        return None
    if getattr(args, "no_resource_check", False):
        print("resource check is off (--no-resource-check)", flush=True)
        return None
    short = []
    ram = free_ram_gb()
    if ram is None:
        print("free RAM could not be read (no /proc/meminfo), so the RAM check was skipped", flush=True)
    elif ram < cfg.min_free_ram_gb:
        short.append(f"not enough free RAM: {ram:.1f} GB free, limit {cfg.min_free_ram_gb:g} GB (change resources.min_free_ram_gb in pipeline.yml)")
    disk = free_disk_gb(repo)
    if disk < cfg.min_free_disk_gb:
        short.append(f"not enough free disk: {disk:.1f} GB free on {repo}, limit {cfg.min_free_disk_gb:g} GB (change resources.min_free_disk_gb in pipeline.yml)")
    if not short:
        return None
    for line in short:
        print(line, file=sys.stderr)
    items = owned_items(repo)[:5]
    print("biggest items the pipeline owns (`devpipeline clean --yes` deletes them):" if items
          else "the pipeline owns nothing it could free", file=sys.stderr)
    for line in format_items(items):
        print(line, file=sys.stderr)
    print("to run anyway, pass --no-resource-check", file=sys.stderr)
    return 2


def clean(repo: Path, yes: bool, home: Path | None = None, tmp: Path | None = None, run=None) -> int:
    items = owned_items(repo, home, tmp, run)
    if not items:
        print("nothing to clean")
        return 0
    print(f"pipeline-owned disk use, biggest first ({human(sum(i[0] for i in items))} in total):")
    for line in format_items(items):
        print(line)
    if not yes:
        print("nothing was deleted. Run `devpipeline clean --yes` to delete the items above (not piece copies).")
        return 0
    freed, failed = 0, 0
    for size, path, why in items:
        if why.startswith(PIECE_LABEL):
            continue
        try:
            if path.is_symlink():
                path.unlink()
            else:
                shutil.rmtree(path)
            freed += size
            print(f"deleted {path}")
        except OSError as e:
            failed += 1
            print(f"could not delete {path}: {e.strerror}", file=sys.stderr)
    print(f"freed about {human(freed)}")
    return 1 if failed else 0
