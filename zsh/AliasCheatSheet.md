# Zsh Shortcut Cheat Sheet

This document provides a handy reference for various Zsh shortcuts and functions, including command aliases and custom functions for productivity and convenience.

## General Aliases

### Fun and Utility Aliases
- **today**: `calendar -A 0 -f /usr/share/calendar/calendar.mark | sort`  
  Displays today's calendar events.
- **dus**: `du -sckx * | sort -nr`  
  Shows disk usage of files and directories in the current directory, sorted by size.
- **adventure**: `emacs -batch -l dunnet`  
  Launches the Dunnet game in Emacs.
- **mailsize**: `du -hs ~/Library/mail`  
  Displays the size of the mail directory.
- **bk**: `cd $OLDPWD`  
  Switches back to the previous directory.
- **ttop**: `top -ocpu -R -F -s 2 -n30`  
  Runs `top` with CPU usage sorting.
- **lh**: `ls -a | egrep "^\."`  
  Lists hidden files.
- **python**: `/usr/bin/python3`  
  Runs Python 3.
- **v**: `fd --type f --exclude .git | fzf-tmux -p | xargs nvim`  
  Uses `fzf` to search and open files with `nvim`.
- **vim**: `nvim`  
  Alias for `nvim`.
- **vi**: `nvim`  
  Alias for `nvim`.
- **oldvim**: `vim`  
  Alias for the traditional `vim`.

### Safety Aliases
- **rm**: `rm -i`  
  Prompts before removing files.

## JBoss Aliases
- **startjboss**: `/usr/local/jboss-4.0.5.GA/bin/run.sh &`  
  Starts JBoss server.
- **stopjboss**: `/usr/local/jboss-4.0.5.GA/bin/shutdown.sh --shutdown`  
  Stops JBoss server.

## Mercurial (hg) Aliases
- **h**: `hg status`  
  Shows the status of the repository.
- **hc**: `hg commit`  
  Commits changes.
- **push**: `hg push`  
  Pushes changes to the remote repository.
- **pull**: `hg pull`  
  Pulls changes from the remote repository.
- **clone**: `hg clone`  
  Clones a repository.

## Git Aliases
- **ga**: `git add`  
  Adds files to the staging area.
- **gp**: `git push`  
  Pushes changes to the remote repository.
- **gl**: `git log`  
  Shows the commit log.
- **gs**: `git status`  
  Shows the status of the repository.
- **gd**: `git diff`  
  Shows differences between commits, commit, and working tree, etc.
- **gm**: `git commit -m`  
  Commits changes with a message.
- **gma**: `git commit -am`  
  Adds and commits changes with a message.
- **gb**: `git branch`  
  Lists branches.
- **gc**: `git checkout`  
  Checks out a branch or paths to the working tree.
- **gra**: `git remote add`  
  Adds a remote repository.
- **grr**: `git remote rm`  
  Removes a remote repository.
- **gpu**: `git pull`  
  Pulls changes from the remote repository.
- **gcl**: `git clone`  
  Clones a repository.
- **gta**: `git tag -a -m`  
  Tags a commit with an annotated tag.
- **gf**: `git reflog`  
  Shows the reference logs.
- **gh**: `git hist`  
  Shows the Git history.

## Miscellaneous Aliases
- **sloc**: `/usr/local/sloccount/bin/sloccount`  
  Runs `sloccount` to count lines of code.
- **rake**: `noglob rake`  
  Prevents globbing for the `rake` command.
- **wordy**: `wc -w * | sort | tail -n10`  
  Sorts files in the current directory by word count.
- **filecount**: `ls -aRF | wc -l`  
  Counts the number of files in the current directory recursively.

## Custom Functions

### Finder Visibility
- **hiddenOn**: `defaults write com.apple.Finder AppleShowAllFiles YES`  
  Shows hidden files in Finder.
- **hiddenOff**: `defaults write com.apple.Finder AppleShowAllFiles NO`  
  Hides hidden files in Finder.

### PostgreSQL Functions
- **psqlstart**: `/usr/local/pgsql/bin/pg_ctl -D /usr/local/pgsql/data -l logfile start`  
  Starts the PostgreSQL server.
- **psqlstop**: `/usr/local/pgsql/bin/pg_ctl stop`  
  Stops the PostgreSQL server.

### Man Pages in Preview
- **pman**: `ps=$(mktemp -t manpageXXXX).ps ; man -t $@ > "$ps" ; open "$ps"`  
  Opens man pages in Preview.

### Apache Tomcat Functions
- **tomcatup**: `/usr/local/tomcat/bin/startup.sh`  
  Starts Tomcat server.
- **tomcatdown**: `/usr/local/tomcat/bin/shutdown.sh`  
  Stops Tomcat server.

### Nicely Formatted Mount Information
- **nicemount**: `(echo "DEVICE PATH TYPE FLAGS" && mount | awk '$2="";1') | column -t`  
  Displays mounted drive information in a nicely formatted manner.

### IP Address Information
- **myip**: Displays the IP addresses of various network interfaces.

### New Functions
- **s**: `pwd > ~/.save_dir`  
  Saves the current directory to a file.
- **i**: `cd "$(cat ~/.save_dir)"`  
  Navigates to the saved directory.
- **c**: `cd "$@" && ls -alhtrS`  
  Changes directory and lists files sorted by size.
- **rgpg**: `gpgconf --kill gpg-agent && gpg-agent --daemon`  
  Restarts the GPG agent.
- **ktnls**: `pkill -f 'ssh -[LR]'`  
  Kills SSH tunnels.
- **f**: `fzf --height=40% --layout=reverse --info=inline --border --margin=1 --padding=1 --preview="cat {}" | xargs code`  
  Uses `fzf` to search and open files with `code`.

Keep this cheat sheet handy for quick reference to your custom Zsh shortcuts and functions!