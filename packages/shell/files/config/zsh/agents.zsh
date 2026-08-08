# disable rtk telemetry
export RTK_TELEMETRY_DISABLED=1

_merge_agent_instructions() {
  local target=$1
  shift

  local helper="$HOME/bin/agent-instruction-shim"
  if [[ ! -x "$helper" ]]; then
    print -u2 -- "Missing helper: $helper"
    return 1
  fi

  command "$helper" "$target" "$HOME/.agents/AGENTS.md" "$@"
}

_disable_legacy_agent_override() {
  local legacy_file=$1
  local disabled_file="${legacy_file}.disabled"

  if [[ ! -e "$legacy_file" && ! -L "$legacy_file" ]]; then
    return 0
  fi

  if command -v trash-put >/dev/null 2>&1; then
    command trash-put "$legacy_file" >/dev/null 2>&1 && return 0
  fi

  command mv -f "$legacy_file" "$disabled_file"
}

typeset -g _API_KEY_CACHE_SCHEMA="api-key-cache-v1"
typeset -g API_KEY_CACHE_TTL_SECONDS=${API_KEY_CACHE_TTL_SECONDS:-43200}
# Resolve 1Password secrets in one batched op run call.
_resolve_api_keys_from_1password() {
  emulate -L zsh

  if ! _ensure_command op "1Password API key lookup"; then
    return 1
  fi

  local env_var print_script resolved_output
  local index
  local -a env_assignments resolved_values

  reply=()

  (( $# )) || return 0

  for (( index = 1; index <= $#; index++ )); do
    env_var="OP_CACHE_KEY_${index}"
    env_assignments+=(
      "${env_var}=op://dev/${argv[index]}/credential"
    )
  done

  print_script='printf "%s\\n"'
  for (( index = 1; index <= $#; index++ )); do
    print_script+=" \"\$OP_CACHE_KEY_${index}\""
  done

  resolved_output=$(
    env "${env_assignments[@]}" \
      op run --no-masking -- zsh -fc "$print_script"
  ) || return 1

  resolved_values=("${(@f)resolved_output}")

  if (( ${#resolved_values[@]} != $# )); then
    print -u2 -- "Failed to resolve expected number of API keys via op run"
    return 1
  fi

  for (( index = 1; index <= $#; index++ )); do
    reply+=(
      "${argv[index]}"
      "${resolved_values[index]}"
    )
  done
}

_api_key_cache_available() {
  [[ $OSTYPE == linux* ]] \
    && [[ -n ${XDG_RUNTIME_DIR:-} && -d $XDG_RUNTIME_DIR ]] \
    && (( ${+commands[keyctl]} && ${+commands[flock]} ))
}

_api_key_cache_description() {
  REPLY="${_API_KEY_CACHE_SCHEMA}:$1"
}

_api_key_cache_ttl() {
  local ttl=$API_KEY_CACHE_TTL_SECONDS

  if [[ $ttl != <-> ]] || (( ttl <= 0 )); then
    print -u2 -- "API_KEY_CACHE_TTL_SECONDS must be a positive integer"
    return 1
  fi

  REPLY=$ttl
}

_api_key_cache_read() {
  emulate -L zsh

  local service=$1
  local description key_id payload
  local -a records

  _api_key_cache_description "$service"
  description=$REPLY
  key_id=$(command keyctl search @u user "$description" 2>/dev/null) || return 1
  payload=$(command keyctl pipe "$key_id" 2>/dev/null) || return 1
  records=( "${(@f)payload}" )

  (( ${#records} == 3 )) || return 1
  [[ ${records[1]} == $_API_KEY_CACHE_SCHEMA ]] || return 1
  [[ ${records[2]} == $service ]] || return 1
  [[ -n ${records[3]} ]] || return 1
  REPLY=${records[3]}
}

_api_key_cache_write() {
  emulate -L zsh

  local service=$1
  local value=$2
  local ttl=$3
  local description key_id
  local payload=$_API_KEY_CACHE_SCHEMA$'\n'$service$'\n'$value

  _api_key_cache_description "$service"
  description=$REPLY
  key_id=$(
    print -rn -- "$payload" \
      | command keyctl padd user "$description" @u
  ) || return 1

  if ! command keyctl timeout "$key_id" "$ttl"; then
    command keyctl unlink "$key_id" @u >/dev/null 2>&1
    return 1
  fi
}

_api_key_cache_delete() {
  emulate -L zsh

  local service=$1
  local description key_id

  _api_key_cache_description "$service"
  description=$REPLY
  key_id=$(command keyctl search @u user "$description" 2>/dev/null) || return 0
  command keyctl unlink "$key_id" @u
}

_api_key_cache_load() {
  emulate -L zsh

  local force_refresh=$1
  shift

  local lock_path lock_fd service ttl
  local index cache_write_failed=0
  local -A cached_keys
  local -a missing_services resolved_keys services=( "$@" )

  _api_key_cache_ttl || return 1
  ttl=$REPLY

  if (( ! force_refresh )); then
    for service in "${services[@]}"; do
      if _api_key_cache_read "$service"; then
        cached_keys[$service]=$REPLY
      else
        missing_services+=( "$service" )
      fi
    done

    if (( ${#missing_services} == 0 )); then
      reply=()
      for service in "${services[@]}"; do
        reply+=( "$service" "${cached_keys[$service]}" )
      done
      return 0
    fi
  fi

  lock_path="$XDG_RUNTIME_DIR/api-key-cache.lock"
  if ! exec {lock_fd}>>"$lock_path"; then
    print -u2 -- "Unable to open the Linux API key cache lock; bypassing cache"
    _resolve_api_keys_from_1password "${services[@]}"
    return
  fi

  if ! command flock -x "$lock_fd"; then
    exec {lock_fd}>&-
    print -u2 -- "Unable to lock the Linux API key cache; bypassing cache"
    _resolve_api_keys_from_1password "${services[@]}"
    return
  fi

  # Recheck every service after locking; another terminal may have populated a miss.
  cached_keys=()
  missing_services=()
  if (( force_refresh )); then
    missing_services=( "${services[@]}" )
  else
    for service in "${services[@]}"; do
      if _api_key_cache_read "$service"; then
        cached_keys[$service]=$REPLY
      else
        missing_services+=( "$service" )
      fi
    done
  fi

  if (( ${#missing_services} )); then
    if ! _resolve_api_keys_from_1password "${missing_services[@]}"; then
      exec {lock_fd}>&-
      return 1
    fi
    resolved_keys=( "${reply[@]}" )

    for (( index = 1; index <= ${#resolved_keys}; index += 2 )); do
      service=${resolved_keys[index]}
      cached_keys[$service]=${resolved_keys[index + 1]}
      _api_key_cache_write "$service" "${resolved_keys[index + 1]}" "$ttl" \
        || cache_write_failed=1
    done
  fi

  if (( cache_write_failed )); then
    print -u2 -- "Unable to update every API key cache entry; using resolved keys once"
  fi

  reply=()
  for service in "${services[@]}"; do
    reply+=( "$service" "${cached_keys[$service]}" )
  done
  exec {lock_fd}>&-
}

_load_api_keys() {
  emulate -L zsh

  reply=()
  (( $# )) || return 0

  if _api_key_cache_available; then
    _api_key_cache_load 0 "$@"
  else
    _resolve_api_keys_from_1password "$@"
  fi
}

api-key-cache-status() {
  emulate -L zsh

  if (( $# == 0 )); then
    print -u2 -- "usage: api-key-cache-status <service>..."
    return 2
  fi

  if ! _api_key_cache_available; then
    print -- "API key cache: unavailable on this platform"
    return 0
  fi

  local service warm_count=0
  local -a services=( "$@" )

  for service in "${services[@]}"; do
    _api_key_cache_read "$service" && (( warm_count++ ))
  done

  if (( warm_count == ${#services} )); then
    print -- "API key cache: warm"
  elif (( warm_count == 0 )); then
    print -- "API key cache: empty"
  else
    print -- "API key cache: partial (${warm_count}/${#services})"
  fi
}

api-key-cache-clear() {
  emulate -L zsh

  if (( $# == 0 )); then
    print -u2 -- "usage: api-key-cache-clear <service>..."
    return 2
  fi

  if ! _api_key_cache_available; then
    print -- "API key cache: unavailable on this platform"
    return 0
  fi

  local lock_fd service clear_failed=0
  local -a services=( "$@" )

  exec {lock_fd}>>"$XDG_RUNTIME_DIR/api-key-cache.lock" || return 1
  command flock -x "$lock_fd" || {
    exec {lock_fd}>&-
    return 1
  }

  for service in "${services[@]}"; do
    _api_key_cache_delete "$service" || clear_failed=1
  done

  exec {lock_fd}>&-
  (( clear_failed == 0 )) || return 1
  print -- "API key cache: cleared"
}

api-key-cache-refresh() {
  emulate -L zsh

  if (( $# == 0 )); then
    print -u2 -- "usage: api-key-cache-refresh <service>..."
    return 2
  fi

  if ! _api_key_cache_available; then
    print -- "API key cache: unavailable on this platform"
    return 1
  fi

  local -a reply services=( "$@" )
  _api_key_cache_load 1 "${services[@]}" || return 1
  print -- "API key cache: refreshed"
}

claude() {
  if ! _ensure_command claude "Claude Code"; then
      return 1
  fi

  command claude --dangerously-skip-permissions "$@"
}

claudex() {
  ANTHROPIC_BASE_URL="https://cliproxyapi.service.xianzzz.com" \
  ANTHROPIC_AUTH_TOKEN="local-cliproxyapi" \
  CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000 \
  CLAUDE_CODE_AUTO_COMPACT_WINDOW=272000 \
  CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90 \
  ANTHROPIC_DEFAULT_OPUS_MODEL="gpt-5.6-sol" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="gpt-5.6-terra" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="gpt-5.6-luna" \
  CLAUDE_CODE_ALWAYS_ENABLE_EFFORT=1 \
  CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY=3 \
  ENABLE_TOOL_SEARCH=false \
  claude "$@"
}

pi() (
  if ! _ensure_command pi "Pi coding agent"; then
    return 1
  fi

  local -A _keys
  local -a reply
  local -a api_key_services=(
    deepseek-api
    brave-api
    exa-api
  )

  _load_api_keys "${api_key_services[@]}" || return 1
  _keys=( "${reply[@]}" )

  export DEEPSEEK_API_KEY=${_keys[deepseek-api]}
  export BRAVE_API_KEY=${_keys[brave-api]}
  export EXA_API_KEY=${_keys[exa-api]}

  command pi "$@"
)
