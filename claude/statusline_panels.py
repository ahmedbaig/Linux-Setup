"""Side panels (WORK and SCOPE) for the Claude Code status line.

Two branded boxes to the right of the stats lines:

  WORK   repos this session is exploring (read/grep/bash) or looking after
         (edit/write), then the files worked on: names when the edits sit in one
         repo, per-repo numbers (on the repo rows) when they span several.
  SCOPE  balance needle (left = drifting off target, centre = on scope,
         right = hallucination risk), where the goal came from (chat turn or a
         maintained doc), reference docs (declared, auto-loaded, read), and what
         is in context right now (files/lines read since the last compaction).

Scope state lives in STATE_DIR/scope/<session_id>.json and is written by
~/.claude/hooks/scope-set. Objective signals from the transcript (not-found /
no-match tool errors, edits in repos outside the declared scope) raise the
needle even if the self-assessment says 0. Only Read/Edit/Write/NotebookEdit
count as file work; files changed through Bash (sed -i, redirects) are missed.
"""

import json
import os
import re
import struct
import subprocess

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.join(HOME, ".claude"))
SCOPE_DIR = os.path.join(CLAUDE_DIR, "statusline-stats", "scope")
STATE_VERSION = 4

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"


def rgb(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


def c(code):
    return f"\033[38;5;{code}m"


# accent palette: #00A960, #1B8342, #d6f5e7
ACCENT = rgb(0, 169, 96)
ACCENT_DARK = rgb(27, 131, 66)
ACCENT_LIGHT = rgb(214, 245, 231)
GREY, WHITE = c(245), c(255)
YELLOW, ORANGE, RED = c(221), c(208), c(203)

PANEL_MIN, PANEL_MAX = 40, 58
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
FILE_TOOLS = EDIT_TOOLS | {"Read"}
PATH_KEYS = ("file_path", "path", "notebook_path", "repo_root")
DOC_EXT = (".md", ".mdx", ".pdf", ".txt", ".rst", ".adoc", ".docx")
ABS_RE = re.compile(r"(?<![\w.])((?:~|" + re.escape(HOME) + r")/[^\s\"'`;|&<>()]*)")
CD_RE = re.compile(r"(?:\bcd|\bgit\s+-C)\s+([^\s;&|)]+)")
MISS_RE = re.compile(
    r"does not exist|No such file|String to replace not found|not found in file"
    r"|did not match any|InputValidationError|Unknown (?:skill|tool|agent)",
    re.I,
)
TAG_RE = re.compile(r"<([a-z-]+)>.*?</\1>", re.S)
# files written by Bash: redirects, tee, sed -i, cp/mv target, python open(..., "w")
BASH_WRITE_RES = [
    re.compile(r"(?:^|[^<>&\d])>>?\s*([^\s;&|<>()'\"]+)"),
    re.compile(r"\btee\s+(?:-a\s+)?([^\s;&|<>()]+)"),
    re.compile(r"\bsed\s+-i\b[^;&|\n]*?\s([^\s;&|'\"]+)(?=\s*(?:$|[;&|\n]))", re.M),
    re.compile(r"\b(?:cp|mv)\s+(?:-\w+\s+)*[^\s;&|]+\s+([^\s;&|]+)"),
    re.compile(r"open\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"'][wa]"),
]
PY_PATH_RE = re.compile(r"expanduser\(\s*[\"']([^\"']+)[\"']\s*\)")
PY_WRITE_RE = re.compile(r"open\([^)]*,\s*[\"'][wa]")
SKIP_PREFIXES = ("/private/tmp", "/tmp", "/var/folders")
ANSI_RE = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033\a]*(?:\033\\|\a)")
ANCHOR = "\u2800"


# ----------------------------------------------------------------------------
# transcript tracking (called from the incremental parser in statusline.py)
# ----------------------------------------------------------------------------
def ensure_state(st):
    """Reset the incremental parse when the tracked schema changes."""
    if st.get("v") != STATE_VERSION:
        st.clear()
        st["v"] = STATE_VERSION
    return st


def _repo_root(path, cache):
    path = os.path.expanduser(path)
    if not path.startswith(HOME) or path.startswith(SKIP_PREFIXES):
        return None
    d = path if os.path.isdir(path) else os.path.dirname(path)
    if d in cache:
        return cache[d]
    probe, root = d, None
    while probe and probe != HOME and probe != "/":
        if os.path.exists(os.path.join(probe, ".git")):
            root = probe
            break
        probe = os.path.dirname(probe)
    if root is None and (d + "/").startswith(os.path.join(CLAUDE_DIR, "")):
        root = CLAUDE_DIR  # config edits: show as ~/.claude
    if len(cache) > 3000:
        cache.clear()
    cache[d] = root
    return root


def _paths_from_tool(name, inp, cwd):
    paths = [inp[k] for k in PATH_KEYS if isinstance(inp.get(k), str)]
    cmd = inp.get("command") if name == "Bash" else None
    if isinstance(cmd, str):
        paths += ABS_RE.findall(cmd)
        for rel in CD_RE.findall(cmd):
            rel = rel.strip("\"'")
            paths.append(rel if rel.startswith(("/", "~")) else os.path.join(cwd or HOME, rel))
    if not paths and name in ("Grep", "Glob") and cwd:
        paths.append(cwd)
    return paths


def _bash_writes(cmd, cwd):
    found = [m for rx in BASH_WRITE_RES for m in rx.findall(cmd)]
    if PY_WRITE_RE.search(cmd):
        found += PY_PATH_RE.findall(cmd)
    out = set()
    for p in found:
        p = os.path.expanduser(p.strip("\"'"))
        if not p.startswith("/"):
            p = os.path.join(cwd or HOME, p)
        p = os.path.normpath(p)
        if p.startswith(HOME) and not p.startswith(SKIP_PREFIXES) and os.path.isfile(p):
            out.add(p)
    return out


def _file_entry(st, fpath, cache):
    return st.setdefault("files", {}).setdefault(
        fpath, {"e": 0, "r": 0, "new": False, "last": 0, "root": _repo_root(fpath, cache)}
    )


def _bump_repo(st, root, kind, ts):
    r = st.setdefault("repos", {}).setdefault(root, {"e": 0, "r": 0, "last": 0})
    r[kind] += 1
    r["last"] = ts


def track_tool_use(st, block, cwd, ts):
    """Record a tool_use block against the repos and files it touches."""
    seen = st.setdefault("seen_tools", [])
    tid = block.get("id")
    if tid in seen:
        return
    seen.append(tid)
    del seen[:-300]
    name = block.get("name") or ""
    inp = block.get("input") or {}
    kind = "e" if name in EDIT_TOOLS else "r"
    cache = st.setdefault("root_cache", {})
    pend = st.setdefault("pending", {})
    pend[tid] = [name, None, 0]  # result handler needs the tool name
    if len(pend) > 200:
        for k in list(pend)[:-100]:
            del pend[k]
    for root in {_repo_root(p, cache) for p in _paths_from_tool(name, inp, cwd)} - {None}:
        _bump_repo(st, root, kind, ts)

    if name == "Bash" and isinstance(inp.get("command"), str):
        for fpath in _bash_writes(inp["command"], cwd):
            f = _file_entry(st, fpath, cache)
            f["e"] += 1
            f["last"] = ts
            if f["root"]:
                st.setdefault("repos", {}).setdefault(f["root"], {"e": 0, "r": 0, "last": ts})["e"] += 1
        return

    fpath = inp.get("file_path") or inp.get("notebook_path")
    if name in FILE_TOOLS and isinstance(fpath, str):
        fpath = os.path.expanduser(fpath)
        if fpath.startswith(SKIP_PREFIXES):
            return
        f = _file_entry(st, fpath, cache)
        f[kind] += 1
        f["last"] = ts
        pend[tid] = [name, fpath, len(str(inp.get("content") or "").splitlines())]


def track_tool_result(st, block):
    content = block.get("content")
    if isinstance(content, list):
        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    else:
        text = str(content or "")
    err = bool(block.get("is_error"))
    pend = (st.get("pending") or {}).pop(block.get("tool_use_id"), None)
    name, fpath, write_lines = pend or ["", None, 0]
    # a failed shell probe (ls/test on an optional file) is exploration, not a
    # hallucination; count misses only where a path or string was asserted
    miss = err and name != "Bash" and bool(MISS_RE.search(text[:2000]))
    ring = st.setdefault("results", [])
    ring.append(1 if miss else 0)
    del ring[:-30]

    if not fpath or err:
        return
    ctx = st.setdefault("ctx", {})
    if name == "Read":
        ctx[fpath] = max(ctx.get(fpath, 0), text.count("\n") + (1 if text else 0))
    elif name == "Write":
        ctx[fpath] = write_lines
        if "created successfully" in text:
            st["files"][fpath]["new"] = True
    else:
        ctx.setdefault(fpath, 0)


def track_compact(st):
    ctx = st.get("ctx") or {}
    st["dropped"] = st.get("dropped", 0) + len(ctx)
    st["compactions"] = st.get("compactions", 0) + 1
    st["ctx"] = {}


def track_prompt(st, content):
    """Keep a short snippet of every real user prompt (turn number = index + 1)."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    text = " ".join(TAG_RE.sub("", str(content or "")).split())
    if not text:
        return False
    prompts = st.setdefault("prompts", [])
    prompts.append(text[:90])
    del prompts[:-300]
    return True


def track_cwd(st, cwd, ts):
    if cwd and cwd != st.get("last_cwd"):
        st["last_cwd"] = cwd
        root = _repo_root(cwd, st.setdefault("root_cache", {}))
        if root:
            _bump_repo(st, root, "r", ts)


# ----------------------------------------------------------------------------
# rendering helpers
# ----------------------------------------------------------------------------
def vis(s):
    return len(ANSI_RE.sub("", s))


def trunc(s, n):
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def short_path(p):
    return "~" + p[len(HOME):] if p.startswith(HOME) else p


def fmt_n(n):
    if n >= 100_000:
        return f"{n/1000:.0f}k"
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def _branch(root, st, now):
    bc = st.setdefault("branch_cache", {})
    hit = bc.get(root)
    if hit and now - hit[1] < 60:
        return hit[0]
    try:
        out = subprocess.run(
            ["git", "-C", root, "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True, text=True, timeout=0.5,
        ).stdout.strip()
    except Exception:
        out = ""
    bc[root] = [out, now]
    return out


def load_scope(sid):
    try:
        with open(os.path.join(SCOPE_DIR, f"{sid}.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def auto_refs(data):
    """Instruction files Claude Code loads on its own for this session."""
    ws = data.get("workspace") or {}
    proj = ws.get("project_dir") or data.get("cwd") or HOME
    cwd = ws.get("current_dir") or proj
    found = []
    cands = [os.path.join(CLAUDE_DIR, "CLAUDE.md")]
    d = cwd
    while d.startswith(HOME) and d != "/":
        cands += [os.path.join(d, "CLAUDE.md"), os.path.join(d, ".claude", "CLAUDE.md")]
        if d == HOME:
            break
        d = os.path.dirname(d)
    slug = re.sub(r"[^A-Za-z0-9]", "-", proj)
    cands.append(os.path.join(CLAUDE_DIR, "projects", slug, "memory", "MEMORY.md"))
    for p in cands:
        if os.path.isfile(p) and p not in found:
            found.append(p)
    return found


def _lvl_color(n):
    return ACCENT if n <= 0 else YELLOW if n <= 2 else ORANGE if n == 3 else RED


def scale_line(drift, halluc, cells=6):
    left = "".join(
        (_lvl_color(drift) + "█") if i >= cells - drift else (GREY + "░") for i in range(cells)
    )
    right = "".join((_lvl_color(halluc) + "█") if i < halluc else (GREY + "░") for i in range(cells))
    centre = _lvl_color(max(drift, halluc)) + BOLD + "●" + RESET
    return f"{GREY}off-target ◀{RESET}{left}{RESET}{centre}{right}{RESET}{GREY}▶ halluc{RESET}"


class Box:
    def __init__(self, w, title, tag=""):
        self.w, self.lines = w, []
        tag = f" {DIM}{tag}{RESET} " if tag else ""
        fill = w - vis(title) - vis(tag) - 2
        self.lines.append(f"{ACCENT_DARK}╭─{RESET}{title}{ACCENT_DARK}{'─' * fill}{RESET}{tag}{ACCENT_DARK}─╮{RESET}")

    def row(self, content, right=""):
        pad = self.w - vis(content) - vis(right) - 1
        self.lines.append(f"{ACCENT_DARK}│{RESET} {content}{' ' * max(0, pad)}{right}{ACCENT_DARK}│{RESET}")

    def kv(self, key, value):
        self.row(f"{GREY}{key:<5}{RESET} {value}")

    def div(self, label, right=""):
        right = f" {right} " if right else ""
        fill = self.w - len(label) - 3 - vis(right) - 1
        self.lines.append(
            f"{ACCENT_DARK}├─{RESET}{GREY} {label} {RESET}{ACCENT_DARK}{'─' * fill}{RESET}{DIM}{right}{RESET}{ACCENT_DARK}─┤{RESET}"
        )

    def done(self):
        self.lines.append(f"{ACCENT_DARK}╰{'─' * self.w}╯{RESET}")
        return self.lines


# ----------------------------------------------------------------------------
# panels
# ----------------------------------------------------------------------------
def work_panel(st, now, W):
    repos = st.get("repos") or {}
    files = st.get("files") or {}
    edited = {p: f for p, f in files.items() if f["e"]}
    edit_roots = {f["root"] for f in edited.values()}
    multi = len(edit_roots) > 1
    per_repo = {}
    for p, f in files.items():
        pr = per_repo.setdefault(f["root"], {"e": 0, "new": 0, "r": 0})
        pr["e" if f["e"] else "r"] += 1
        pr["new"] += f["new"]

    title = f" {ACCENT}{BOLD}◆{RESET} {ACCENT_LIGHT}{BOLD}C L A U D E{RESET} "
    b = Box(W, title, "work")
    ordered = sorted(repos.items(), key=lambda kv: (kv[1]["e"] > 0, kv[1]["last"]), reverse=True)
    b.row(f"{GREY}REPOS{RESET}", f"{DIM}{'files ✎ edited +new r read' if multi else '✎ edits  r reads'} {RESET}")
    for root, r in ordered[:4]:
        name = "~/.claude" if root == st.get("_claude_dir") else os.path.basename(root)
        mark = (ACCENT + "●") if r["e"] else (GREY + "○")
        if root in st.get("_offscope", ()):
            mark = ORANGE + "⚠"
        if multi:
            pr = per_repo.get(root, {"e": 0, "new": 0, "r": 0})
            counts = (f"✎{pr['e']} " if pr["e"] else "") + (f"+{pr['new']} " if pr["new"] else "") + f"r{pr['r']}"
        else:
            counts = (f"✎{r['e']} " if r["e"] else "") + f"r{r['r']}"
        br = "" if root == st.get("_claude_dir") else _branch(root, st, now)
        name_w = W - 3 - len(counts) - 1
        br_w = max(0, min(len(br), name_w - len(name) - 1, 18))
        left = f"{mark}{RESET} {WHITE if r['e'] else GREY}{trunc(name, name_w - (br_w + 1 if br_w else 0))}{RESET}"
        if br_w:
            left += f" {DIM}{trunc(br, br_w)}{RESET}"
        b.row(left, f"{DIM}{counts}{RESET} ")
    if len(ordered) > 4:
        b.row(f"{DIM}  +{len(ordered) - 4} more repos{RESET}")
    if not ordered:
        b.row(f"{DIM}  no repos touched yet{RESET}")

    n_new = sum(f["new"] for f in files.values())
    summary = f"✎{len(edited)}" + (f" +{n_new}" if n_new else "") + f" r{len(files) - len(edited)}"
    b.div("FILES", summary)
    if multi:
        b.row(f"{DIM}edits span {len(edit_roots)} repos: counts on repo rows ↑{RESET}")
        return b.done()
    ordered_f = sorted(files.items(), key=lambda kv: (kv[1]["e"] > 0, kv[1]["last"]), reverse=True)
    for p, f in ordered_f[:6]:
        mark = (ACCENT + "+") if f["new"] else (ACCENT + "✎") if f["e"] else (GREY + "r")
        rel = os.path.relpath(p, f["root"]) if f["root"] else short_path(p)
        cnt = f"{DIM}×{f['e'] or f['r']}{RESET} " if (f["e"] or f["r"]) > 1 else ""
        b.row(f"{mark}{RESET} {WHITE if f['e'] else GREY}{trunc(rel, W - 8)}{RESET}", cnt)
    if len(ordered_f) > 6:
        b.row(f"{DIM}  +{len(ordered_f) - 6} more files{RESET}")
    if not ordered_f:
        b.row(f"{DIM}  none yet{RESET}")
    return b.done()


def scope_levels(st, scope):
    """(drift, halluc, misses, offscope, coloured verdict word)."""
    misses = sum(st.get("results") or [])
    offscope = len(st.get("_offscope", ()))
    drift = max(int(scope.get("drift") or 0), min(3, offscope))
    halluc = max(int(scope.get("halluc") or 0), min(3, misses))
    if max(drift, halluc) == 0:
        verdict = f"{ACCENT}on scope{RESET}"
    elif drift >= halluc:
        verdict = f"{_lvl_color(drift)}drifting{RESET}"
    else:
        verdict = f"{_lvl_color(halluc)}verify claims{RESET}"
    return drift, halluc, misses, offscope, verdict


def scope_panel(st, data, scope, W):
    drift, halluc, misses, offscope, verdict = scope_levels(st, scope)
    prompts = st.get("prompts") or []

    b = Box(W, f" {ACCENT}{BOLD}◆{RESET} {ACCENT_LIGHT}{BOLD}SCOPE{RESET} ", f"turn {len(prompts)}")
    b.row(scale_line(drift, halluc))
    signals = [f"{misses} miss{'es' if misses > 1 else ''}"] if misses else []
    if offscope:
        signals.append(f"{offscope} off-scope repo{'s' if offscope > 1 else ''}")
    if scope.get("note"):
        signals.append(scope["note"])
    if signals:
        verdict += f" {DIM}({trunc(' · '.join(signals), W - vis(verdict) - 5)}){RESET}"
    b.row(verdict)

    # -- where the goal came from --------------------------------------------
    b.div("SOURCE", "pinned" if scope.get("goal") else "unpinned")
    vw = W - 7
    goal = scope.get("goal")
    b.kv("goal", f"{WHITE}{trunc(goal, vw)}{RESET}" if goal else f"{DIM}not pinned (scope-set --goal){RESET}")
    src = scope.get("source") or ""
    m = re.match(r"chat\s*#?(\d+)", src)
    if m and 0 < int(m.group(1)) <= len(prompts):
        n = int(m.group(1))
        b.kv("from", f"chat #{n} {DIM}“{trunc(prompts[n - 1], vw - len(str(n)) - 10)}”{RESET}")
    elif src:
        p = os.path.expanduser(src)
        label = f"doc {short_path(p)}" if os.path.exists(p) else src
        b.kv("from", trunc(label, vw))
    else:
        b.kv("from", f"{DIM}chat (no turn pinned){RESET}")
    if prompts:
        n = len(prompts)
        b.kv("now", f"#{n} {DIM}“{trunc(prompts[-1], vw - len(str(n)) - 5)}”{RESET}")

    # -- reference docs ------------------------------------------------------
    declared = [os.path.expanduser(r) for r in scope.get("refs") or []]
    auto = [p for p in auto_refs(data) if p not in declared]
    read_docs = [
        p for p, f in (st.get("files") or {}).items()
        if p.lower().endswith(DOC_EXT) and p not in declared and p not in auto
        and not f["e"]
    ]
    items = [f"{WHITE}{os.path.basename(p)}{RESET}" for p in declared]
    items += [f"{GREY}{os.path.basename(p)}{DIM}ᵃ{RESET}" for p in auto]
    items += [f"{GREY}{os.path.basename(p)}{DIM}ʳ{RESET}" for p in read_docs]
    lines, cur = [], ""
    for it in items:
        cand = f"{cur}{DIM} · {RESET}{it}" if cur else it
        if vis(cand) > vw:
            lines.append(cur)
            cur = it
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1] + f"{DIM} …{RESET}"
    for i, ln in enumerate(lines or [f"{DIM}none{RESET}"]):
        b.kv("refs" if i == 0 else "", ln)

    # -- context -------------------------------------------------------------
    ctx = st.get("ctx") or {}
    cw = data.get("context_window") or {}
    tok = cw.get("total_input_tokens") or 0
    pct = cw.get("used_percentage")
    b.div("IN CONTEXT", f"{fmt_n(tok)} tok" + (f" {pct:.0f}%" if pct is not None else ""))
    lines_in = sum(ctx.values())
    b.kv("files", f"{WHITE}{len(ctx)}{RESET} loaded · {WHITE}{fmt_n(lines_in)}{RESET} lines read")
    if ctx:
        big = max(ctx.items(), key=lambda kv: kv[1])
        b.kv("big", f"{DIM}{trunc(os.path.basename(big[0]), vw - 12)} {fmt_n(big[1])} lines{RESET}")
    comp = st.get("compactions", 0)
    if comp:
        b.kv("lost", f"{ORANGE}{st.get('dropped', 0)} files{RESET} {DIM}dropped by {comp} compaction{'s' if comp > 1 else ''} (re-read if needed){RESET}")
    else:
        b.kv("lost", f"{DIM}nothing, no compaction yet{RESET}")
    return b.done()


def _mark_offscope(st, scope):
    in_scope = set(scope.get("repos") or [])
    st["_claude_dir"] = CLAUDE_DIR
    st["_offscope"] = [
        root for root, r in (st.get("repos") or {}).items()
        if in_scope and r["e"] and os.path.basename(root) not in in_scope and root != CLAUDE_DIR
    ]


def _unmark(st):
    for k in ("_claude_dir", "_offscope"):
        st.pop(k, None)


def render_panels(st, data, sid, now, left_width, hidden=()):
    scope = load_scope(sid)
    _mark_offscope(st, scope)
    builders = [("work", lambda W: work_panel(st, now, W)), ("scope", lambda W: scope_panel(st, data, scope, W))]
    builders = [(n, fn) for n, fn in builders if n not in hidden]
    cols = tty_cols()
    need = len(builders) * (PANEL_MIN + 2) + 2 * (len(builders) - 1)
    avail = (cols - left_width - 3 - 4) if cols else 2 * PANEL_MAX + 6
    below = bool(cols) and avail < need
    if below:  # no room beside the stats: put the panels underneath
        avail = cols - 2
    side = avail >= need
    per = (avail - 2 * (len(builders) - 1)) // max(1, len(builders)) - 2 if side else avail - 2
    W = max(PANEL_MIN, min(PANEL_MAX, per))
    panels = [fn(W) for _, fn in builders]
    _unmark(st)
    return panels, cols, side, below


# ----------------------------------------------------------------------------
# show / hide  (state flipped by ~/.claude/hooks/panel-toggle, or by clicking the
# ccpanel:// links below; ~/Applications/CCPanelToggle.app handles the scheme)
# ----------------------------------------------------------------------------
VIEW_PATH = os.path.join(CLAUDE_DIR, "statusline-stats", "view.json")
SECTIONS = ("stats", "work", "scope")
# Clicks never reach the handler in Claude Code's fullscreen TUI, so links are
# off by default; the toggle is bound to Ctrl-Option-X in iTerm2 (Run Coprocess).
LINKS = os.environ.get("CC_PANEL_LINKS", "0") == "1"
TOGGLE_KEY = os.environ.get("CC_PANEL_KEY", "⌃⌥X")


def load_view():
    try:
        with open(VIEW_PATH) as f:
            v = json.load(f)
    except Exception:
        v = {}
    return bool(v.get("expanded", True)), set(v.get("hidden") or [])


def link(text, url):
    """OSC 8 hyperlink (Cmd+click in iTerm2); plain text when CC_PANEL_LINKS=0."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\" if LINKS else text


def button(label):
    return f"{ACCENT_DARK}[{RESET}{ACCENT}{BOLD}{label}{RESET}{ACCENT_DARK}]{RESET}"


def toggle_bar(hidden):
    """Last line of the expanded view: hide button + per-section switches."""
    parts = [link(button(f"▼ {TOGGLE_KEY} hide"), "ccpanel://hide")]
    for name in SECTIONS:
        on = name not in hidden
        dot = f"{ACCENT}●{RESET}" if on else f"{GREY}○{RESET}"
        parts.append(link(f"{dot} {WHITE if on else DIM}{name}{RESET}", f"ccpanel://section/{name}"))
    return f"{ACCENT}{BOLD}◆{RESET} " + "  ".join(parts)


def collapsed_line(st, sid, summary):
    """One-line view: show button, brand, then caller-supplied metric snippets."""
    scope = load_scope(sid)
    _mark_offscope(st, scope)
    drift, halluc, _, _, verdict = scope_levels(st, scope)
    _unmark(st)
    files = st.get("files") or {}
    edited = sum(1 for f in files.values() if f["e"])
    bits = list(summary)
    bits.append(f"{_lvl_color(max(drift, halluc))}●{RESET} {verdict}")
    bits.append(f"{GREY}files{RESET} ✎{edited} r{len(files) - edited}")
    bits.append(f"{GREY}ctx{RESET} {len(st.get('ctx') or {})} files")
    sep = f" {DIM}│{RESET} "
    head = f"{ACCENT}{BOLD}◆{RESET} {ACCENT_LIGHT}{BOLD}CLAUDE{RESET} " + link(button(f"▲ {TOGGLE_KEY} show"), "ccpanel://show")
    return head + sep + sep.join(bits)


def tty_cols():
    env = os.environ.get("CC_STATUS_COLS")
    if env and env.isdigit():
        return int(env)
    import fcntl
    import termios

    def size(dev):
        fd = os.open(dev, os.O_RDONLY | os.O_NOCTTY)
        try:
            return struct.unpack("hhhh", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))[1]
        finally:
            os.close(fd)

    candidates = ["/dev/tty"]
    # the status line command has no controlling tty; borrow Claude Code's
    try:
        for pid in filter(None, [os.environ.get("CLAUDE_PID"), str(os.getppid())]):
            tty = subprocess.run(["ps", "-o", "tty=", "-p", pid], capture_output=True,
                                 text=True, timeout=0.5).stdout.strip()
            if tty and tty not in ("??", "-"):
                candidates.append("/dev/" + tty)
    except Exception:
        pass
    for dev in candidates:
        try:
            cols = size(dev)
            if cols:
                return cols
        except Exception:
            continue
    return None


def _hjoin(blocks, gap=2):
    n = max(len(b) for b in blocks)
    widths = [max(vis(l) for l in b) for b in blocks]
    out = []
    for i in range(n):
        parts = [(b[i] if i < len(b) else "") for b in blocks]
        out.append((" " * gap).join(p + " " * (w - vis(p)) for p, w in zip(parts, widths)).rstrip())
    return out


def merge(left_text, panels, cols, side, below):
    """Place panels right of the left lines, or under them when there is no room;
    side by side when wide enough, else stacked."""
    left = left_text.split("\n")
    lw = max((vis(l) for l in left), default=0)
    block = _hjoin(panels) if side else [l for p in panels for l in p]
    bw = max(vis(l) for l in block)
    if below:
        return left_text + "\n" + "\n".join(block)
    col = lw + 3
    if cols:
        col = max(col, cols - bw - 4)
    n = max(len(left), len(block))
    left += [""] * (n - len(left))
    block += [""] * (n - len(block))
    # Claude Code trims leading whitespace per line; an empty left side would
    # collapse the padding, so anchor it with a braille blank (not whitespace).
    return "\n".join(
        ((l or ANCHOR) + " " * (col - max(vis(l), 1)) + bx) if bx else l for l, bx in zip(left, block)
    )
