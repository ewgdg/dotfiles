#
# DOTFILES
#
ZSH_PLUGIN_DIR=${ZSH_PLUGIN_DIR:-$HOME/.zsh-plugins}
ZIM_HOME=${ZIM_HOME:-$ZSH_PLUGIN_DIR}
ZIM_CONFIG_FILE=${ZIM_CONFIG_FILE:-$ZSH_CONFIG_DIR/.zimrc}

export EDITOR=nvim
export SYSTEMD_EDITOR=nvim

if [ -f "$HOME/dotfiles/config.yaml" ]; then
    export DOTDROP_CONFIG="$HOME/dotfiles/config.yaml"
elif [ -f "$HOME/projects/dotfiles/config.yaml" ]; then
    export DOTDROP_CONFIG="$HOME/projects/dotfiles/config.yaml"
fi

# custom env
export PROJECTS_PATH=~/projects

typeset -gA _ZSH_WARNED_COMMANDS
_ensure_command() {
    local command_name=$1
    local feature=${2:-$command_name}
    local warn_key="${command_name}:${feature}"

    (( ${+commands[$command_name]} )) && return 0

    if [[ -o interactive && -z ${_ZSH_WARNED_COMMANDS[$warn_key]} ]]; then
        print -u2 -- "[zsh] missing command '${command_name}'; ${feature} disabled"
        _ZSH_WARNED_COMMANDS[$warn_key]=1
    fi

    return 1
}
