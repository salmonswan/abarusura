"""Decides whether an omp agent's tool call may run. Returns None to allow, or the reason to refuse."""
from __future__ import annotations

import posixpath
import re
import shlex

SAFE_TOOLS = frozenset("read grep glob find lsp ast_grep todo task ask web_search fetch plan goal out recap archive wait".split())
UNREADABLE = "could not read this command; simplify it"
MAX_DEPTH = 6
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
WRAPPERS = {"sudo", "env", "nohup", "time", "command", "exec", "xargs", "setsid", "nice", "timeout",
            "npx", "stdbuf", "watch", "ionice", "doas", "busybox"}
# Two-word wrappers: (program, first word) -> options that take a value.
WRAPPER_PAIRS = {("npm", "exec"): {"-w", "--workspace"}, ("pnpm", "exec"): set(), ("uv", "run"): {"--with", "-p", "--python"},
                 ("conda", "run"): {"-n", "--name", "-p", "--prefix"}}
RESERVED = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "fi", "done"}
# Programs whose every non-option word is a path they change.
WRITERS = {"tee", "cp", "mv", "rm", "rmdir", "ln", "touch", "truncate", "install", "chmod"}
# Options of a wrapper that take a separate value word.
WRAPPER_VALUE_OPTS = {"sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-U"}, "env": {"-u", "-C", "-S"},
                      "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E"}, "nice": {"-n"},
                      "timeout": {"-s", "-k", "--signal", "--kill-after"}, "exec": {"-a"}, "stdbuf": {"-i", "-o", "-e"},
                      "ionice": {"-c", "-n", "-p"}, "watch": {"-n", "-d"}}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def _match_paren(s: str, i: int) -> int:
    depth = 1
    while i < len(s):
        depth += {"(": 1, ")": -1}.get(s[i], 0)
        if depth == 0:
            return i
        i += 1
    return len(s)


HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z0-9_]+)\2")


def _skip_heredocs(s: str, i: int, pending: list) -> tuple[int, list[tuple[int, str]]]:
    """Skip the body lines of every pending heredoc. Returns the index after the last end line
    and (segment index, body text) for each heredoc."""
    bodies = []
    for word, strip, seg in pending:
        body = []
        while i < len(s):
            j = s.find("\n", i)
            j = len(s) if j < 0 else j
            line = s[i:j]
            i = min(j + 1, len(s))
            if (line.lstrip("\t") if strip else line) == word:
                break
            body.append(line)
        bodies.append((seg, "\n".join(body)))
    pending.clear()
    return i, bodies


