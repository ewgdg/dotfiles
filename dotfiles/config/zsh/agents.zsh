typeset -gA _API_KEY_CACHE

_load_api_key() {
  if ! _ensure_command op "1Password API key lookup"; then
    return 1
  fi

  local service env_var resolved_output print_script
  local index
  local -a missing_services env_assignments resolved_values

  for service in "$@"; do
    [[ -n ${_API_KEY_CACHE[$service]-} ]] && continue

    missing_services+=("$service")
    env_var="OP_CACHE_KEY_${#missing_services[@]}"
    env_assignments+=("${env_var}=op://dev/${service}/credential")
  done

  (( ${#missing_services[@]} )) || return 0

  print_script='printf "%s\\n"'
  for (( index = 1; index <= ${#missing_services[@]}; index++ )); do
    print_script+=" \"\$OP_CACHE_KEY_${index}\""
  done

  # Resolve all uncached secrets in one CLI invocation to avoid repeated startup overhead.
  resolved_output=$(env "${env_assignments[@]}" op run --no-masking -- zsh -fc "$print_script") || return 1
  resolved_values=("${(@f)resolved_output}")

  if (( ${#resolved_values[@]} != ${#missing_services[@]} )); then
    print -u2 -- "Failed to resolve expected number of API keys via op run"
    return 1
  fi

  for (( index = 1; index <= ${#missing_services[@]}; index++ )); do
    _API_KEY_CACHE[${missing_services[index]}]=${resolved_values[index]}
  done
}

claudecode() {
    if ! _ensure_command claude "Claude Code"; then
        return 1
    fi

    # ANTHROPIC_BASE_URL="https://litellm.service.xianzzz.com" \
    # ANTHROPIC_AUTH_TOKEN="litellm" \
    # ANTHROPIC_SMALL_FAST_MODEL="gpt-mini" \
    # ANTHROPIC_BASE_URL="http://0.0.0.0:8787" \
    ANTHROPIC_SMALL_FAST_MODEL="gpt-5-nano" \
    ANTHROPIC_BASE_URL="https://claude-router.service.xianzzz.com" \
    command claude --dangerously-skip-permissions "$@"
}

omp(){
  if ! _ensure_command omp "Pi coding agent"; then
    return 1
  fi

  _load_api_key openai-api anthropic-api openrouter-api brave-api exa-api || return 1

  OPENAI_API_KEY=${_API_KEY_CACHE[openai-api]} \
    ANTHROPIC_API_KEY=${_API_KEY_CACHE[anthropic-api]} \
    OPENROUTER_API_KEY=${_API_KEY_CACHE[openrouter-api]} \
    BRAVE_API_KEY=${_API_KEY_CACHE[brave-api]} \
    EXA_API_KEY=${_API_KEY_CACHE[exa-api]} \
    command omp "$@"
}
