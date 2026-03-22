#!/usr/bin/env python3

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable


class TransformMode(StrEnum):
    STRIP = "strip"
    MERGE = "merge"


class SelectorAction(StrEnum):
    STRIP = "strip"
    RETAIN = "retain"


@dataclass(frozen=True)
class SelectorSpec:
    name: str
    cli_flag: str
    description: str
    examples: tuple[str, ...] = ()
    supported_modes: frozenset[TransformMode] = field(
        default_factory=lambda: frozenset({TransformMode.STRIP, TransformMode.MERGE})
    )

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("selector spec name must not be empty")
        if not self.cli_flag:
            raise ValueError("selector spec cli_flag must not be empty")
        if not self.description:
            raise ValueError("selector spec description must not be empty")
        if not self.supported_modes:
            raise ValueError("selector spec supported_modes must not be empty")

    def option_name(self, action: SelectorAction) -> str:
        return f"--{action.value}-{self.cli_flag}"


@dataclass(frozen=True)
class TransformRequest:
    base_path: Path
    output_path: Path
    mode: TransformMode
    selector_action: SelectorAction
    selectors_by_type: Mapping[str, tuple[str, ...]]
    overlay_path: Path | None = None
    engine_options: Mapping[str, Any] = field(default_factory=dict)

    def validate_basic(self) -> None:
        if self.mode == TransformMode.MERGE and self.overlay_path is None:
            raise ValueError("overlay_path is required when mode=merge")
        if self.mode == TransformMode.STRIP and self.overlay_path is not None:
            raise ValueError("overlay_path is only valid when mode=merge")

    def selector_values(self, selector_type: str) -> tuple[str, ...]:
        return self.selectors_by_type.get(selector_type, ())

    def engine_option(self, option_name: str, default: Any = None) -> Any:
        return self.engine_options.get(option_name, default)


@runtime_checkable
class TransformEngine(Protocol):
    name: str

    @classmethod
    def selector_specs(cls) -> tuple[SelectorSpec, ...]:
        ...

    def requires_selectors(self) -> bool:
        ...

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        ...

    def build_engine_options(
        self,
        parsed_args: argparse.Namespace,
    ) -> Mapping[str, Any]:
        ...

    def validate_request(self, request: TransformRequest) -> None:
        ...

    def transform(self, request: TransformRequest) -> None:
        ...


class BaseTransformEngine(ABC):
    name: ClassVar[str]
    SELECTOR_SPECS: ClassVar[tuple[SelectorSpec, ...]]

    @classmethod
    def selector_specs(cls) -> tuple[SelectorSpec, ...]:
        return cls.SELECTOR_SPECS

    @classmethod
    def selector_spec_map(cls) -> dict[str, SelectorSpec]:
        return {spec.name: spec for spec in cls.selector_specs()}

    def requires_selectors(self) -> bool:
        return True

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        del parser

    def build_engine_options(
        self,
        parsed_args: argparse.Namespace,
    ) -> Mapping[str, Any]:
        del parsed_args
        return {}

    def validate_request(self, request: TransformRequest) -> None:
        request.validate_basic()
        if self.requires_selectors() and not any(request.selectors_by_type.values()):
            raise ValueError("at least one selector value is required")

        supported_specs = self.selector_spec_map()
        unknown_selector_types = sorted(
            selector_type
            for selector_type in request.selectors_by_type
            if selector_type not in supported_specs
        )
        if unknown_selector_types:
            raise ValueError(
                f"{self.name} does not support selector types: {', '.join(unknown_selector_types)}"
            )

        unsupported_mode_selector_types = sorted(
            selector_type
            for selector_type in request.selectors_by_type
            if selector_type in supported_specs
            and request.selector_values(selector_type)
            and request.mode not in supported_specs[selector_type].supported_modes
        )
        if unsupported_mode_selector_types:
            raise ValueError(
                f"{self.name} selector types not supported in {request.mode.value} mode: "
                f"{', '.join(unsupported_mode_selector_types)}"
            )

    @abstractmethod
    def transform(self, request: TransformRequest) -> None:
        raise NotImplementedError
