typeset -gA _API_KEY_CACHE

get_api_key() {
  local service=$1
  [[ -n ${_API_KEY_CACHE[$service]} ]] || _API_KEY_CACHE[$service]=$(op item get "$service" --vault dev --field credential --reveal)
  echo ${_API_KEY_CACHE[$service]}
}

claudecode() {
    # ANTHROPIC_BASE_URL="https://litellm.service.xianzzz.com" \
    # ANTHROPIC_AUTH_TOKEN="litellm" \
    # ANTHROPIC_SMALL_FAST_MODEL="gpt-mini" \
    # ANTHROPIC_BASE_URL="http://0.0.0.0:8787" \
    ANTHROPIC_SMALL_FAST_MODEL="gpt-5-nano" \
    ANTHROPIC_BASE_URL="https://claude-router.service.xianzzz.com" \
    command claude --dangerously-skip-permissions "$@"
}

omp(){
  OPENAI_API_KEY=$(get_api_key openai-api) \
    ANTHROPIC_API_KEY=$(get_api_key anthropic-api) \
    OPENROUTER_API_KEY=$(get_api_key openrouter-api) \
    BRAVE_API_KEY=$(get_api_key brave-api) \
    EXA_API_KEY=$(get_api_key exa-api) \
    command omp
}
