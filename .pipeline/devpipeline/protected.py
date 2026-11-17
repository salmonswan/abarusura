"""Gate protected_files: a PR may not change the files that decide how it is judged."""
from __future__ import annotations

import json

from .config import PipelineConfig
from .journey_change import matches_any
from .results import GateResult

PROTECTED_PATTERNS = [
    ".pipeline/**", ".github/**", ".omp/**", "pipeline.yml", ".pipeline-baseline.json", "docs/standards.yml", "docs/standards-review.yml",
    ".nvmrc", ".npmrc", ".semgrepignore", ".gitleaksignore", ".gitleaks*", "osv-scanner.toml", ".osv-scanner.toml",
    "**/vitest.config.*", "**/vitest.workspace.*", "**/playwright.config.*", "**/vite.config.*", "**/jest.config.*", "**/pytest.ini",
]


def protected_patterns(app_dir: str = ".") -> list[str]:
    """The built-in patterns. A web app in a subfolder also has its own .nvmrc and .npmrc."""
    if app_dir in (".", ""):
        return list(PROTECTED_PATTERNS)
    return PROTECTED_PATTERNS + [f"{app_dir}/.nvmrc", f"{app_dir}/.npmrc"]


SCRIPTS_MARK = "package.json#scripts"


def scripts_changed(base_text: str | None, head_text: str | None) -> bool:
    """True when package.json `scripts` differ. Unreadable head text counts as changed."""
    def scripts(text):
        if text is None:
            return {}
        return json.loads(text).get("scripts") or {}
    try:
        return scripts(base_text) != scripts(head_text)
    except (ValueError, AttributeError):
        return True


def check_protected(changed_files: list[str], package_scripts_changed: bool, cfg: PipelineConfig) -> GateResult:
    if not changed_files:
        return GateResult("protected_files", "passed", 0, [], "no changes against base")
    patterns = protected_patterns(cfg.app_dir) + cfg.protected_paths
    hits = sorted(f for f in changed_files if matches_any(f, patterns))
    if package_scripts_changed:
        hits.append(SCRIPTS_MARK)
    if not hits:
        return GateResult("protected_files", "passed", len(changed_files), [], "")
    findings = [{"fingerprint": f"protected_files:{h}", "summary": h, "blocking": True} for h in hits]
    return GateResult("protected_files", "failed", len(changed_files), findings,
                      "protected files changed: " + ", ".join(hits) + ". Only the owner can confirm this, at the merge guard")
