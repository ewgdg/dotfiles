# Shell package

## API key cache

On Linux, agent wrappers can cache resolved 1Password API keys in the user
kernel keyring. The cache is shared by terminal instances, never written to a
regular file, and cleared by reboot. A kernel-enforced hard TTL limits the cache
to 12 hours by default.

Each service has an independent keyring entry. A caller can request any
combination of services; only missing entries are resolved, batched into one
`op run` call. Concurrent misses are serialized through an `flock` lock in
`$XDG_RUNTIME_DIR`, and every requested service is checked again after taking
the lock to prevent duplicate 1Password prompts.

On non-Linux systems, or when `keyctl`, `flock`, or `$XDG_RUNTIME_DIR` is
unavailable, callers resolve keys directly through 1Password as before.

Set a custom hard TTL in seconds before launching `pi`:

```zsh
export API_KEY_CACHE_TTL_SECONDS=21600
```

Cache management commands require the service names, keeping service selection
local to each caller rather than defining a global key set:

```zsh
api-key-cache-status service-a service-b
api-key-cache-refresh service-a service-b
api-key-cache-clear service-a service-b
```

The kernel keyring prevents plaintext persistence, but it is not a security
boundary against privileged processes or processes running as the same user
that can access the user keyring. Suspend and hibernation are not reboots, so
the TTL still governs cache lifetime across them.
