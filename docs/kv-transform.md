# Key/Value Transform

`scripts/kv_transform.py` renders and captures simple line-based `key=value`
config files for package targets that need small structured rewrites without a
package-local script.

It preserves non-key lines and unknown live keys during render. It is intended
for simple flat config files, not full INI section semantics.

## Commands

```sh
uv run scripts/kv_transform.py render repo.conf \
  --live-path live.conf \
  --home-expand-keys example-key \
  --require-keys example-key
```

```sh
uv run scripts/kv_transform.py capture live.conf \
  --remove-keys example-runtime-key \
  --home-collapse-keys example-key \
  --require-keys example-key
```

## Home Path Rewrites

Home path normalization reuses `scripts/text_rewrite.py` helpers:

- render: `~` and `~/...` become `$HOME` and `$HOME/...`
- capture: `$HOME` and `$HOME/...` become `~` and `~/...`

Rewrites apply only to selected key values, not whole files.
