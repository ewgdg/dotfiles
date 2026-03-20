# Dotdrop Template Update Helper

`dotdrop update` does not safely round-trip templated files back into the repo.
This repo ships a local helper for the manual part of that workflow:

```sh
uv run scripts/dotdrop_template_update.py <template-src> <live-file> --in-place
```

Example:

```sh
uv run scripts/dotdrop_template_update.py dotfiles/profile ~/.profile --in-place
uv run scripts/dotdrop_template_update.py dotfiles/gitconfig ~/.gitconfig --in-place
uv run scripts/dotdrop_template_update.py dotfiles/ssh/config ~/.ssh/config --in-place
```

After running it, review the result with `git diff`.

## Tests

Run the regression suite with:

```sh
uv run pytest
```

You can also target just the template-update regression file:

```sh
uv run pytest tests/test_dotdrop_template_update.py
```

## What It Does

The script uses a conservative heuristic merge:

- dotdrop control lines such as `{%@@ if ... @@%}` are preserved as-is
- lines that contain inline template expressions such as `{{@@ os @@}}` are kept as-is
- plain literal blocks are aligned against the rendered live file
- if a literal block is clearly the active branch between two matched anchors, the block is replaced from the live file
- otherwise the script only applies smaller in-block updates where the anchors are unambiguous

The goal is to preserve the template structure while still pulling back ordinary
literal edits from the live file.

## When It Works Well

- editing non-template sections in a templated file
- updating the currently active branch of an `if/elif/else` template block
- inserting or removing lines inside an active branch when the branch has stable anchor lines around the change
- updating small `if ... endif` sections even when the rendered branch has no exact line match left in the template source

## Known Limits

- inline template lines are not rewritten; the script keeps them unchanged
- blocks at the start or end of a file are handled more conservatively because they have fewer anchors
- if an active branch has too little stable literal context, new lines at the edge of that branch can be missed
- inactive branches are intentionally left unchanged
- zero-match updates in `if/elif/else` chains remain conservative because the active branch can be ambiguous without stronger anchors

## Suggested Workflow

1. Edit and validate the rendered file on the machine.
2. Run the helper against the templated source file in `dotfiles/`.
3. Review `git diff`.
4. Re-run `dotdrop compare` or `dotdrop install` to confirm the rendered output is still correct.
