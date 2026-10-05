# linux-setup

My terminal setup for macOS and Linux: zsh with powerlevel10k, tmux with tmux-powerline, fzf and jump for getting around, and a Claude Code status line with side panels.

## Layout

| Path | What |
|---|---|
| `zsh/macos/.zshrc`, `zsh/linux/.zshrc` | oh-my-zsh, aliases, lazy-loaded nvm and gvm, fzf and jump helpers |
| `zsh/.p10k.zsh` | powerlevel10k prompt, shared by both systems |
| `zsh/AliasCheatSheet.md` | the oh-my-zsh git aliases worth remembering |
| `bash/linux/.bashrc` | bash fallback for Linux boxes |
| `tmux/macos/`, `tmux/linux/` | tmux config (prefix `C-a`), tpm plugins, tmux-powerline config and an fzf segment |
| `claude/` | Claude Code settings, status line and hooks (see [claude/README.md](claude/README.md)) |
| `Brewfile` | everything installed through Homebrew on the Mac |
| `docker/` | compose files for local databases, mail catcher, metrics, SonarQube |
| `scripts/` | ssh and tunnel helpers, shell script templates, a display reset for macOS |
| `install.sh` | links everything into place |

## Install

```sh
git clone https://github.com/ahmedbaig/linux-setup.git ~/.dotfiles
cd ~/.dotfiles
./install.sh --dry-run          # preview
./install.sh --deps --brew      # oh-my-zsh, powerlevel10k, tpm, Homebrew packages, then links
```

`install.sh` picks the macOS or Linux variant itself. Files it replaces are kept as `<file>.bak-<timestamp>`, and running it again changes nothing.
`~/.claude/settings.json` is copied rather than linked, because Claude Code rewrites it; pass `--force` to replace an existing one.
Inside tmux, press `prefix` + `I` once to install the plugins.

On Linux without Homebrew, install the tools with the package manager first:

```sh
sudo apt update && sudo apt install -y zsh tmux fzf fd-find neovim curl git dialog
chsh -s "$(which zsh)"
```

## Getting around

| Keys / command | Does |
|---|---|
| `z <part of a path>` | jump to a frequently used directory ([jump](https://github.com/gsamokovarov/jump), bound to `z`) |
| `v` | fuzzy-pick a file under the current directory (fd + fzf in a tmux popup) and open it in nvim |
| `f` | fuzzy-pick a file with a preview and open it in Cursor |
| `s`, then `i` | save the current directory, come back to it later from any shell |
| `c <dir>` | cd and list by size |
| `ktnls` | kill every open ssh tunnel |

The jump init script is cached in `~/.cache/jump-init.zsh` and regenerated only when the jump binary changes, which keeps shell start fast.

## tmux

| Keys | Does |
|---|---|
| `C-a` | prefix |
| `prefix` `\|` / `-` | split right / down in the current directory |
| `Alt` + arrows | move between panes |
| `prefix` `e` / `E` | type into all panes / stop |
| `prefix` `/` | fuzzy search the pane's scrollback with fzf |
| `prefix` `P` / `A` | live grep filter on this pane / all panes in a popup |
| `prefix` `u` | pick a URL from the visible pane |
| `prefix` `r` | reload the config |

## Docker examples

Each file in `docker/` runs on its own, for example `docker compose -f docker/docker-compose-postgresql.yml up -d`.
Passwords come from the environment with local-only defaults; copy `docker/.env.example` to `docker/.env` to change them.
