"""Standards catalogue, suggestions from the project profile, and line item resolution."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from .config import ConfigError
from .results import GateResult

CHECK_TYPES = ("tool", "test", "review")
REVIEW_MAX_AGE_DAYS = 180


def today() -> date:
    """The one place that reads the clock, so tests can fix it."""
    return date.today()


@dataclass
class LineItem:
    id: str
    standard: str
    text: str
    check_type: str
    ref: str | None = None


@dataclass
class ItemStatus:
    item: LineItem
    status: str  # passed | failed | not_covered | not_applicable
    evidence: str
    expired: bool = False  # a review record that ran out; counts as not_covered but not toward rule 5


def load_catalogue(dir: Path) -> dict[str, list[LineItem]]:
    out: dict[str, list[LineItem]] = {}
    for path in sorted(Path(dir).glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text())
            sid = data["id"]
            items = []
            for it in data["items"]:
                check = it["check"]
                if check["type"] not in CHECK_TYPES:
                    raise ValueError(f"unknown check type {check['type']!r} on {it['id']}")
                if check["type"] != "review" and not check.get("ref"):
                    raise ValueError(f"item {it['id']} needs check.ref")
                items.append(LineItem(id=it["id"], standard=sid, text=str(it["text"]),
                                      check_type=check["type"], ref=check.get("ref")))
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as e:
            raise ConfigError(f"{path} is not a valid catalogue file ({type(e).__name__}: {e}); fix the file or run `devpipeline sync`") from e
        out[sid] = items
    return out


# profile and suggestions
def parse_profile(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"{path} not found; create it from the template (docs/project-profile.md) or pass --repo PATH")
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        raise ConfigError(f"{path} must start with YAML front matter between --- lines holding the profile booleans")
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} front matter is not valid YAML; fix it") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} front matter must be a mapping of profile booleans")
    return data


def suggest_standards(profile: dict) -> list[tuple[str, str]]:
    p = lambda k: bool(profile.get(k))
    out = [("baseline", "every project"), ("owasp-top-ten-2021", "every project")]
    if p("web_app") or p("api"):
        out.append(("asvs-5.0-l2", "web app or API"))
    if p("api"):
        out.append(("owasp-api-top10-2023", "has an API"))
    if p("mobile_app"):
        out.append(("masvs", "mobile app"))
    if p("personal_data"):
        out.append(("ug-dppa-2019", "holds personal data"))
        if p("eu_users"):
            out.append(("gdpr", "holds personal data of EU users"))
    if p("health_data"):
        out.append(("client-health-rules", "holds health data"))
        if p("exchanges_health_records"):
            out.append(("hl7-fhir", "exchanges health records"))
    if p("card_payments"):
        out.append(("pci-dss-4", "takes card payments"))
    if p("public_screens"):
        out.append(("wcag-2.2-aa", "has public-facing screens"))
    return out


def load_standards_file(path: Path) -> tuple[list[tuple[str, str]], dict[str, dict]]:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"{path} not found; run `devpipeline standards suggest` and save its output there")
    try:
        data = yaml.safe_load(path.read_text()) or {}
        chosen = [(s["id"], str(s.get("reason", ""))) for s in data["standards"]]
        overrides = data.get("overrides") or {}
    except (KeyError, TypeError, yaml.YAMLError) as e:
        raise ConfigError(f"{path} must hold `standards: [{{id, reason}}]` and optional `overrides`; fix it") from e
    return chosen, overrides


def _read_yaml_mapping(path: Path, what: str) -> dict:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"{path} is not valid YAML ({type(e).__name__}); fix the {what}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a mapping; fix the {what}")
    return data


def load_not_applicable(path: Path) -> dict[str, str]:
    """The optional `not_applicable` map of docs/standards.yml. Every reason must be non-empty text."""
    raw = _read_yaml_mapping(path, "standards file").get("not_applicable")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: not_applicable must map an item id or chapter to a reason")
    out = {}
    for key, reason in raw.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(f"{path}: not_applicable key {key!r} needs a non-empty reason")
        out[str(key)] = reason.strip()
    return out


def load_reviews(path: Path) -> list[dict]:
    """docs/standards-review.yml. A missing file means no reviews. Each entry gets a real date."""
    path = Path(path)
    if not path.is_file():
        return []
    raw = _read_yaml_mapping(path, "review file").get("reviews")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: reviews must be a list of entries with id, date, by and note")
    out = []
    for i, e in enumerate(raw, 1):
        name = f"{path} review entry {i}" + (f" ({e['id']})" if isinstance(e, dict) and e.get("id") else "")
        if not isinstance(e, dict):
            raise ConfigError(f"{name} must be a mapping with id, date, by and note")
        for field in ("id", "date", "by", "note"):
            if e.get(field) is None or not str(e[field]).strip():
                raise ConfigError(f"{name} is missing {field}")
        d = e["date"]
        if not isinstance(d, date):
            try:
                d = date.fromisoformat(str(d).strip())
            except ValueError:
                raise ConfigError(f"{name} has a bad date {e['date']!r}; use YYYY-MM-DD") from None
        if d > today():
            raise ConfigError(f"{name} is dated in the future ({d})")
        out.append({"id": str(e["id"]).strip(), "date": d, "by": str(e["by"]).strip(), "note": str(e["note"]).strip()})
    return out


def key_matches(key: str, item_id: str) -> bool:
    """An id key matches itself. A chapter key matches whole id segments: ASVS-V6 matches ASVS-V6.1.1, never ASVS-V60.1."""
    return item_id == key or item_id.startswith(key + ".")


def _matching(key: str, items: list[LineItem], source: str, what: str) -> list[LineItem]:
    """Review items a key covers. An unknown key, or an exact id of a tool or test item, is a config error.
    A chapter key skips tool and test items: a gate proves those, so they keep their gate status."""
    hits = [i for i in items if key_matches(key, i.id)]
    if not hits:
        raise ConfigError(f"{source}: {what} {key!r} matches no item in the chosen standards")
    reviewable = [i for i in hits if i.check_type == "review"]
    if not reviewable:
        raise ConfigError(f"{source}: {what} {key!r} matches only {hits[0].check_type} items; a gate proves those, so they cannot be marked here")
    exact = next((i for i in hits if i.id == key), None)
    if exact and exact.check_type != "review":
        raise ConfigError(f"{source}: {what} {key!r} is a {exact.check_type} item; a gate proves it, so it cannot be marked here")
    return reviewable


# resolution
def _checklist_ticks(pr_body: str) -> set[str]:
    ticked, inside = set(), False
    for line in pr_body.splitlines():
        if re.match(r"^##\s+Review checklist\s*$", line.strip()):
            inside = True
            continue
        if inside and re.match(r"^#{1,6}\s", line.strip()):
            inside = False
        if inside:
            m = re.match(r"^\s*[-*]\s*\[[xX]\]\s+(\S+)\s*$", line.rstrip())
            if m:
                ticked.add(m.group(1))
    return ticked


def _test_cases_from(results: dict[str, GateResult], ref: str) -> list[dict]:
    cases = []
    for gate in ("tests", "e2e"):
        for f in results.get(gate, GateResult(gate, "error")).findings:
            file = f.get("file", "")
            if file and (ref == file or ref.endswith("/" + file)):
                cases.append(f)
    return cases


def _effective(item: LineItem, overrides: dict[str, dict]) -> LineItem:
    ov = overrides.get(item.id)
    if not ov:
        return item
    return LineItem(item.id, item.standard, item.text, ov.get("type", item.check_type), ov.get("ref", item.ref))


def _effective_items(chosen: list[str], overrides: dict[str, dict], catalogue: dict[str, list[LineItem]]) -> list[LineItem]:
    return [_effective(raw, overrides) for sid in chosen for raw in catalogue.get(sid, [])]


def resolve_items(chosen: list[str], overrides: dict[str, dict], catalogue: dict[str, list[LineItem]],
                  results: dict[str, GateResult], pr_body: str, repo_root: Path,
                  not_applicable: dict[str, str] | None = None, reviews: list[dict] | None = None) -> list[ItemStatus]:
    ticks = _checklist_ticks(pr_body)
    items = _effective_items(chosen, overrides, catalogue)
    na: dict[str, str] = {}
    for key, reason in (not_applicable or {}).items():
        for it in _matching(key, items, "not_applicable", "key"):
            na.setdefault(it.id, reason)
    reviewed: dict[str, dict] = {}
    for e in reviews or []:
        for it in _matching(e["id"], items, "docs/standards-review.yml", "id"):
            if it.id not in reviewed or e["date"] > reviewed[it.id]["date"]:
                reviewed[it.id] = e
    now = today()
    out: list[ItemStatus] = []
    for sid in chosen:
        if sid not in catalogue:
            out.append(ItemStatus(LineItem(f"{sid}-UNMAPPED", sid, f"{sid} has no catalogue file yet", "review"),
                                  "not_covered", "no catalogue file for this standard"))
            continue
        for raw in catalogue[sid]:
            it = _effective(raw, overrides)
            if it.id in na and it.check_type == "review":
                out.append(ItemStatus(it, "not_applicable", na[it.id]))
            elif it.check_type == "tool":
                res = results.get(it.ref or "")
                if res is None:
                    out.append(ItemStatus(it, "failed", "gate did not run"))
                elif res.status == "passed":
                    out.append(ItemStatus(it, "passed", f"gate {it.ref} passed"))
                else:
                    out.append(ItemStatus(it, "failed", f"gate {it.ref} {res.status}"))
            elif it.check_type == "test":
                ref = it.ref or ""
                if not ref or not (Path(repo_root) / ref).is_file():
                    out.append(ItemStatus(it, "failed", f"test file {ref} does not exist"))
                    continue
                cases = _test_cases_from(results, ref)
                if any(not c.get("passed") and not c.get("skipped") for c in cases):
                    out.append(ItemStatus(it, "failed", f"a test from {ref} failed"))
                elif any(c.get("passed") for c in cases):
                    out.append(ItemStatus(it, "passed", f"{sum(1 for c in cases if c.get('passed'))} test(s) from {ref} passed"))
                else:
                    out.append(ItemStatus(it, "failed", f"no passing test from {ref} in the test results"))
            else:
                if it.id in ticks:
                    out.append(ItemStatus(it, "passed", "ticked in the PR review checklist"))
                elif it.id in reviewed:
                    e = reviewed[it.id]
                    if now - e["date"] > timedelta(days=REVIEW_MAX_AGE_DAYS):
                        out.append(ItemStatus(it, "not_covered", f"review expired {e['date']}", expired=True))
                    else:
                        out.append(ItemStatus(it, "passed", f"reviewed {e['date']} by {e['by']}: {e['note']}"))
                else:
                    out.append(ItemStatus(it, "not_covered", "not ticked in the PR review checklist"))
    return out


# rendering
def render_markdown(chosen_with_reasons: list[tuple[str, str]], statuses: list[ItemStatus] | None = None,
                    catalogue: dict[str, list[LineItem]] | None = None,
                    overrides: dict[str, dict] | None = None, not_applicable: dict[str, str] | None = None) -> str:
    """Markdown for people. Without statuses it is the static mapping of items to checks,
    so it only changes when the standards file, the catalogue or the overrides change."""
    lines = ["# Standards", "",
             "Generated by `devpipeline standards render` from `docs/standards.yml`. Do not edit by hand.", ""]
    by_std: dict[str, list[ItemStatus]] = {}
    for s in statuses or []:
        by_std.setdefault(s.item.standard, []).append(s)
    for sid, reason in chosen_with_reasons:
        lines += [f"## {sid}", "", f"Why: {reason}", ""]
        na_keys = {k: r for k, r in (not_applicable or {}).items()
                   if sid in (catalogue or {}) and any(key_matches(k, i.id) and _effective(i, overrides or {}).check_type == "review"
                                                       for i in catalogue[sid])}
        if na_keys:
            lines += ["Not applicable:", ""] + [f"- {k}: {r}" for k, r in na_keys.items()] + [""]
        if statuses is not None:
            rows = by_std.get(sid, [])
            lines += ["| Item | Status | Evidence |", "|---|---|---|"]
            lines += [f"| {r.item.id} | {r.status} | {r.evidence} |" for r in rows]
        elif catalogue is not None and sid in catalogue:
            lines += ["| Item | Check | Text |", "|---|---|---|"]
            for raw in catalogue[sid]:
                it = _effective(raw, overrides or {})
                check = it.check_type + (f": {it.ref}" if it.ref else "")
                for k, r in (not_applicable or {}).items():
                    if it.check_type == "review" and key_matches(k, it.id):
                        check = f"not applicable: {r.replace('|', '/')}"
                        break
                lines.append(f"| {it.id} | {check} | {it.text.replace('|', '/')} |")
        elif catalogue is not None:
            lines.append(f"No catalogue file yet. Reported as {sid}-UNMAPPED (not_covered).")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def load_items(path: Path) -> list[ItemStatus] | None:
    """Read results/standards_items.json written by `devpipeline resolve`. None when missing."""
    import json
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return [ItemStatus(LineItem(d["id"], d["standard"], d["text"], d["check_type"], d.get("ref")),
                           d["status"], d.get("evidence", ""), bool(d.get("expired"))) for d in json.loads(path.read_text())]
    except (ValueError, KeyError, TypeError) as e:
        raise ConfigError(f"{path} is not valid ({type(e).__name__}); run `devpipeline resolve` again") from e
