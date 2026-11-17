"""`devpipeline init` and `sync`: put the pipeline into a project."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import __version__
from .baseline import Baseline, save_baseline
from .config import ConfigError, package_dir
from .standards import load_catalogue, load_standards_file, render_markdown, resolve_items

WORKFLOW = Path(".github/workflows/pipeline.yml")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _templates() -> Path:
    t = package_dir() / "templates"
    if not t.is_dir():
        raise ConfigError(f"templates folder not found at {t}; run this command from the dev-pipeline template repo (python -m devpipeline --repo PATH ...)")
    return t


def _version(pkg: Path) -> str:
    v = __version__
    try:
        out = subprocess.run(["git", "-C", str(pkg), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        v += "+" + out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return v


def _vendor(target: Path) -> None:
    pkg = package_dir()
    dest = target / ".pipeline"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(pkg / "devpipeline", dest / "devpipeline", ignore=IGNORE)
    shutil.copytree(pkg / "catalogue", dest / "catalogue", ignore=IGNORE)
    shutil.copytree(pkg / "scanner-config", dest / "scanner-config", ignore=IGNORE)
    for name in ("tools.lock", "requirements-core.lock", "requirements-semgrep.lock"):
        shutil.copy2(pkg / name, dest / name)
    (dest / "VERSION").write_text(_version(pkg) + "\n")


def _copy_omp(templates: Path, target: Path, replace: bool) -> Path:
    dest = target / ".omp"
    if replace and dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(templates / ".omp", dest, ignore=IGNORE, dirs_exist_ok=True)
    return dest


def init_project(target: Path) -> list[Path]:
    """Copy templates (never overwriting) and vendor the package. Returns the files that already existed and were kept."""
    target = Path(target)
    templates = _templates()
    skipped: list[Path] = []
    for src in sorted(p for p in templates.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        dst = target / src.relative_to(templates)
        if dst.exists():
            skipped.append(dst)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    _vendor(target)

    chosen, overrides = load_standards_file(target / "docs" / "standards.yml")
    catalogue = load_catalogue(package_dir() / "catalogue")
    md = target / "docs" / "standards.md"
    if md.exists():
        skipped.append(md)
    else:
        md.write_text(render_markdown(chosen, None, catalogue, overrides))
    baseline = target / ".pipeline-baseline.json"
    if baseline.exists():
        skipped.append(baseline)
    else:
        statuses = resolve_items([c for c, _ in chosen], overrides, catalogue, {}, "", target)
        save_baseline(Baseline({}, set(), sum(1 for s in statuses if s.status == "not_covered")), baseline)
    return skipped


def sync_project(target: Path) -> list[Path]:
    """Replace only .pipeline/ and the workflow. Never touches project docs. Returns the files written."""
    target = Path(target)
    templates = _templates()
    _vendor(target)
    wf = target / WORKFLOW
    wf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(templates / WORKFLOW, wf)
    omp = _copy_omp(templates, target, replace=True)
    return [target / ".pipeline", wf, omp]