def _scan(cmd: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Split into simple commands and the bodies of $(...) and backticks. Quotes are respected."""
    segs, subs, cur, q, i, n = [], [], [], None, 0, len(cmd)
    pending: list[tuple[str, bool, int]] = []
    heredocs: dict[int, list[str]] = {}
    while i < n:
        c = cmd[i]
        if c == "\n" and pending and q is None:
            segs.append("".join(cur))
            cur = []
            i, bodies = _skip_heredocs(cmd, i + 1, pending)
            for seg, body in bodies:
                heredocs.setdefault(seg, []).append(body)
            continue
        if q is None and c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = HEREDOC.match(cmd, i)
            if m:
                pending.append((m.group(3), bool(m.group(1)), len(segs)))
                cur.append(" x ")
                i = m.end()
                continue
        if q is None and c == "#" and (not cur or cur[-1][-1:].isspace()):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        if q == "'":
            cur.append(c)
            q = None if c == "'" else q
        elif c == "\\" and i + 1 < n:
            cur.append(cmd[i:i + 2])
            i += 1
        elif cmd.startswith("$(", i):
            end = _match_paren(cmd, i + 2)
            subs.append(cmd[i + 2:end])
            cur.append("x")
            i = end
        elif c == "`":
            end = cmd.find("`", i + 1)
            end = n if end < 0 else end
            subs.append(cmd[i + 1:end])
            cur.append("x")
            i = end
        elif q == '"':
            cur.append(c)
            q = None if c == '"' else q
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c in ";&|\n()":
            segs.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    segs.append("".join(cur))
    return [(t, heredocs.get(k, [])) for k, t in enumerate(segs) if t.strip()], subs


def check_command(cmd: str, depth: int = 0) -> str | None:
    if depth > MAX_DEPTH:
        return "command is nested too deeply; simplify it"
    segs, subs = _scan(cmd)
    for text in subs:
        why = check_command(text, depth + 1)
        if why:
            return why
    for seg, bodies in segs:
        try:
            words = shlex.split(seg)
        except ValueError:
            return UNREADABLE
        why = _check_words(words, depth, bodies)
        if why:
            return why
    return None


def _skip_options(words: list[str], value_opts: set[str]) -> list[str]:
    i = 0
    while i < len(words) and words[i].startswith("-") and words[i] != "--":
        i += 2 if words[i] in value_opts else 1
    return words[i + 1:] if i < len(words) and words[i] == "--" else words[i:]


def _positional(words: list[str], value_opts: set[str]) -> list[str]:
    """Words that are not options, skipping the value of options that take one."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if w in value_opts:
            i += 1
        elif not w.startswith("-"):
            out.append(w)
        i += 1
    return out


def _redirect_reason(words: list[str]) -> str | None:
    for i, w in enumerate(words):
        if ">" in w:
            target = w.rsplit(">", 1)[1].lstrip("|")
            if not target and i + 1 < len(words):
                target = words[i + 1]
            why = check_path(target) if target else None
            if why:
                return why
    return None


def _check_words(words: list[str], depth: int, heredocs: list[str] = ()) -> str | None:
    why = _redirect_reason(words)
    if why:
        return why
    while True:
        while words and (ASSIGN.match(words[0]) or words[0] in RESERVED):
            m = ASSIGN.match(words[0])
            if m and m.group(1) == "CI":
                return "setting CI is not allowed; the pipeline decides how tests run"
            words = words[1:]
        if not words:
            return None
        prog = posixpath.basename(words[0])
        rest = words[1:]
        if prog in WRAPPERS:
            rest = _skip_options(rest, WRAPPER_VALUE_OPTS.get(prog, set()))
            if prog == "timeout" and rest:
                rest = rest[1:]
            words = rest
            continue
        if len(rest) and (prog, rest[0]) in WRAPPER_PAIRS:
            words = _skip_options(rest[1:], WRAPPER_PAIRS[(prog, rest[0])])
            continue
        break
    if prog == "eval":
        return check_command(" ".join(rest), depth + 1)
    if prog in SHELLS:
        for i, w in enumerate(rest):
            if w.startswith("-") and not w.startswith("--") and w.endswith("c"):
                j = i + 2 if rest[i + 1:i + 2] == ["--"] else i + 1
                return check_command(rest[j], depth + 1) if j < len(rest) else None
            if not w.startswith("-"):
                break
        # A shell reading a heredoc runs its body. Other commands only read it as text.
        for body in heredocs:
            why = check_command(body, depth + 1)
            if why:
                return why
        return None
    if prog.startswith("python") and "-m" in rest and rest.index("-m") + 1 < len(rest) and rest[rest.index("-m") + 1] == "devpipeline":
        prog, rest = "devpipeline", rest[rest.index("-m") + 2:]
    if prog in ("script", "expect", "unbuffer"):
        return f"{prog} makes a fake terminal and is not allowed"
    if prog in ("export", "declare", "typeset", "readonly"):
        if any(w == "CI" or w.startswith("CI=") for w in rest):
            return "setting CI is not allowed; the pipeline decides how tests run"
    if prog in WRITERS or (prog in ("sed", "perl") and any(re.match(r"-[A-Za-z]*i", w) or w == "--in-place" for w in rest)):
        for w in rest:
            why = check_path(w)
            if why:
                return why
    pos = _positional(rest, {"-R", "--repo", "-C", "-c", "--git-dir", "--work-tree"})
    if prog == "gh":
        if pos[:2] == ["pr", "merge"]:
            return "merging is done by the owner with devpipeline merge, not by the agent"
        if pos[:2] == ["pr", "create"]:
            return "open a PR with devpipeline piece pr, not gh pr create"
        if pos[:1] == ["api"] and any(w.split("?")[0].rstrip("/").endswith("/merge") or "mergePullRequest" in w for w in rest):
            return "merging is done by the owner with devpipeline merge, not by the agent"
    if prog == "git" and pos[:1] == ["push"]:
        return "do not run git push; devpipeline piece pr pushes for you"
    if prog == "git" and pos[:1] in (["rm"], ["mv"], ["checkout"], ["restore"]):
        for w in pos[1:]:
            why = check_path(w)
            if why:
                return why
    if prog == "devpipeline" and pos[:1] == ["merge"]:
        return "merging is done by the owner, not by the agent"
    return None


def check_path(path: str) -> str | None:
    norm = posixpath.normpath(path.replace("\\", "/"))
    if norm == "docs/standards-review.yml" or norm.endswith("/docs/standards-review.yml"):
        return f"{path} is a review record only the owner may write"
    if ".omp" in norm.split("/"):
        return f"{path} is pipeline configuration; the agent may not change .omp/"
    return None


def check_call(tool: str, payload: dict) -> str | None:
    if tool in SAFE_TOOLS:
        return None
    if tool == "bash":
        cmd = payload.get("command")
        return check_command(cmd) if isinstance(cmd, str) else "bash call has no command text"
    if tool in ("write", "edit"):
        paths = [payload[k] for k in ("path", "file_path") if k in payload]
        if not paths or not all(isinstance(p, str) and p for p in paths):
            return f"{tool} call has no file path"
        return next((why for why in map(check_path, paths) if why), None)
    return f"tool {tool} is off in the pipeline loop"
