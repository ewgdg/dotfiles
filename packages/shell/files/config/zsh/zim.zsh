# PLUGINS
#
# zimfw

zstyle ':zim:zmodule' use 'degit'

# Download zimfw plugin manager if missing.
if [[ ! -e ${ZIM_HOME}/zimfw.zsh ]]; then
    if _ensure_command curl "zimfw bootstrap"; then
        curl -fsSL --create-dirs -o ${ZIM_HOME}/zimfw.zsh \
            https://github.com/zimfw/zimfw/releases/latest/download/zimfw.zsh
    else
        return 0
    fi
fi

# Install missing modules and update ${ZIM_HOME}/init.zsh if missing or outdated.
if [[ ! ${ZIM_HOME}/init.zsh -nt ${ZIM_CONFIG_FILE:-${ZDOTDIR:-${HOME}}/.zimrc} ]]; then
    source ${ZIM_HOME}/zimfw.zsh init
fi

# Initialize modules.
source ${ZIM_HOME}/init.zsh
