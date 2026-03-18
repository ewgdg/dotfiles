# zsh-autosuggestions
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# zsh-syntax-highlighting
ZSH_HIGHLIGHT_HIGHLIGHTERS+=(main brackets pattern)
typeset -A ZSH_HIGHLIGHT_PATTERNS
# To have commands starting with `rm -rf` highlighted:
ZSH_HIGHLIGHT_PATTERNS+=('rm -rf *' 'fg=yellow,bold,underline')
