#!/usr/bin/env python3
"""Capture LinearMouse config without per-device identifiers."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]

DEVICE_IDENTIFIER_KEYS = {
    "vendorID",
    "productID",
    "productName",
    "serialNumber",
}


def merge_json(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = copy.deepcopy(base)
        for key, value in overlay.items():
            merged[key] = merge_json(merged[key], value) if key in merged else copy.deepcopy(value)
        return merged
    return copy.deepcopy(overlay)


def normalize_device_condition(condition: Any) -> Any:
    if not isinstance(condition, dict):
        return condition

    normalized = copy.deepcopy(condition)
    device = normalized.get("device")
    if isinstance(device, dict):
        category = device.get("category")
        if category:
            normalized["device"] = {"category": category}
        else:
            for key in DEVICE_IDENTIFIER_KEYS:
                device.pop(key, None)
    return normalized


def normalized_condition_key(condition: Any) -> str:
    return json.dumps(condition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sanitize_scheme_condition(raw_condition: Any) -> Any:
    if isinstance(raw_condition, list):
        normalized_conditions = [normalize_device_condition(condition) for condition in raw_condition]
        unique_conditions: list[Any] = []
        seen: set[str] = set()
        for condition in normalized_conditions:
            key = normalized_condition_key(condition)
            if key not in seen:
                seen.add(key)
                unique_conditions.append(condition)
        return unique_conditions
    return normalize_device_condition(raw_condition)


def sanitize_config(config: JsonObject) -> JsonObject:
    sanitized = copy.deepcopy(config)
    schemes = sanitized.get("schemes")
    if not isinstance(schemes, list):
        return sanitized

    merged_schemes: list[JsonObject] = []
    scheme_indexes_by_condition: dict[str, int] = {}

    for raw_scheme in schemes:
        if not isinstance(raw_scheme, dict):
            continue

        scheme = copy.deepcopy(raw_scheme)
        if "if" in scheme:
            scheme["if"] = sanitize_scheme_condition(scheme["if"])
        condition_key = normalized_condition_key(scheme.get("if"))

        if condition_key in scheme_indexes_by_condition:
            index = scheme_indexes_by_condition[condition_key]
            existing = merged_schemes[index]
            condition = existing.get("if")
            existing_without_if = {key: value for key, value in existing.items() if key != "if"}
            scheme_without_if = {key: value for key, value in scheme.items() if key != "if"}
            merged = merge_json(existing_without_if, scheme_without_if)
            if condition is not None:
                merged = {"if": condition, **merged}
            merged_schemes[index] = merged
        else:
            scheme_indexes_by_condition[condition_key] = len(merged_schemes)
            merged_schemes.append(scheme)

    sanitized["schemes"] = merged_schemes
    return sanitized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["capture"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    config = json.loads(args.path.read_text(encoding="utf-8"))
    sanitized = sanitize_config(config)
    print(json.dumps(sanitized, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
