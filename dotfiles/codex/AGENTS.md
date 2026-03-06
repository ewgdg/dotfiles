# User-Level Agent Configuration

## Libraries and Dependencies

- Use latest libraries and frameworks, reference docs with `context7`

## File Operations

- Use soft deletion `gio trash` instead of `rm`

## Documentation

- document for features or techniques of a project, that worth mention or review
- if you need to write doc, store docs in `./docs/` directory

## Privileged Commands

- use `sudo -A` when execute commands with a non-interactive shell

## Code Quality

- Use descriptive, intention-revealing names; prioritize readability over brevity.

## Python Related

- Use `uv` for python package management
- Use `uv run` for running python scripts

## Github CLI

- If there is an appropriate template to use, always use `-T <template>` for `gh` to select the template

## CLI Tools

- `gh` for github
- `op` for 1password
