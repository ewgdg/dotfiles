# Set the history file path
HISTFILE=$HOME/.zsh_history
# Set history save size and total history size
SAVEHIST=10000
HISTSIZE=10000
HISTORY_IGNORE="pwd:ls:clear"

# Set shell options for history behavior
setopt BANG_HIST
setopt SHARE_HISTORY
setopt APPEND_HISTORY
setopt INC_APPEND_HISTORY
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_FIND_NO_DUPS
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_SAVE_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt HIST_VERIFY
# Write the history file in the ':start:elapsed;command' format.
setopt EXTENDED_HISTORY
