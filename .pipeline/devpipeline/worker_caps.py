"""Gate test_workers: every test runner the project uses must have a worker count, at most the cap.

It reads files only and never runs project code. Values are read with plain regex, so an expression
such as `process.env.CI ? 2 : undefined` is judged by the literal numbers in it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import PipelineConfig
from .results import GateResult

JS_EXT = ("ts", "js", "mjs", "cjs", "mts", "cts")
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w.])")
MAX_FLAG = re.compile(r"--max-?[wW]orkers[= ]\s*([^\s;&|]+)")
JEST_W_FLAG = re.compile(r"(?:(?<=\s)|^)-w(?:[= ]\s*|\s+)([^\s;&|]+)")
WORKERS_FLAG = re.compile(r"--workers[= ]\s*([^\s;&|]+)")
PYTEST_N = re.compile(r"(?:(?<=[\s\"',\[])|^)(?:-n\s*=?\s*|--numprocesses[= ]\s*)([A-Za-z0-9]+)")


def _read(path: Path) -> str:
    return path.read_text(errors="replace")


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", text)


def _expression(text: str, start: int) -> str:
    """Text from `start` up to the comma or closing bracket that ends the value."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return text[start:i]
            depth -= 1
        elif c == "," and depth == 0:
            return text[start:i]
    return text[start:]


def _js_values(text: str, keys: tuple[str, ...]) -> list[str]:
    text = _strip_js_comments(text)
    out = []
    for m in re.finditer(r"\b(?:%s)\b[\"']?\s*:\s*" % "|".join(keys), text):
        out.append(" ".join(_expression(text, m.end()).split()))
    return out


def judge(value: str, cap: int) -> tuple[bool, str]:
    """(ok, reason when not ok). Every literal number must be within the cap; undefined and auto fail."""
    v = value.strip().strip("\"'")
    low = v.lower()
    if re.search(r"\bundefined\b|\bnull\b", low) or re.search(r"\bauto\b|\blogical\b", low):
        return False, "may be unset or auto"
    nums = NUM.findall(v)
    if not nums:
        return False, "is not a number"
    for n in nums:
        if n.endswith("%"):
            return False, f"{n} depends on the core count"
        if float(n) > cap:
            return False, f"{n} is above the cap {cap}"
    return True, ""


def _files(repo: Path, stem: str) -> list[Path]:
    return [repo / f"{stem}.{e}" for e in JS_EXT if (repo / f"{stem}.{e}").is_file()]


def _script_text(repo: Path, commands: dict[str, str]) -> str:
    """The test and e2e commands, with `npm run NAME` / `npm test` replaced by the package.json script text."""
    parts = [commands.get("test", ""), commands.get("e2e", "")]
    try:
        scripts = json.loads(_read(repo / "package.json")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        scripts = {}
    for cmd in list(parts):
        for m in re.finditer(r"\bnpm\s+(?:run(?:-script)?\s+)?([\w:.-]+)", cmd):
            if isinstance(scripts.get(m.group(1)), str):
                parts.append(scripts[m.group(1)])
    return "\n".join(parts)


def _judge_all(label: str, key: str, values: list[str], cap: int, results: list, fails: list, runner: str) -> None:
    if not values:
        msg = f"{label}: {key} not set; set it to at most {cap}"
        results.append(msg)
        fails.append((runner, msg))
        return
    for v in values:
        ok, why = judge(v, cap)
        msg = f"{label}: {key} {v}" + ("" if ok else f" ({why}; the cap is {cap})")
        results.append(msg)
        if not ok:
            fails.append((runner, msg))


def check_test_workers(repo_root: Path, cfg: PipelineConfig) -> GateResult:
    repo, cap = Path(repo_root) / cfg.app_dir, cfg.max_test_workers
    cmds = _script_text(repo, cfg.commands)
    notes: list[str] = []
    fails: list[tuple[str, str]] = []
    judged = 0
    try:
        # Playwright: unset means half the cores.
        pw = _files(repo, "playwright.config")
        if pw or re.search(r"\bplaywright\b", cmds):
            judged += 1
            vals, label = [], "playwright.config"
            for f in pw:
                label = f.name
                vals += _js_values(_read(f), ("workers",))
            vals += WORKERS_FLAG.findall(cmds)
            _judge_all(label, "workers", vals, cap, notes, fails, "playwright")

        # Vitest
        vt = _files(repo, "vitest.config")
        if vt or re.search(r"\bvitest\b", cmds):
            judged += 1
            vals, label = [], "vitest.config"
            for f in vt + _files(repo, "vite.config"):
                found = _js_values(_read(f), ("maxWorkers", "maxThreads", "maxForks"))
                if found or f in vt:
                    label = f.name
                vals += found
            if re.search(r"\bvitest\b", cmds):
                vals += MAX_FLAG.findall(cmds)
            _judge_all(label, "maxWorkers", vals, cap, notes, fails, "vitest")

        # Jest
        jc = _files(repo, "jest.config")
        pj_jest = None
        try:
            pj_data = json.loads(_read(repo / "package.json"))
            pj_jest = pj_data.get("jest") if isinstance(pj_data, dict) else None
        except (OSError, ValueError):
            pass
        if jc or isinstance(pj_jest, dict) or re.search(r"\bjest\b", cmds):
            judged += 1
            vals, label = [], "jest.config"
            for f in jc:
                label = f.name
                vals += _js_values(_read(f), ("maxWorkers",))
            if isinstance(pj_jest, dict) and "maxWorkers" in pj_jest:
                label = "package.json jest"
                vals.append(str(pj_jest["maxWorkers"]))
            if re.search(r"\bjest\b", cmds):
                vals += MAX_FLAG.findall(cmds) + JEST_W_FLAG.findall(cmds)
            _judge_all(label, "maxWorkers", vals, cap, notes, fails, "jest")

        # pytest with xdist: no -n passes, -n auto fails.
        py_texts = [("test command", cmds)]
        for name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
            f = repo / name
            if f.is_file():
                text = _read(f)
                for m in re.finditer(r"\baddopts\s*=\s*", text):
                    py_texts.append((name, re.sub(r"[\"',\[\]]", " ", text[m.end():m.end() + 300])))
        found = [(label, m.group(1)) for label, t in py_texts for m in PYTEST_N.finditer(t)]
        if found:
            judged += 1
            for label, v in found:
                ok, why = judge(v, cap) if v != "0" else (True, "")
                msg = f"{label}: pytest -n {v}" + ("" if ok else f" ({why}; the cap is {cap})")
                notes.append(msg)
                if not ok:
                    fails.append(("pytest", msg))
    except OSError as e:
        return GateResult("test_workers", "error", 0, [], f"could not read {e.filename}: {e.strerror}")

    if not judged:
        return GateResult("test_workers", "passed", 0, [], "no test runner found to judge")
    findings = [{"fingerprint": f"test_workers:{r}", "summary": m, "blocking": True} for r, m in fails]
    message = "; ".join(notes)
    if fails:
        return GateResult("test_workers", "failed", judged, findings, message + ". The cap is resources.max_test_workers in pipeline.yml")
    return GateResult("test_workers", "passed", judged, [], message)
