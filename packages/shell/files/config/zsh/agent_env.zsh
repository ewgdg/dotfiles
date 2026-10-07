# Overrides for shells run by coding agents, applied after the human defaults.

# Claude Code (CLAUDECODE) and Codex (CODEX_THREAD_ID) replay this config into their tool shells.
# Pi and DeepSeek Harness run plain `bash -c`, so they never load it.
[[ -n ${CLAUDECODE}${CODEX_THREAD_ID} ]] || return 0

# Agents write files with `>` and expect it to overwrite; NO_CLOBBER makes that fail.
unsetopt NO_CLOBBER
