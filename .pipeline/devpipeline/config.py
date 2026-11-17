"""pipeline.yml loading and bundled-data lookup."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_COMMANDS = ("build", "test", "e2e", "lint")
WORKERS_CEILING = 6
WHOLE_KEYS = ("max_test_workers", "max_piece_copies")
RESOURCE_DEFAULTS = {"max_test_workers": 4, "min_free_ram_gb": 4, "min_free_disk_gb": 10,
                    "max_piece_copies": 3}


class ConfigError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class PipelineConfig:
    stack: str
    commands: dict[str, str]
    app_paths: list[str]
    repo_root: Path
    journeys_dir: Path
    standards_file: Path
    baseline_file: Path
    results_dir: Path
    e2e_dir: str = "e2e"
    app_dir: str = "."
    protected_paths: list[str] = field(default_factory=list)
    max_test_workers: int = RESOURCE_DEFAULTS["max_test_workers"]
    min_free_ram_gb: float = RESOURCE_DEFAULTS["min_free_ram_gb"]
    min_free_disk_gb: float = RESOURCE_DEFAULTS["min_free_disk_gb"]
    max_piece_copies: int = RESOURCE_DEFAULTS["max_piece_copies"]


def _load_app_dir(path: Path, data: dict) -> str:
    raw = data.get("app_dir")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "."
    fix = "use a relative folder inside the repo such as frontend, or remove app_dir"
    if not isinstance(raw, str):
        raise ConfigError(f"{path} app_dir must be a folder name, not {raw!r}; {fix}")
    value = raw.strip()
    if not value.isprintable() or any(c in value for c in "\\*?[]{}"):
        raise ConfigError(f"{path} app_dir {raw!r} has odd characters; {fix}")
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise ConfigError(f"{path} app_dir {raw!r} is an absolute path; {fix}")
    parts = [p for p in value.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ConfigError(f"{path} app_dir {raw!r} contains ..; {fix}")
    return "/".join(parts) or "."


def app_root(cfg: PipelineConfig) -> Path:
    """The folder that holds the web app: repo_root, or repo_root/app_dir."""
    return cfg.repo_root if cfg.app_dir == "." else cfg.repo_root / cfg.app_dir


def package_dir() -> Path:
    """Folder holding catalogue/ and templates/, found by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "catalogue").is_dir():
            return parent
    raise ConfigError(f"bundled catalogue folder not found above {here}; reinstall or run `devpipeline sync`")


def _load_resources(path: Path, data: dict) -> dict:
    res = data.get("resources")
    if res is None:
        return dict(RESOURCE_DEFAULTS)
    if not isinstance(res, dict):
        raise ConfigError(f"{path} resources must be a mapping with {', '.join(RESOURCE_DEFAULTS)}; fix it or remove it")
    unknown = sorted(str(k) for k in res if k not in RESOURCE_DEFAULTS)
    if unknown:
        raise ConfigError(f"{path} resources has unknown key {unknown[0]}; the keys are {', '.join(RESOURCE_DEFAULTS)}")
    out = dict(RESOURCE_DEFAULTS)
    for key, value in res.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{path} resources.{key} must be a number, not {value!r}; fix it")
        if key in WHOLE_KEYS:
            if value != int(value) or not 1 <= value <= WORKERS_CEILING:
                raise ConfigError(f"{path} resources.{key} is {value}; it must be a whole number from 1 to {WORKERS_CEILING}")
            value = int(value)
        elif value < 0:
            raise ConfigError(f"{path} resources.{key} is {value}; it cannot be negative")
        out[key] = value
    return out


def load_config(repo_root: Path, trusted: Path | None = None) -> PipelineConfig:
    """Load pipeline.yml. With `trusted`, the config, baseline and standards list come from that folder
    (a copy taken from the base branch), so a PR cannot change what it is judged against."""
    repo_root = Path(repo_root)
    base = Path(trusted) if trusted else repo_root
    path = base / "pipeline.yml"
    if not path.is_file():
        if trusted:
            raise ConfigError(f"{path} not found; the base branch has no pipeline.yml, so the first adoption must be committed by the owner directly")
        raise ConfigError(f"{path} not found; pass --repo PATH pointing at a project that has pipeline.yml")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML ({str(e).splitlines()[0]}); fix it or pass --repo PATH") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a YAML mapping; fix it or pass --repo PATH")
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise ConfigError(f"{path} is missing commands; add commands.build, commands.test, commands.e2e, commands.lint")
    for key in REQUIRED_COMMANDS:
        if not commands.get(key):
            raise ConfigError(f"{path} is missing commands.{key}; add it or pass --repo PATH for another project")
    if not data.get("stack"):
        raise ConfigError(f"{path} is missing stack; add `stack: web`")
    app_paths = data.get("app_paths")
    if not isinstance(app_paths, list):
        raise ConfigError(f"{path} is missing app_paths; add a list of globs such as ['src/**']")
    resources = _load_resources(path, data)
    return PipelineConfig(
        stack=str(data["stack"]),
        commands={k: str(v) for k, v in commands.items()},
        app_paths=[str(p) for p in app_paths],
        repo_root=repo_root,
        journeys_dir=repo_root / data.get("journeys_dir", "docs/journeys"),
        standards_file=base / data.get("standards_file", "docs/standards.yml"),
        baseline_file=base / data.get("baseline_file", ".pipeline-baseline.json"),
        results_dir=repo_root / data.get("results_dir", "results"),
        e2e_dir=str(data.get("e2e_dir", "e2e")).strip("/"),
        app_dir=_load_app_dir(path, data),
        protected_paths=[str(p) for p in data.get("protected_paths") or []],
        **resources,
    )
