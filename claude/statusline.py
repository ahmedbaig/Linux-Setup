#!/usr/bin/env python3
"""Claude Code status line: caveman badge + usage stats with bar graphs.

Reads the statusLine JSON from stdin (see https://code.claude.com/docs/en/statusline),
parses the session transcript incrementally for per-model token split and message
counts, records rate-limit samples over time to predict when the 5h / 7d limits
will run out, and renders three lines of ANSI-coloured bars.

Tunables (env vars):
  CC_STATS_COST_BUDGET   USD the session cost bar is scaled against (default 25)
  CC_STATS_BAR_WIDTH     bar width in cells (default 10)
  CC_STATS_WINDOW_MIN    minutes used for "recent" burn / cost rates (default 10)
  CC_STATS_LAYOUT        wide (one stat per line, default) | compact (3 dense lines)
  CC_STATS_LINES         compact layout only: number of lines to render, 1-3 (default 3)
"""

import datetime as dt
import json
import os
import subprocess
import sys
import time

import statusline_panels as panel

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.join(HOME, ".claude"))
STATE_DIR = os.path.join(CLAUDE_DIR, "statusline-stats")
CAVEMAN_SCRIPT = os.path.join(
    CLAUDE_DIR,
    "plugins/cache/caveman/caveman/655b7d9c5431/src/hooks/caveman-statusline.sh",
)

COST_BUDGET = float(os.environ.get("CC_STATS_COST_BUDGET", "25"))
BAR_W = int(os.environ.get("CC_STATS_BAR_WIDTH", "10"))
WINDOW_S = float(os.environ.get("CC_STATS_WINDOW_MIN", "10")) * 60
LINES = int(os.environ.get("CC_STATS_LINES", "3"))
LAYOUT = os.environ.get("CC_STATS_LAYOUT", "wide")  # wide | compact

FULL, EMPTY = "█", "░"
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"


def c(code):
    return f"\033[38;5;{code}m"


GREY, WHITE, ORANGE = c(245), c(255), c(172)
PALETTE = [c(75), c(141), c(114), c(215), c(203), c(81)]  # model segments


# ----------------------------------------------------------------------------
# formatting helpers
# ----------------------------------------------------------------------------
def pct_color(p):
    if p is None:
        return GREY
    if p < 50:
        return c(114)  # green
    if p < 80:
        return c(221)  # yellow
    return c(203)  # red


def P(p):
    """Right-aligned coloured percent."""
    return f"{pct_color(p)}{(p or 0):>3.0f}%{RESET}"


def bar(pct, width=BAR_W, color=None):
    if pct is None:
        return GREY + EMPTY * width + RESET
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(pct / 100 * width))
    if pct > 0 and filled == 0:
        filled = 1
    color = color or pct_color(pct)
    return color + FULL * filled + GREY + EMPTY * (width - filled) + RESET


def seg_bar(parts, width=BAR_W):
    """parts: list of (fraction, color). Renders one bar of coloured segments."""
    total = sum(f for f, _ in parts) or 1.0
    cells, out = [], ""
    for f, col in parts:
        cells.append(int(round(f / total * width)))
    # fix rounding so segments sum to width
    diff = width - sum(cells)
    if cells:
        cells[0] += diff
    for n, (_, col) in zip(cells, parts):
        out += col + FULL * max(0, n)
    return out + RESET


def _trim(v):
    """Strip trailing zeros only after a decimal point ("1.00"->"1", "30"->"30")."""
    return v.rstrip("0").rstrip(".") if "." in v else v


def fmt_tok(n):
    n = float(n or 0)
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        v = f"{n/1e6:.2f}" if n < 10e6 else f"{n/1e6:.1f}"
        return _trim(v) + "M"
    if n >= 1e3:
        v = f"{n/1e3:.1f}" if n < 10e3 else f"{n/1e3:.0f}"
        return _trim(v) + "k"
    return f"{n:.0f}"


