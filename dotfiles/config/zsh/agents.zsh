typeset -gA _API_KEY_CACHE

_load_api_key() {
  if ! _ensure_command op "1Password API key lookup"; then
    return 1
  fi

  local service=$1
  [[ -n ${_API_KEY_CACHE[$service]-} ]] || _API_KEY_CACHE[$service]=$(op item get "$service" --vault dev --field credential --reveal)
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

  _load_api_key openai-api || return 1
  _load_api_key anthropic-api || return 1
  _load_api_key openrouter-api || return 1
  _load_api_key brave-api || return 1
  _load_api_key exa-api || return 1

  OPENAI_API_KEY=${_API_KEY_CACHE[openai-api]} \
    ANTHROPIC_API_KEY=${_API_KEY_CACHE[anthropic-api]} \
    OPENROUTER_API_KEY=${_API_KEY_CACHE[openrouter-api]} \
    BRAVE_API_KEY=${_API_KEY_CACHE[brave-api]} \
    EXA_API_KEY=${_API_KEY_CACHE[exa-api]} \
    command omp
}
