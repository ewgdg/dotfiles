#!/bin/bash

# Claude Code statusline script matching oh-my-posh theme
input=$(cat)
current_dir=$(echo "$input" | jq -r '.workspace.current_dir')
model_name=$(echo "$input" | jq -r '.model.display_name')
output_style=$(echo "$input" | jq -r '.output_style.name')
context_size=$(echo "$input" | jq -r '.context_window.context_window_size // empty')
context_pct_reported=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
usage_total=$(echo "$input" | jq -r 'if .context_window.current_usage != null then ((.context_window.current_usage.input_tokens // 0) + (.context_window.current_usage.cache_creation_input_tokens // 0) + (.context_window.current_usage.cache_read_input_tokens // 0)) else empty end')
cache_read_tokens=$(echo "$input" | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')
effort_level=$(echo "$input" | jq -r '.effort.level // empty')
five_hour_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
seven_day_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')

# Keep the last completed API usage per session. Claude Code can send transient
# zero/null context values while a request or compaction is in progress.
session_id=$(echo "$input" | jq -r '.session_id // empty')
state_file=""
saved_context_pct=""
saved_context_total=""
saved_cache_hit=""
if [ -n "$session_id" ]; then
    state_dir="$HOME/.claude/statusline-state"
    state_key=$(printf '%s' "$session_id" | tr -cd '[:alnum:]_-')
    state_file="${state_dir}/${state_key}"
    if [ -r "$state_file" ]; then
        IFS=' ' read -r saved_context_pct saved_context_total saved_cache_hit < "$state_file"
    fi
fi

new_context_pct=""
new_context_total=""
new_cache_hit=""
if [ -n "$usage_total" ] && [ "$usage_total" -gt 0 ]; then
    if [ -n "$context_pct_reported" ] && [ -n "$context_size" ] && [ "$context_size" -gt 0 ]; then
        new_context_pct=$(awk "BEGIN {
            pct = $context_pct_reported
            if (pct < 0) pct = 0
            if (pct > 100) pct = 100
            printf \"%.1f\", pct
        }")
        if [ "$context_size" -ge 1000000 ]; then
            new_context_total=$(awk "BEGIN {printf \"%.1fm\", $context_size / 1000000}")
        elif [ "$context_size" -ge 1000 ]; then
            new_context_total=$(awk "BEGIN {printf \"%.0fk\", $context_size / 1000}")
        else
            new_context_total="$context_size"
        fi
    fi
    new_cache_hit=$(awk "BEGIN {printf \"%.0f\", ($cache_read_tokens / $usage_total) * 100}")
    if [ -n "$state_file" ]; then
        mkdir -p "$(dirname "$state_file")" 2>/dev/null
        state_tmp="${state_file}.$$"
        state_context_pct="${new_context_pct:-$saved_context_pct}"
        state_context_total="${new_context_total:-$saved_context_total}"
        printf '%s %s %s\n' "$state_context_pct" "$state_context_total" "$new_cache_hit" > "$state_tmp" && mv -f "$state_tmp" "$state_file"
    fi
fi

context_pct="${new_context_pct:-$saved_context_pct}"
context_total="${new_context_total:-$saved_context_total}"
cache_hit="${new_cache_hit:-$saved_cache_hit}"

# Color palette matching oh-my-posh config
pink='\033[38;5;218m'      # F1C2A6 equivalent
cyan='\033[96m'            # lightCyan
green='\033[92m'           # lightGreen  
yellow='\033[93m'          # yellow
blue='\033[94m'            # lightBlue
red='\033[91m'             # lightRed
reset='\033[0m'

# Username (matching oh-my-posh pink)
printf "${pink}%s${reset}" "$(whoami)"

# Current directory (matching oh-my-posh cyan, show folder name)
printf " ${cyan}%s${reset}" "$(basename "$current_dir")"

# Git information (just branch name, no status)
if git -C "$current_dir" rev-parse --git-dir >/dev/null 2>&1; then
    # Get branch name, truncate to 25 chars like oh-my-posh
    branch=$(git -C "$current_dir" branch --show-current 2>/dev/null || echo 'HEAD')
    branch_short=$(printf "%.25s" "$branch")
    printf " ${green}%s${reset}" "$branch_short"
fi

# Model, output style, and effort
model_label=$(echo "$model_name" | sed 's/Claude //')
if [ "$output_style" != "default" ]; then
    model_label="${model_label}:${output_style}"
fi
if [ -n "$effort_level" ]; then
    printf " ${blue}%s•%s${reset}" "$model_label" "$effort_level"
else
    printf " ${blue}%s${reset}" "$model_label"
fi

# Context usage
if [ -n "$context_pct" ]; then
    context_used=$(printf '%.0f' "$context_pct")
    if [ "$context_used" -ge 85 ]; then
        context_color="$red"
    elif [ "$context_used" -ge 70 ]; then
        context_color="$yellow"
    else
        context_color="$green"
    fi
    if [ -n "$context_total" ]; then
        printf " %b" "${context_color}${context_pct}%/${context_total}${reset}"
    else
        printf " %b" "${context_color}${context_pct}%${reset}"
    fi
fi

# Prompt cache hit rate (kept from the last completed API call while running)
if [ -n "$cache_hit" ]; then
    printf " ${blue}CH:%s%%${reset}" "$cache_hit"
fi

# Quota / rate limit state (only shown after first API response)
# Displays remaining quota (100 - used_percentage)
if [ -n "$five_hour_pct" ] || [ -n "$seven_day_pct" ]; then
    quota_parts=""
    if [ -n "$five_hour_pct" ]; then
        five_used=$(printf '%.0f' "$five_hour_pct")
        five_remaining=$((100 - five_used))
        if [ "$five_remaining" -lt 10 ]; then
            quota_color="$red"
        elif [ "$five_remaining" -lt 30 ]; then
            quota_color="$yellow"
        else
            quota_color="$green"
        fi
        quota_parts="${quota_color}5h:${five_remaining}%${reset}"
    fi
    if [ -n "$seven_day_pct" ]; then
        week_used=$(printf '%.0f' "$seven_day_pct")
        week_remaining=$((100 - week_used))
        if [ "$week_remaining" -lt 10 ]; then
            week_color="$red"
        elif [ "$week_remaining" -lt 30 ]; then
            week_color="$yellow"
        else
            week_color="$green"
        fi
        week_part="${week_color}7d:${week_remaining}%${reset}"
        if [ -n "$quota_parts" ]; then
            quota_parts="${quota_parts} ${week_part}"
        else
            quota_parts="$week_part"
        fi
    fi
    printf " %b" "$quota_parts"
fi

