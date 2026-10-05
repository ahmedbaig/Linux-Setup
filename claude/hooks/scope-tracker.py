#!/usr/bin/env python3
"""UserPromptSubmit hook: remind Claude to keep the status line scope balance honest."""
import json
import os
import sys

SCOPE_DIR = os.path.join(
    os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")), "statusline-stats", "scope"
)

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
sid = data.get("session_id") or ""
try:
    with open(os.path.join(SCOPE_DIR, f"{sid}.json")) as f:
        scope = json.load(f)
except Exception:
    scope = {}

goal = scope.get("goal") or "NOT SET"
repos = ",".join(scope.get("repos") or []) or "-"
print(
    f"SCOPE BALANCE (status line): goal={goal!r} repos={repos} "
    f"drift={scope.get('drift', 0)} halluc={scope.get('halluc', 0)}. "
    "Judge this prompt and your own recent work against the goal. "
    "drift 0-5 = unannounced wandering from goal (by user or you). "
    "halluc 0-5 = unverified claims, guessed APIs/paths/flags, retractions. "
    f"source={scope.get('source', '-')!r} refs={','.join(scope.get('refs') or []) or '-'}. "
    "If goal unset, the user explicitly pivots (set new goal, reset drift), or your "
    "assessment changed, run ~/.claude/hooks/scope-set [--goal ..] [--source 'chat #N'|doc-path] "
    "[--refs doc1,doc2] [--repos a,b] [--drift N] [--halluc N] [--note ..] once before "
    "ending the turn. Else skip it. "
    "Be honest, not flattering. Mention it only when drift or halluc is 3+."
)
