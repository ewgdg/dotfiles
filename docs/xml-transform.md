# XML Transform

Use dotman's public XML transform CLI for active package workflows:

```sh
dotman transform xml BASE OUTPUT \
  --mode cleanup|merge \
  [--overlay-file OVERLAY] \
  --selector-type remove|retain \
  --selectors SELECTOR...
```

Both operands accept `-` for streams. `--stdout` also emits output to stdout.
File output preserves base-file permissions. `--compare-file PATH` reuses that
file's exact bytes when transformed XML is semantically equal.

## Selectors and XML options

Unprefixed and `exact:` selectors use `fnmatch` against root-inclusive element
paths. `re:` selectors use regex search. Retain preserves matching subtrees and
required ancestor chains; remove deletes matching subtrees.

XML-specific options:

- `--sort-attributes` sorts each element's attributes
- repeatable `--sort-children NODE_PATH` sorts immediate children of matching parents
- `--compare-file PATH` includes selected child sorting in semantic comparison

Repeated siblings use tag plus available `id`, `name`, `key`, `uuid`, or
non-empty text identity. During merge, selectors filter base XML first, then
overlay XML is applied. This preserves unmanaged live state while allowing
repo-side deletion inside managed regions.

GoldenDict's helper performs only repository-specific Jinja rendering and
dictionary-path substitution. Cleanup, merge, selection, canonical sorting,
comparison, byte reuse, and file-mode behavior come from `dotman transform xml`.

Example:

```sh
dotman transform xml live.xml output.xml \
  --mode merge \
  --overlay-file repo.xml \
  --selector-type retain \
  --selectors 'config/WindowGeometry' \
  --sort-children 'config/mutedDictionaries' \
  --compare-file live.xml
```

## Transitional legacy code

`scripts/xml_transform.py` remains temporarily for unmigrated consumers and its
legacy tests. New workflows must use public dotman CLI. Generic implementation
removal is tracked separately in issue #16.
