#!/bin/bash

# Claude Code statusline script matching oh-my-posh theme
input=$(cat)
current_dir=$(echo "$input" | jq -r '.workspace.current_dir')
model_name=$(echo "$input" | jq -r '.model.display_name')
output_style=$(echo "$input" | jq -r '.output_style.name')
five_hour_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
seven_day_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')

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

# Model and output style info (subtle, at the end)
if [ "$output_style" != "default" ]; then
    printf " ${blue}%s:%s${reset}" "$(echo "$model_name" | sed 's/Claude //')" "$output_style"
else
    printf " ${blue}%s${reset}" "$(echo "$model_name" | sed 's/Claude //')"
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

# Time (matching oh-my-posh right prompt time format)
printf " ${blue}[%s]${reset}" "$(date +%H:%M:%S)"