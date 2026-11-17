"""Small repo checks that need no external tool."""
from __future__ import annotations

import json
from pathlib import Path

from .results import GateResult

LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock")
DEP_KEYS = ("dependencies", "devDependencies", "optionalDependencies")


def check_pinned_deps(repo_root: Path, app_dir: str = ".") -> GateResult:
    root = Path(repo_root) / app_dir
    pj = root / "package.json"
    if not pj.is_file():
        return GateResult("pinned_deps", "error", 0, [], f"{pj} not found; this check reads package.json, pass --repo PATH for a web project")
    try:
        data = json.loads(pj.read_text())
    except ValueError:
        return GateResult("pinned_deps", "error", 0, [], f"{pj} is not valid JSON")
    deps = {k: v for key in DEP_KEYS for k, v in (data.get(key) or {}).items()}
    if any((root / lf).is_file() for lf in LOCKFILES):
        return GateResult("pinned_deps", "passed", len(deps), [], "")
    loose = sorted(k for k, v in deps.items() if str(v).startswith(("^", "~")))
    findings = [{"fingerprint": f"pinned_deps:{k}", "summary": f"{k} uses range {deps[k]} and no lockfile is committed", "blocking": True}
                for k in loose]
    msg = "no lockfile is committed; commit package-lock.json or pin exact versions" if loose else ""
    return GateResult("pinned_deps", "failed" if loose else "passed", len(deps), findings, msg)