def fmt_dur(seconds):
    s = int(max(0, seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_clock(epoch, now):
    if not epoch:
        return "?"
    t = dt.datetime.fromtimestamp(epoch)
    n = dt.datetime.fromtimestamp(now)
    if t.date() == n.date():
        return t.strftime("%H:%M")
    if (t - n).total_seconds() < 6 * 86400:
        return t.strftime("%a %H:%M")
    return t.strftime("%d %b %H:%M")


def fmt_usd(x):
    x = float(x or 0)
    if x >= 100 or x == int(x):
        return f"${x:.0f}"
    return f"${x:.2f}"


def short_model(mid):
    if not mid:
        return "?"
    parts = mid.replace("claude-", "").split("-")
    name = parts[0]
    ver = ".".join(p for p in parts[1:3] if p.isdigit())
    return f"{name}{ver}" if ver else name


def parse_iso(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


# ----------------------------------------------------------------------------
# state
# ----------------------------------------------------------------------------
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# transcript: incremental parse
# ----------------------------------------------------------------------------
def update_transcript_stats(path, state):
    """Parse only bytes appended since last run. Dedup streamed assistant lines
    (same message.id repeated per content block) by skipping adjacent repeats."""
    defaults = {
            "offset": 0,
            "last_id": None,
            "models": {},
            "user_msgs": 0,
            "asst_msgs": 0,
            "msgs": [],  # [ts, tokens] ring for recent burn rate
            "first_ts": None,
            "last_ts": None,
    }
    st = panel.ensure_state(state.setdefault("tx", {}))
    for k, v in defaults.items():
        st.setdefault(k, v)
    if not path or not os.path.isfile(path):
        return st
    try:
        size = os.path.getsize(path)
    except OSError:
        return st
    if size < st["offset"]:  # truncated / rotated
        st.clear()
        panel.ensure_state(st)
        st.update(defaults)
    if size == st["offset"]:
        return st

    with open(path, "rb") as f:
        f.seek(st["offset"])
        chunk = f.read()
    end = chunk.rfind(b"\n")
    if end < 0:
        return st
    complete, st["offset"] = chunk[: end + 1], st["offset"] + end + 1

    for raw in complete.split(b"\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        typ = rec.get("type")
        rts = parse_iso(rec.get("timestamp") or "") or time.time()
        panel.track_cwd(st, rec.get("cwd"), rts)
        content = (rec.get("message") or {}).get("content")
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        if typ == "system" and rec.get("subtype") == "compact_boundary":
            panel.track_compact(st)
            continue
        if typ == "user":
            if rec.get("isMeta") or rec.get("isCompactSummary"):
                continue
            results = [b for b in blocks if b.get("type") == "tool_result"]
            for b in results:
                panel.track_tool_result(st, b)
            if results:
                continue
            st["user_msgs"] += 1
            panel.track_prompt(st, content)
        elif typ == "assistant":
            for b in blocks:
                if b.get("type") == "tool_use":
                    panel.track_tool_use(st, b, rec.get("cwd"), rts)
            msg = rec.get("message") or {}
            mid = msg.get("id")
            if mid and mid == st["last_id"]:
                continue
            st["last_id"] = mid
            model = msg.get("model") or "?"
            if model.startswith("<"):
                continue
            u = msg.get("usage") or {}
            inp = u.get("input_tokens", 0) or 0
            out = u.get("output_tokens", 0) or 0
            cw = u.get("cache_creation_input_tokens", 0) or 0
            cr = u.get("cache_read_input_tokens", 0) or 0
            m = st["models"].setdefault(model, {"in": 0, "out": 0, "cw": 0, "cr": 0, "n": 0})
            m["in"] += inp
            m["out"] += out
            m["cw"] += cw
            m["cr"] += cr
            m["n"] += 1
            st["asst_msgs"] += 1
            ts = parse_iso(rec.get("timestamp") or "") or time.time()
            st["first_ts"] = st["first_ts"] or ts
            st["last_ts"] = ts
            st["msgs"].append([ts, inp + out + cw + cr, out])
            if len(st["msgs"]) > 400:
                st["msgs"] = st["msgs"][-400:]
    return st


# ----------------------------------------------------------------------------
# rate-limit history + prediction
# ----------------------------------------------------------------------------
def record_rate_limits(rl, now):
    path = os.path.join(STATE_DIR, "ratelimits.jsonl")
    hist = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    hist.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    sample = {"t": now}
    for key in ("five_hour", "seven_day", "spend_limit"):
        w = rl.get(key) or {}
        if "used_percentage" in w:
            sample[key] = [float(w.get("used_percentage") or 0), w.get("resets_at")]
    # Usage is monotonic within a window; several open sessions share this file
    # and idle ones report stale (lower) values. Drop any window whose sample is
    # below the best already recorded for the same resets_at.
    for key in ("five_hour", "seven_day", "spend_limit"):
        if key not in sample:
            continue
        best = max(
            (h[key][0] for h in hist if key in h and h[key][1] == sample[key][1]),
            default=-1,
        )
        if sample[key][0] < best:
            del sample[key]
    last = hist[-1] if hist else None
    changed = last is None or any(sample.get(k) != last.get(k) for k in ("five_hour", "seven_day", "spend_limit"))
    if changed or (last and now - last["t"] >= 60):
        hist.append(sample)
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            if len(hist) > 4000:
                hist = hist[-2000:]
                with open(path, "w") as f:
                    f.writelines(json.dumps(h) + "\n" for h in hist)
            else:
                with open(path, "a") as f:
                    f.write(json.dumps(sample) + "\n")
        except Exception:
            pass
    return hist


def predict_exhaust(hist, key, used, resets_at, now, lookback=3 * 3600):
    """Linear projection of used% within the current window. Returns
    (eta_epoch or None, pct_per_hour or None, note)."""
    pts = [
        (h["t"], h[key][0])
        for h in hist
        if key in h and h[key][1] == resets_at and now - h["t"] <= lookback
    ]
    if len(pts) < 2:
        return None, None, "…"
    t0, u0 = pts[0]
    t1, u1 = now, used
    dt_s = t1 - t0
    if dt_s < 120:
        return None, None, "…"
    rate = (u1 - u0) / dt_s  # % per second
    if rate <= 0:
        return None, 0.0, "idle"
    eta = now + (100 - used) / rate
    if resets_at and eta >= resets_at:
        return None, rate * 3600, "safe"
    return eta, rate * 3600, "out"


# ----------------------------------------------------------------------------
# main render
# ----------------------------------------------------------------------------
def caveman_badge():
    try:
        r = subprocess.run(["bash", CAVEMAN_SCRIPT], capture_output=True, text=True, timeout=1)
        return r.stdout.strip()
    except Exception:
        return ""


def render(data):
    now = time.time()
    sid = data.get("session_id") or "unknown"
    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, f"session-{sid}.json")
    state = load_json(state_path, {})

    cost = data.get("cost") or {}
    ctx = data.get("context_window") or {}
    rl = data.get("rate_limits") or {}
    pc = data.get("prompt_cache") or {}
    model = data.get("model") or {}

    total_cost = float(cost.get("total_cost_usd") or 0)
    dur_s = float(cost.get("total_duration_ms") or 0) / 1000
    api_s = float(cost.get("total_api_duration_ms") or 0) / 1000

    # cost samples for recent $/h
    cs = state.setdefault("cost_samples", [])
    if not cs or now - cs[-1][0] >= 15:
        cs.append([now, total_cost])
        if len(cs) > 400:
            del cs[:-400]

    tx = update_transcript_stats(data.get("transcript_path"), state)
    hist = record_rate_limits(rl, now)
    save_json(state_path, state)

    # ---- tokens ------------------------------------------------------------
    models = tx["models"]
    tot_in = sum(m["in"] + m["cw"] + m["cr"] for m in models.values())
    tot_out = sum(m["out"] for m in models.values())
    tot_all = tot_in + tot_out

    # recent burn rate (tokens/min) over WINDOW_S; fall back to session average
    recent = [m for m in tx["msgs"] if now - m[0] <= WINDOW_S]
    if len(recent) >= 2:
        span = max(recent[-1][0] - recent[0][0], 60)
        burn = sum(m[1] for m in recent) / span * 60
        burn_out = sum(m[2] for m in recent) / span * 60
    elif tot_all and dur_s > 0:
        burn = tot_all / dur_s * 60
        burn_out = tot_out / dur_s * 60
    else:
        burn = burn_out = 0.0

    # recent cost rate ($/h) over WINDOW_S; fall back to session average
    rc = [s for s in cs if now - s[0] <= WINDOW_S]
    if len(rc) >= 2 and rc[-1][0] - rc[0][0] >= 60:
        cost_rate = (rc[-1][1] - rc[0][1]) / (rc[-1][0] - rc[0][0]) * 3600
    elif dur_s > 60:
        cost_rate = total_cost / dur_s * 3600
    else:
        cost_rate = 0.0

    # ---- context window ------------------------------------------------------
    ctx_used = ctx.get("total_input_tokens") or 0
    ctx_size = ctx.get("context_window_size") or 0
    ctx_pct = ctx.get("used_percentage")
    if ctx_pct is None and ctx_size:
        ctx_pct = ctx_used / ctx_size * 100

    # ---- shared pieces -----------------------------------------------------
    badge = caveman_badge()
    mname = model.get("display_name") or short_model(model.get("id"))
    cost_pct = total_cost / COST_BUDGET * 100 if COST_BUDGET > 0 else None
    um, am = tx["user_msgs"], tx["asst_msgs"]
    budget_eta = None
    if cost_rate > 0 and COST_BUDGET > total_cost:
        budget_eta = now + (COST_BUDGET - total_cost) / cost_rate * 3600

    limits = []  # (label, used%, resets_at, eta, rate_h, note)
    for key, label in (("five_hour", "5-hour limit"), ("seven_day", "7-day limit"), ("spend_limit", "Spend limit")):
        w = rl.get(key)
        if not w:
            continue
        used = float(w.get("used_percentage") or 0)
        resets = w.get("resets_at")
        # stale sessions under-report; trust the best sample seen for this window
        used = max([used] + [h[key][0] for h in hist if key in h and h[key][1] == resets])
        eta, rate_h, note = predict_exhaust(hist, key, used, resets, now)
        limits.append((label, used, resets, eta, rate_h, note))

    model_parts, model_legend = [], []
    if models:
        ordered = sorted(models.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["cw"] + kv[1]["cr"] + kv[1]["out"]))
        for i, (mid, m) in enumerate(ordered):
            t = m["in"] + m["cw"] + m["cr"] + m["out"]
            col = PALETTE[i % len(PALETTE)]
            model_parts.append((t, col))
            share = f" {t/tot_all*100:.0f}%" if tot_all else ""
            model_legend.append(f"{col}{short_model(mid)}{share}{RESET}")

    hit = float(pc["hit_ratio"]) * 100 if pc.get("hit_ratio") is not None else None

    def side(left):
        expanded, hidden = panel.load_view()
        if not expanded:
            summary = [badge] if badge else []
            summary.append(f"{GREY}ctx{RESET} {bar(ctx_pct, 5)} {P(ctx_pct)}")
            summary.append(f"{WHITE}{fmt_usd(total_cost)}{RESET}")
            short = {"5-hour limit": "5h", "7-day limit": "7d", "Spend limit": "$lim"}
            if limits:
                summary.append(" ".join(f"{GREY}{short.get(l[0], l[0])}{RESET} {P(l[1])}" for l in limits))
            return panel.collapsed_line(tx, sid, summary)
        if "stats" in hidden:
            left = ""
        lw = max(panel.vis(l) for l in left.split("\n"))
        panels, cols, beside, below = panel.render_panels(tx, data, sid, now, lw, hidden)
        save_json(state_path, state)  # branch cache
        body = panel.merge(left, panels, cols, beside, below) if panels else left
        return (body + "\n" if body.strip() else "") + panel.toggle_bar(hidden)

    if LAYOUT == "compact":
        return side(render_compact(
            badge, mname, ctx_pct, ctx_used, ctx_size, cost_pct, total_cost, um, am, dur_s,
            limits, hit, burn, burn_out, tot_all, tot_in, tot_out, cost_rate, budget_eta,
            model_parts, model_legend, now,
        ))

    # ---- wide layout: one stat per line, aligned label column ---------------
    dot = f" {DIM}·{RESET} "
    L = lambda t: f"{GREY}{t:<12}{RESET} "  # label column

    lines = []
    head = f"{BOLD}{WHITE}{mname}{RESET}{dot}session {fmt_dur(dur_s)}"
    lines.append((badge + "  " if badge else "") + head)

    lines.append(
        L("Context") + f"{bar(ctx_pct)} {P(ctx_pct)}  {fmt_tok(ctx_used)} of {fmt_tok(ctx_size)} tokens"
    )

    cost_line = L("Cost") + f"{bar(cost_pct)} {P(cost_pct)}  {WHITE}{fmt_usd(total_cost)}{RESET} of {fmt_usd(COST_BUDGET)} budget"
    if cost_rate > 0:
        cost_line += dot + f"{fmt_usd(cost_rate)}/hr"
    if budget_eta:
        cost_line += dot + f"budget hit ~{fmt_clock(budget_eta, now)}"
    lines.append(cost_line)

    tok_line = L("Tokens") + f"{WHITE}{fmt_tok(tot_all)}{RESET} total"
    tok_line += f"  {DIM}({fmt_tok(tot_in)} in, {fmt_tok(tot_out)} out){RESET}"
    tok_line += dot + f"burn {WHITE}{fmt_tok(burn)}{RESET}/min"
    lines.append(tok_line)

    if um + am:
        lines.append(
            L("Messages") + f"{seg_bar([(um, c(75)), (am, c(141))])}  "
            f"{c(75)}{um} you{RESET} / {c(141)}{am} claude{RESET}"
        )

    for label, used, resets, eta, rate_h, note in limits:
        line = L(label) + f"{bar(used)} {P(used)}"
        if resets:
            line += f"  resets in {fmt_dur(resets - now)} ({fmt_clock(resets, now)})"
        if note == "out" and eta:
            line += dot + f"{c(203)}runs out in {fmt_dur(eta - now)} ({fmt_clock(eta, now)}){RESET}"
        elif note == "safe":
            line += dot + f"{c(114)}safe, resets first{RESET}"
        elif note == "idle":
            line += dot + f"{DIM}idle{RESET}"
        if rate_h:
            line += f" {DIM}at {rate_h:.1f}%/hr{RESET}"
        lines.append(line)
    if not limits:
        lines.append(L("Limits") + f"{DIM}not reported yet{RESET}")

    if model_parts:
        mline = L("Models") + f"{seg_bar(model_parts)}  " + "  ".join(model_legend)
        if hit is not None:
            mline += dot + f"cache hit {hit:.0f}%"
        lines.append(mline)

    return side("\n".join(lines))


def render_compact(badge, mname, ctx_pct, ctx_used, ctx_size, cost_pct, total_cost, um, am, dur_s,
                   limits, hit, burn, burn_out, tot_all, tot_in, tot_out, cost_rate, budget_eta,
                   model_parts, model_legend, now):
    l1 = [badge] if badge else []
    l1.append(f"{BOLD}{WHITE}{mname}{RESET}")
    l1.append(f"{GREY}ctx{RESET} {bar(ctx_pct)} {pct_color(ctx_pct)}{(ctx_pct or 0):.0f}%{RESET} {DIM}{fmt_tok(ctx_used)}/{fmt_tok(ctx_size)}{RESET}")
    l1.append(f"{GREY}cost{RESET} {bar(cost_pct)} {WHITE}{fmt_usd(total_cost)}{RESET}{DIM}/{fmt_usd(COST_BUDGET)}{RESET}")
    if um + am:
        l1.append(f"{GREY}msgs{RESET} {seg_bar([(um, c(75)), (am, c(141))], 6)} {c(75)}{um}u{RESET}{DIM}/{RESET}{c(141)}{am}a{RESET}")
    l1.append(f"{GREY}⏱{RESET} {fmt_dur(dur_s)}")

    l2 = []
    short = {"5-hour limit": "5h", "7-day limit": "7d", "Spend limit": "$lim"}
    for label, used, resets, eta, rate_h, note in limits:
        seg = f"{GREY}{short.get(label, label)}{RESET} {bar(used)} {pct_color(used)}{used:.0f}%{RESET}"
        if resets:
            seg += f" {DIM}↻{fmt_dur(resets - now)} @{fmt_clock(resets, now)}{RESET}"
        if note == "out" and eta:
            seg += f" {c(203)}⚠ out {fmt_dur(eta - now)} @{fmt_clock(eta, now)}{RESET}"
        elif note == "safe":
            seg += f" {c(114)}✓safe{RESET}"
        elif note == "idle":
            seg += f" {DIM}idle{RESET}"
        if rate_h:
            seg += f" {DIM}{rate_h:.1f}%/h{RESET}"
        l2.append(seg)
    if not l2:
        l2.append(f"{DIM}rate limits n/a{RESET}")
    if hit is not None:
        l2.append(f"{GREY}cache{RESET} {bar(hit, 5, pct_color(100 - hit))} {hit:.0f}%")

    l3 = [f"{GREY}burn{RESET} {WHITE}{fmt_tok(burn)}{RESET}{DIM}/min ↑{fmt_tok(burn_out)}{RESET}",
          f"{GREY}tok{RESET} {WHITE}{fmt_tok(tot_all)}{RESET}{DIM} ↓{fmt_tok(tot_in)} ↑{fmt_tok(tot_out)}{RESET}",
          f"{GREY}$rate{RESET} {WHITE}{fmt_usd(cost_rate)}/h{RESET}" + (f"{DIM} budget @{fmt_clock(budget_eta, now)}{RESET}" if budget_eta else "")]
    if model_parts:
        l3.append(f"{GREY}models{RESET} {seg_bar(model_parts)} " + " ".join(model_legend))

    sep = f" {DIM}│{RESET} "
    lines = [sep.join(l1), sep.join(l2), sep.join(l3)]
    return "\n".join(lines[: max(1, min(3, LINES))])


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    try:
        out = render(data)
    except Exception as e:  # never break the status bar
        out = (caveman_badge() + f" {DIM}stats err: {type(e).__name__}: {e}{RESET}").strip()
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
