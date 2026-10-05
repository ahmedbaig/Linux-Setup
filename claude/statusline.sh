#!/bin/sh
# Status line entry point (refreshInterval 1s). Reuses this session's last render
# for up to 4s so the 1s ticks cost a cat, not a Python run; hooks/panel-toggle
# deletes the cache so a show/hide lands on the next tick.
DIR="$HOME/.claude/statusline-stats/cache"
OUT="$DIR/$PPID.out"
export CLAUDE_PID="${CLAUDE_PID:-$PPID}"

if [ -f "$OUT" ] && [ $(( $(date +%s) - $(stat -f %m "$OUT") )) -lt 4 ]; then
  cat >/dev/null
  cat "$OUT"
  exit 0
fi

mkdir -p "$DIR"
find "$DIR" -name '*.out' -mmin +60 -delete 2>/dev/null  # ended sessions
python3 "$HOME/.claude/statusline.py" > "$OUT.tmp"
cat "$OUT.tmp"
mv -f "$OUT.tmp" "$OUT"
