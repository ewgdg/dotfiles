# Transform Engine Interface

This document defines the Python contract for the future shared transformer CLI.
The goal is to separate:

- shared CLI concerns: mode selection, typed selector flags, request validation
- engine concerns: parsing, format-aware matching, merge/strip behavior, output
  serialization

## Core Types

The reference contract lives in
[`scripts/transform_engine.py`](/Users/xian/Projects/dotfiles/scripts/transform_engine.py).

- `TransformMode`
  - `strip`
  - `merge`
- `SelectorAction`
  - `strip`
  - `retain`
- `SelectorSpec`
  - declares one selector type supported by an engine
  - includes a stable engine name and a CLI-safe flag suffix
- `TransformRequest`
  - normalized request passed from the shared CLI into the engine
- `TransformEngine`
  - protocol each engine should implement
- `BaseTransformEngine`
  - convenience base class with common request validation

`TransformRequest` can also carry engine-specific parsed options through
`engine_options` when a format needs extra non-selector flags.

## Selector Model

Selectors are typed. The shared CLI should derive its flags from
`SelectorSpec.option_name()` instead of relying on string prefixes like `re:`.

That means a TOML engine can expose selector types such as:

- `key` -> `--retain-key` / `--strip-key`
- `table-regex` -> `--retain-table-regex` / `--strip-table-regex`

This avoids collisions between matcher syntax and key-path content.

## Engine Contract

Each engine should implement:

```python
class TransformEngine(Protocol):
    name: str

    @classmethod
    def selector_specs(cls) -> tuple[SelectorSpec, ...]: ...

    def requires_selectors(self) -> bool: ...

    def configure_parser(self, parser: argparse.ArgumentParser) -> None: ...

    def build_engine_options(
        self,
        parsed_args: argparse.Namespace,
    ) -> Mapping[str, Any]: ...

    def validate_request(self, request: TransformRequest) -> None: ...

    def transform(self, request: TransformRequest) -> None: ...
```

Design expectations:

- the shared CLI constructs `TransformRequest`
- engines may add format-specific CLI flags through `configure_parser()`
- engines may opt into selectorless operation through `requires_selectors()`
- parsed extra flags flow into `TransformRequest.engine_options`
- the engine validates engine-specific selector support
- the engine owns parsing, matching, and writing output
- merge semantics remain engine-defined, but the request shape stays shared

## Example

```python
from scripts.transform_engine import (
    BaseTransformEngine,
    SelectorSpec,
    TransformRequest,
)


class TomlEngine(BaseTransformEngine):
    name = "toml"
    SELECTOR_SPECS = (
        SelectorSpec(
            name="key",
            cli_flag="key",
            description="Exact TOML key path",
            examples=("model", "mcp_servers.playwright.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN"),
        ),
        SelectorSpec(
            name="table_regex",
            cli_flag="table-regex",
            description="Regex matching dotted TOML table paths",
            examples=(r"^projects\.", r"^mcp_servers\.playwright\.env$"),
        ),
    )

    def transform(self, request: TransformRequest) -> None:
        self.validate_request(request)
        ...
```

An engine like the plist transformer can override `requires_selectors()` and
return `False` so the shared CLI can support compare-only or whole-file
transforms without fake selector flags.

## Why This Shape

- keeps CLI concerns out of format engines
- avoids ambiguous matcher prefixes
- lets each engine declare its own selector vocabulary
- gives the future shared CLI enough metadata to generate flags and help text

The shared CLI implementation now lives in
[`scripts/transform_cli.py`](/Users/xian/Projects/dotfiles/scripts/transform_cli.py).
