# shellcheck shell=bash
# Display fzf indicator/trigger segment

TMUX_POWERLINE_SEG_FZF_SYMBOL="${TMUX_POWERLINE_SEG_FZF_SYMBOL:-🔍}"
TMUX_POWERLINE_SEG_FZF_TEXT="${TMUX_POWERLINE_SEG_FZF_TEXT:-fzf}"

generate_segmentrc() {
	read -r -d '' rccontents <<EORC
# Symbol to display (default: 🔍)
export TMUX_POWERLINE_SEG_FZF_SYMBOL="${TMUX_POWERLINE_SEG_FZF_SYMBOL}"
# Text to display (default: fzf)
export TMUX_POWERLINE_SEG_FZF_TEXT="${TMUX_POWERLINE_SEG_FZF_TEXT}"
EORC
	echo "$rccontents"
}

run_segment() {
	local output="${TMUX_POWERLINE_SEG_FZF_SYMBOL:-🔍} ${TMUX_POWERLINE_SEG_FZF_TEXT:-f}"
	echo "$output"
	return 0
}

