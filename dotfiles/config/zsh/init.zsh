# Initialize ZSH configuration

ZSH_CONFIG_DIR=${ZSH_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/zsh}

source "$ZSH_CONFIG_DIR/env.zsh"
source "$ZSH_CONFIG_DIR/history.zsh"
source "$ZSH_CONFIG_DIR/options.zsh"

if [[ -o interactive ]]; then
    source "$ZSH_CONFIG_DIR/zim.zsh"
    source "$ZSH_CONFIG_DIR/vim-mode.zsh"
    source "$ZSH_CONFIG_DIR/theme.zsh"
    source "$ZSH_CONFIG_DIR/plugins/fzf-tab.zsh"
    source "$ZSH_CONFIG_DIR/plugins/zsh-plugins.zsh"
    source "$ZSH_CONFIG_DIR/plugins/fzf.zsh"
    source "$ZSH_CONFIG_DIR/plugins/fnm.zsh"
    source "$ZSH_CONFIG_DIR/plugins/zoxide.zsh"
    source "$ZSH_CONFIG_DIR/keybindings.zsh"
    source "$ZSH_CONFIG_DIR/aliases.zsh"
    source "$ZSH_CONFIG_DIR/agents.zsh"
fi
