"""`devpipeline merge <pr>`: refuse to merge a red, pending or unapproved PR.

It runs from the installed template on the owner's machine, so it is the trusted side. It only stops
people and agents who use it. It cannot tell a person at a keyboard from a program that opens its own
terminal (for example with `script`): that is a known limit until GitHub branch protection is available.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Callable

from .journey_change import matches_any
from .protected import PROTECTED_PATTERNS, protected_patterns

PROMPT = "You are approving this PR. Type the PR number to merge: "
CONFIRM_PROTECTED = "This PR changes protected files (listed above). Type the PR number again to confirm: "
GATES_CHECK = "gates"
PROTECTED_CHECK = "protected-files"
# The guard is stricter than CI here: any change to package.json asks for the second confirmation.
GUARD_PATTERNS = PROTECTED_PATTERNS + ["package.json"]


def guard_patterns(app_dir: str = ".") -> list[str]:
    extra = [] if app_dir in (".", "") else [f"{app_dir}/package.json"]
    return protected_patterns(app_dir) + ["package.json"] + extra
OK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
PENDING = {"", "PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "EXPECTED", "REQUESTED"}


def _refuse(msg: str) -> int:
    print(f"refused: {msg}", file=sys.stderr)
    return 1


def _gh_failed(what: str, p: subprocess.CompletedProcess) -> int:
    excerpt = " ".join((p.stderr or "").split())[:300]
    print(f"gh {what} failed (exit {p.returncode}): {excerpt}", file=sys.stderr)
    return 1


def check_state(c: dict) -> tuple[str, str, str]:
    """(name, state, conclusion) where state is ok, pending or bad."""
    name = c.get("name") or c.get("context") or "(unnamed check)"
    concl = (c.get("conclusion") or c.get("state") or "").upper()
    status = (c.get("status") or "").upper()
    if concl in OK_CONCLUSIONS and status in ("", "COMPLETED"):
        return name, "ok", concl
    if concl in PENDING or status in PENDING - {""}:
        return name, "pending", concl
    return name, "bad", concl


def latest_runs(checks: list[dict]) -> list[dict]:
    """Keep only the newest run of each check. A PR edit or a re-run adds a second run of the same
    check to the same commit, and GitHub cancels the older one. GitHub judges the newest run, so the
    guard does too. Runs are grouped by workflow and check name, so a check of the same name from
    another workflow still counts. If a run in a group has no start time, the whole group is kept."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in checks:
        key = (c.get("workflowName") or "", c.get("name") or c.get("context") or "")
        groups.setdefault(key, []).append(c)
    out: list[dict] = []
    for runs in groups.values():
        if len(runs) > 1 and all(r.get("startedAt") for r in runs):
            out.append(max(runs, key=lambda r: r["startedAt"]))
        else:
            out.extend(runs)
    return out


_check_state = check_state
_latest_runs = latest_runs


def merge_pr(pr: int, run: Callable[[list[str]], subprocess.CompletedProcess], is_tty: bool,
             read_line: Callable[[str], str], app_dir: str = ".") -> int:
    view = run(["gh", "pr", "view", str(pr), "--json", "statusCheckRollup,labels,isDraft,state,headRefOid,headRefName"])
    if view.returncode != 0:
        return _gh_failed(f"pr view {pr}", view)
    try:
        info = json.loads(view.stdout)
        checks = info["statusCheckRollup"] or []
        state, draft, head = info["state"], info["isDraft"], info["headRefOid"]
        branch = info.get("headRefName") or ""
        if not head:
            raise ValueError("no head sha")
    except (ValueError, KeyError, TypeError):
        return _refuse(f"could not read the PR {pr} data from gh; update gh or check the PR number")
    if state != "OPEN":
        return _refuse(f"PR {pr} is {state}, not open")
    if draft:
        return _refuse(f"PR {pr} is a draft")

    states = [check_state(c) for c in latest_runs(checks)]
    protected_red = False
    for name, s, _ in states:
        if s == "bad":
            if name == PROTECTED_CHECK:
                protected_red = True
                continue
            return _refuse(f"check {name} did not succeed")
    for name, s, _ in states:
        if s == "pending":
            return _refuse(f"check {name} is still pending")
    if not any(n == GATES_CHECK and s == "ok" and concl == "SUCCESS" for n, s, concl in states):
        return _refuse(f"the check named {GATES_CHECK} is missing, skipped or not green")

    if not is_tty:
        return _refuse("only a person at a terminal can merge: this is not a terminal")

    diff = run(["gh", "pr", "diff", str(pr), "--name-only"])
    if diff.returncode != 0:
        return _gh_failed(f"pr diff {pr}", diff)
    files = [l for l in diff.stdout.splitlines() if l.strip()]
    if not files:
        return _refuse(f"gh returned no changed files for PR {pr}, so the protected file check could not run")
    protected = sorted(f for f in files if matches_any(f, guard_patterns(app_dir)))
    if protected_red and not protected:
        return _refuse(f"the {PROTECTED_CHECK} check is red but this guard sees no protected path; look at the report")

    if protected:
        print("Protected files changed in this PR:")
        for f in protected:
            print(f"  {f}")
    if read_line(PROMPT).strip() != str(pr):
        return _refuse(f"the typed number did not match PR {pr}")
    if protected and read_line(CONFIRM_PROTECTED).strip() != str(pr):
        return _refuse(f"the protected files confirmation did not match PR {pr}")

    # A piece branch is checked out in its piece copy, so git can not delete it locally and gh stops
    # half way. For those, merge without --delete-branch, delete the GitHub branch here, and leave the
    # local branch and the copy to `devpipeline piece clean`.
    piece = branch.startswith("piece/")
    cmd = ["gh", "pr", "merge", str(pr), "--squash", "--match-head-commit", head]
    if not piece:
        cmd.insert(5, "--delete-branch")
    done = run(cmd)
    if done.returncode != 0:
        return _gh_failed(f"pr merge {pr}", done)
    print(f"merged PR {pr} at {head[:7]}")
    if piece:
        gone = run(["gh", "api", "-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/heads/{branch}"])
        if gone.returncode != 0:
            excerpt = " ".join((gone.stderr or "").split())[:300]
            print(f"the PR is merged, but the GitHub branch {branch} was not deleted: {excerpt}", file=sys.stderr)
        print("Run `devpipeline piece clean` to remove the piece copy.")
    return 0
