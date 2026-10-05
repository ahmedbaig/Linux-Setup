-- URL handler for ccpanel:// links in the Claude Code status line.
-- Rebuild: ~/.claude/hooks/ccpanel-build
on open location theURL
	do shell script "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin $HOME/.claude/hooks/panel-toggle " & quoted form of theURL
end open location

on run
	do shell script "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin $HOME/.claude/hooks/panel-toggle"
end run
