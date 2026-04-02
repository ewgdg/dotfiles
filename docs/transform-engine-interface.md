# Transform Engine Interface

This document defines the Python-side contract behind the shared transform CLI.

It is the implementation guide for aligning each engine with the redesigned CLI
semantics.

## Core Types

The reference types live in [../scripts/transform_engine.py](../scripts/transform_engine.py).

- `TransformMode`
  - `cleanup`
  - `merge`
- `SelectorAction`
  - `remove`
  - `retain`
- `SelectorSpec`
  - declares one selector type supported by an engine
  - includes a stable engine name and a CLI-safe prefix
- `TransformRequest`
  - normalized request passed from the shared CLI into the engine
- `TransformEngine`
  - protocol each engine should implement
- `BaseTransformEngine`
  - convenience base class with common request validation

Important `TransformRequest` roles:

- `base_path`: primary operand and selector target
- `overlay_path`: secondary operand applied on top in merge mode
- `selectors_by_type`: parsed selector values grouped by engine-declared
  selector type
- `engine_options`: extra parsed flags for engine-specific behavior

## Shared Request Semantics

For a selector set `S`:

- cleanup + `retain`: write the retained subset of `base_path`
- cleanup + `remove`: write `base_path` with the matched subset removed
- merge + `retain`: overlay `overlay_path` onto the retained subset of
  `base_path`
- merge + `remove`: overlay `overlay_path` onto `base_path` with the matched
  subset removed

Selectors always target `TransformRequest.base_path`.
`TransformRequest.overlay_path` is never a selector target in the shared
contract.

To preserve repo-side deletions, an engine must build the preserved base
partition first and only then apply the overlay operand.
That rule applies recursively to nested managed content, not only to top-level
fields.

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
- the engine validates engine-specific selector syntax and supported modes
- the engine owns format-aware parsing, overlaying, and writing output
- merge semantics are shared, not engine-defined
- in merge mode, the engine must not recover removed managed content from the
  base operand after the overlay has been applied
- engine docs must document selector syntax, identity rules for repeated or
  nested structures, and any unsupported collection semantics

## Reference Pseudocode

The shared contract is easier to reason about as two steps:

```python
preserved_base = filter_base(request.base_path, request.selector_action, selectors)

if request.mode == TransformMode.CLEANUP:
    write_output(preserved_base)
    return

overlay_doc = load_overlay(request.overlay_path)
result = overlay(preserved_base, overlay_doc)
write_output(result)
```

The exact representation of `filter_base()` and `overlay()` is engine-specific,
but the operand roles are not.

## Why This Shape

- gives every engine the same selector target and the same merge model
- makes repo-managed deletions propagate on install, including nested deletions
- keeps format-specific complexity in selector parsing and structure identity,
  where it belongs
- leaves room for compare or serialization flags without changing semantic
  behavior
