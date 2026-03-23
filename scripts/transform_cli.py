#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.transform_engine import (  # noqa: E402
    SelectorAction,
    SelectorSpec,
    TransformEngine,
    TransformMode,
    TransformRequest,
)


def selector_dest(action: SelectorAction, spec: SelectorSpec) -> str:
    return f"{action.value}_{spec.name}"


def flatten_selector_groups(raw_groups: list[list[str]] | None) -> tuple[str, ...]:
    if not raw_groups:
        return ()
    return tuple(value for group in raw_groups for value in group)


def build_parser(engine: TransformEngine) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Run the {engine.name} transform engine using the shared transform CLI."
        )
    )
    parser.add_argument("base_path", type=Path, help="Base file. Repo file for install mode.")
    parser.add_argument("output_path", type=Path, help="Transformed output path.")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in TransformMode],
        required=True,
        help="Transform mode.",
    )
    parser.add_argument(
        "--overlay-file",
        "--merge-file",
        dest="overlay_path",
        type=Path,
        help="Overlay file. Required when --mode=merge.",
    )

    for spec in engine.selector_specs():
        for action in SelectorAction:
            parser.add_argument(
                spec.option_name(action),
                dest=selector_dest(action, spec),
                action="append",
                nargs="+",
                metavar=spec.cli_flag.upper().replace("-", "_"),
                help=f"{action.value.capitalize()} {spec.description}.",
            )

    engine.configure_parser(parser)
    return parser


def build_request(
    parser: argparse.ArgumentParser,
    engine: TransformEngine,
    parsed_args: argparse.Namespace,
) -> TransformRequest:
    selector_specs = engine.selector_specs()
    retained_selectors = {
        spec.name: flatten_selector_groups(
            getattr(parsed_args, selector_dest(SelectorAction.RETAIN, spec))
        )
        for spec in selector_specs
    }
    stripped_selectors = {
        spec.name: flatten_selector_groups(
            getattr(parsed_args, selector_dest(SelectorAction.STRIP, spec))
        )
        for spec in selector_specs
    }

    has_retained_selectors = any(retained_selectors.values())
    has_stripped_selectors = any(stripped_selectors.values())

    if has_retained_selectors and has_stripped_selectors:
        parser.error("selector flags must all use either retain or strip action")
    if not has_retained_selectors and not has_stripped_selectors:
        selector_action = SelectorAction.RETAIN
    else:
        selector_action = (
            SelectorAction.RETAIN if has_retained_selectors else SelectorAction.STRIP
        )
    selectors_by_type = retained_selectors if has_retained_selectors else stripped_selectors
    request = TransformRequest(
        base_path=parsed_args.base_path,
        output_path=parsed_args.output_path,
        mode=TransformMode(parsed_args.mode),
        selector_action=selector_action,
        selectors_by_type=selectors_by_type,
        overlay_path=parsed_args.overlay_path,
        engine_options=engine.build_engine_options(parsed_args),
    )

    try:
        engine.validate_request(request)
    except ValueError as error:
        parser.error(str(error))

    return request


def run_engine_cli(engine: TransformEngine, argv: list[str] | None = None) -> int:
    parser = build_parser(engine)
    parsed_args = parser.parse_args(argv)
    request = build_request(parser, engine, parsed_args)
    engine.transform(request)
    return 0
