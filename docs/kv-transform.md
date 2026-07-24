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

Home path normalization composes through Dotman's public CLI:

- render sends selected values through `dotman rewrite home expand`
- capture sends selected values through `dotman rewrite home collapse`

The separately installed `dotman` executable is the cross-repository contract;
`dotfiles-tools` does not depend on Dotman as a Python package. Rewrites apply
only to selected key values, not whole files.
