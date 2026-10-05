# Claude Code setup

User-level Claude Code config: settings, a status line with usage stats, and two side panels (WORK and SCOPE).

| File | Goes to | What it does |
|---|---|---|
| `settings.json` | `~/.claude/settings.json` | model, hooks, permissions, status line (1s refresh), caveman plugin |
| `statusline.sh` | `~/.claude/statusline.sh` | entry point; serves a cached render for up to 4s so the 1s ticks stay cheap |
| `statusline.py` | `~/.claude/statusline.py` | context, cost, tokens, burn rate and rate-limit forecasts as bar graphs |
| `statusline_panels.py` | `~/.claude/statusline_panels.py` | WORK (repos and files touched) and SCOPE (drift vs. hallucination balance, goal source, refs, what is in context) panels |
| `hooks/panel-toggle` | `~/.claude/hooks/` | show or hide the panels (`show`, `hide`, `section NAME`) |
| `hooks/scope-set` | `~/.claude/hooks/` | pin the goal, source, refs and drift/halluc scores shown in SCOPE |
| `hooks/scope-tracker.py` | `~/.claude/hooks/` | UserPromptSubmit hook that feeds the scope state back to the model each turn |
| `hooks/ccpanel-*` | `~/.claude/hooks/` | optional `ccpanel://` URL handler app (clicks don't reach it in fullscreen mode) |

`../install.sh` links all of these. The other hooks call iTerm2's `cc-status` utility through `~/.config/iterm2/cc-status`, which the installer links when iTerm2 is present.

Status line tunables: `CC_STATS_COST_BUDGET`, `CC_STATS_BAR_WIDTH`, `CC_STATS_WINDOW_MIN`, `CC_STATS_LAYOUT` (`wide` or `compact`), `CC_STATS_LINES`, `CC_PANEL_KEY`.

## Panel toggle key (iTerm2)

Claude Code keybindings can't run shell commands, so the toggle is an iTerm2 binding:
Settings → Keys → Key Bindings → **+** → shortcut **Ctrl-Option-X**, action **Run Coprocess**, command:

```
~/.claude/hooks/panel-toggle >/dev/null 2>&1
```

Avoid Ctrl-Z (suspends Claude Code) and Ctrl-X (prefix for Claude Code's `ctrl+x …` chords).

## Pinning the scope

```sh
~/.claude/hooks/scope-set --goal "what this session is for" --source "chat #1" --refs docs/plan.md
```
