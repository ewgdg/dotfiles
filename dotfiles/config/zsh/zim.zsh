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

if [[ -o interactive ]]; then
    _zimfw_autocheck() {
        (( ${+functions[zimfw]} )) || return

        zmodload zsh/datetime 2>/dev/null

        local stamp="${ZIM_HOME}/.zimfw-last-check"
        local now
        if [[ -n ${EPOCHSECONDS-} ]]; then
            now=$EPOCHSECONDS
        else
            now=$(date +%s)
        fi
        local ttl=$((7 * 24 * 60 * 60))

        if [[ -f ${stamp} ]]; then
            local last
            read -r last < "${stamp}"
            [[ -n ${last} ]] && (( now - last < ttl )) && return
        fi

        local output check_status show_msg=0 check_msg='[zimfw] Checking for updates...'
        if [[ -t 1 ]]; then
            printf '%s' "${check_msg}"
            show_msg=1
        fi

        output=$(zimfw check)
        check_status=$?

        if (( show_msg )); then
            printf '\r%*s\r' ${#check_msg} ''
        fi

        if (( check_status == 0 )); then
            if [[ -n ${output} ]]; then
                printf '%s\n' "${output}"
                printf '%s\n' "[zimfw] Updates available. Run 'zimfw update' to apply."
            fi
            printf '%s\n' "${now}" >| "${stamp}"
        fi
    }

    _zimfw_autocheck
fi
