setopt PROMPT_SUBST

# Disallow `>` to overwrite existing files. Use `>|`(sh compatible) or `>!`(zsh only) instead.
setopt NO_CLOBBER

# Allow comments starting with `#` in the interactive shell.
setopt INTERACTIVE_COMMENTS
# the cursor is moved to the end of the word if either a single match is inserted or menu completion is performed.
setopt alwaystoend

# Perform cd to a directory if the typed command is invalid, but is a directory.
setopt autocd
# useful for pushd, pushd +N, popd, cd -N, dirs -v
setopt autopushd
setopt pushdignoredups
setopt pushdsilent
# `PUSHDMINUS` swapped the meaning of `cd +1` and `cd -1`, in favor of `cd -N` for choosing N+1 th item from the top.
setopt pushdminus

setopt longlistjobs

# Ensures that Unicode combining characters are handled properly in Zsh
setopt combiningchars
# Allow completion in the middle of a word
setopt completeinword
# Disable XON/XOFF which is useless nowadays
# same as stty -ixon ?
setopt noflowcontrol

# ZSH uses this to determine how long to wait (in hundredths of a second) for additional characters in sequence. Default is 0.4 seconds.
# 1=10ms for key sequences
KEYTIMEOUT=1
