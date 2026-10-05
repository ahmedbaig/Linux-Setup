#!/usr/bin/env bash
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
STAMP="$(date +%Y%m%d-%H%M%S)"
DRY_RUN=0
DEPS=0
BREW=0
FORCE=0

usage() {
  cat <<EOF
usage: ./install.sh [--dry-run] [--deps] [--brew] [--force]

  --dry-run  show what would change, change nothing
  --deps     install oh-my-zsh, powerlevel10k, zsh-syntax-highlighting and tpm if missing
  --brew     run 'brew bundle' with the Brewfile (macOS)
  --force    overwrite ~/.claude/settings.json (otherwise only created when missing)

Existing files are moved to <file>.bak-<timestamp> before a link replaces them.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --deps) DEPS=1 ;;
    --brew) BREW=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) OS=macos ;;
  Linux) OS=linux ;;
  *) echo "unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac

run() {
  if (( DRY_RUN )); then echo "  would run: $*"; else "$@"; fi
}

link() {
  local src="$DOTFILES/$1" dest="$2"
  [ "$1" = . ] && src="$DOTFILES"
  [ -e "$src" ] || { echo "  missing in repo: $1" >&2; return 1; }
  if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
    echo "  ok       $dest"
    return
  fi
  run mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "  backup   $dest -> $dest.bak-$STAMP"
    run mv "$dest" "$dest.bak-$STAMP"
  fi
  echo "  link     $dest -> $src"
  run ln -s "$src" "$dest"
}

copy_once() {
  local src="$DOTFILES/$1" dest="$2"
  [ "$1" = . ] && src="$DOTFILES"
  if [ -e "$dest" ] && (( ! FORCE )); then
    echo "  keep     $dest (use --force to replace)"
    return
  fi
  run mkdir -p "$(dirname "$dest")"
  [ -e "$dest" ] && { echo "  backup   $dest -> $dest.bak-$STAMP"; run cp "$dest" "$dest.bak-$STAMP"; }
  echo "  copy     $dest"
  run cp "$src" "$dest"
}

clone_if_missing() {
  local repo="$1" dest="$2"
  if [ -d "$dest" ]; then echo "  ok       $dest"; return; fi
  echo "  clone    $repo -> $dest"
  run git clone --depth=1 "$repo" "$dest"
}

echo "dotfiles: $DOTFILES ($OS)$( (( DRY_RUN )) && echo ', dry run')"

if [ "$DOTFILES" != "$HOME/.dotfiles" ]; then
  echo "== ~/.dotfiles"
  link . "$HOME/.dotfiles"
fi

if (( DEPS )); then
  echo "== dependencies"
  clone_if_missing https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
  clone_if_missing https://github.com/romkatv/powerlevel10k.git "$HOME/powerlevel10k"
  clone_if_missing https://github.com/zsh-users/zsh-syntax-highlighting.git "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting"
  clone_if_missing https://github.com/tmux-plugins/tpm "$HOME/.tmux/plugins/tpm"
fi

if (( BREW )) && [ "$OS" = macos ]; then
  echo "== brew bundle"
  run brew bundle --file="$DOTFILES/Brewfile"
fi

echo "== zsh"
link "zsh/$OS/.zshrc" "$HOME/.zshrc"
link zsh/.p10k.zsh "$HOME/.p10k.zsh"

echo "== tmux"
link "tmux/$OS/.tmux.conf" "$HOME/.tmux.conf"
if [ "$OS" = macos ]; then
  link tmux/macos/tmux-powerline/config.sh "$HOME/.config/tmux-powerline/config.sh"
  link tmux/macos/tmux-powerline/segments/fzf.sh "$HOME/.config/tmux-powerline/segments/fzf.sh"
else
  link tmux/linux/.tmux-powerlinerc "$HOME/.tmux-powerlinerc"
  link bash/linux/.bashrc "$HOME/.bashrc"
fi

echo "== claude code"
copy_once claude/settings.json "$HOME/.claude/settings.json"
link claude/statusline.sh "$HOME/.claude/statusline.sh"
link claude/statusline.py "$HOME/.claude/statusline.py"
link claude/statusline_panels.py "$HOME/.claude/statusline_panels.py"
for hook in panel-toggle scope-set scope-tracker.py ccpanel-build ccpanel-handler.applescript; do
  link "claude/hooks/$hook" "$HOME/.claude/hooks/$hook"
done
if [ "$OS" = macos ] && [ -x /Applications/iTerm.app/Contents/Resources/utilities/cc-status ]; then
  link_target=/Applications/iTerm.app/Contents/Resources/utilities/cc-status
  if [ "$(readlink "$HOME/.config/iterm2/cc-status" 2>/dev/null)" != "$link_target" ]; then
    echo "  link     ~/.config/iterm2/cc-status -> $link_target"
    run mkdir -p "$HOME/.config/iterm2"
    run ln -sfn "$link_target" "$HOME/.config/iterm2/cc-status"
  else
    echo "  ok       ~/.config/iterm2/cc-status"
  fi
fi

echo "done. open a new shell; in tmux press prefix + I to install plugins."
