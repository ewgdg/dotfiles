#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


RULES_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "niri"
    / "event-stream-rules.json"
)
WINDOW_STATE_EVENT_MARKERS = (
    '"WindowsChanged"',
    '"WindowOpenedOrChanged"',
    '"WindowClosed"',
)


@dataclass(frozen=True)
class FieldMatcher:
    field_name: str
    equals_value: Any | None = None
    regex_pattern: re.Pattern[str] | None = None


@dataclass(frozen=True)
class CompiledRule:
    name: str
    event: str
    previous_matchers: tuple[FieldMatcher, ...]
    current_matchers: tuple[FieldMatcher, ...]
    action_type: str
    action_target: str


@dataclass
class RuleCache:
    mtime_ns: int | None = None
    rules: tuple[CompiledRule, ...] = ()


def niri_json(*args: str) -> Any:
    result = subprocess.run(
        ["niri", "msg", "-j", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return json.loads(result.stdout or "null")


def windows_snapshot() -> dict[str, dict[str, Any]]:
    try:
        data = niri_json("windows")
    except Exception:
        return {}

    if not isinstance(data, list):
        return {}

    windows_by_id: dict[str, dict[str, Any]] = {}
    for window in data:
        if not isinstance(window, dict):
            continue
        window_id = str(window.get("id", "") or "")
        if not window_id:
            continue
        windows_by_id[window_id] = dict(window)

    return windows_by_id


def focused_window_from_snapshot(windows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for window in windows_by_id.values():
        if window.get("is_focused") is True:
            return dict(window)
    return {}


def close_window(window_id: str) -> None:
    if not window_id:
        return
    subprocess.run(
        ["niri", "msg", "action", "close-window", "--id", window_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )


def compile_field_matcher(field_name: str, expected: Any) -> FieldMatcher:
    if isinstance(expected, dict):
        if "regex" in expected:
            flags = re.IGNORECASE if expected.get("ignore_case", False) else 0
            return FieldMatcher(
                field_name=field_name,
                regex_pattern=re.compile(str(expected["regex"]), flags),
            )
        if "equals" in expected:
            return FieldMatcher(field_name=field_name, equals_value=expected["equals"])
        raise ValueError(f"unsupported matcher for field {field_name!r}")

    return FieldMatcher(field_name=field_name, equals_value=expected)


def compile_matchers(match_spec: Any) -> tuple[FieldMatcher, ...]:
    if not match_spec:
        return ()
    if not isinstance(match_spec, dict):
        raise ValueError("match scope must be an object")

    return tuple(
        compile_field_matcher(field_name, expected_value)
        for field_name, expected_value in match_spec.items()
    )


def compile_rule(rule: dict[str, Any]) -> CompiledRule:
    event_name = str(rule.get("event", "") or "")
    action = rule.get("action", {})
    if not isinstance(action, dict):
        raise ValueError("action must be an object")

    action_type = str(action.get("type", "") or "")
    if action_type != "close-window":
        raise ValueError(f"unsupported action type {action_type!r}")

    action_target = str(action.get("target", "previous") or "previous")
    if action_target not in {"previous", "current"}:
        raise ValueError(f"unsupported action target {action_target!r}")

    match_spec = rule.get("match", {})
    if not isinstance(match_spec, dict):
        raise ValueError("match must be an object")

    return CompiledRule(
        name=str(rule.get("name", "") or "<unnamed>"),
        event=event_name,
        previous_matchers=compile_matchers(match_spec.get("previous", {})),
        current_matchers=compile_matchers(match_spec.get("current", {})),
        action_type=action_type,
        action_target=action_target,
    )


def load_rules(cache: RuleCache) -> tuple[CompiledRule, ...]:
    try:
        stat_result = RULES_PATH.stat()
    except OSError:
        cache.mtime_ns = None
        cache.rules = ()
        return cache.rules

    if cache.mtime_ns == stat_result.st_mtime_ns:
        return cache.rules

    try:
        raw = RULES_PATH.read_text(encoding="utf-8")
    except OSError:
        return cache.rules

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"event-stream-rules: failed to parse {RULES_PATH}: {exc}", file=sys.stderr)
        return cache.rules

    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        print(f"event-stream-rules: expected 'rules' to be a list in {RULES_PATH}", file=sys.stderr)
        return cache.rules

    compiled_rules: list[CompiledRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        try:
            compiled_rules.append(compile_rule(raw_rule))
        except ValueError as exc:
            rule_name = raw_rule.get("name", "<unnamed>")
            print(f"event-stream-rules: skipping rule {rule_name!r}: {exc}", file=sys.stderr)

    cache.mtime_ns = stat_result.st_mtime_ns
    cache.rules = tuple(compiled_rules)
    return cache.rules


def matchers_match(matchers: tuple[FieldMatcher, ...], candidate: dict[str, Any]) -> bool:
    for matcher in matchers:
        actual_value = candidate.get(matcher.field_name)
        if matcher.regex_pattern is not None:
            if not isinstance(actual_value, str):
                return False
            if matcher.regex_pattern.search(actual_value) is None:
                return False
            continue
        if actual_value != matcher.equals_value:
            return False
    return True


def rule_matches(rule: CompiledRule, previous: dict[str, Any], current: dict[str, Any]) -> bool:
    if rule.event != "focus-changed":
        return False

    if rule.previous_matchers and not matchers_match(rule.previous_matchers, previous):
        return False

    if rule.current_matchers and not matchers_match(rule.current_matchers, current):
        return False

    return True


def apply_action(rule: CompiledRule, previous: dict[str, Any], current: dict[str, Any]) -> None:
    target_window = previous if rule.action_target == "previous" else current
    window_id = str(target_window.get("id", "") or "")

    if rule.action_type == "close-window":
        close_window(window_id)


def apply_event_to_snapshot(
    event_data: dict[str, Any], windows_by_id: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    updated_windows = windows_by_id

    windows_changed = event_data.get("WindowsChanged")
    if isinstance(windows_changed, dict):
        windows_payload = windows_changed.get("windows")
        if isinstance(windows_payload, list):
            next_windows: dict[str, dict[str, Any]] = {}
            for window in windows_payload:
                if not isinstance(window, dict):
                    continue
                window_id = str(window.get("id", "") or "")
                if window_id:
                    next_windows[window_id] = dict(window)
            updated_windows = next_windows

    window_opened_or_changed = event_data.get("WindowOpenedOrChanged")
    if isinstance(window_opened_or_changed, dict):
        window_payload = window_opened_or_changed.get("window")
        if isinstance(window_payload, dict):
            window_id = str(window_payload.get("id", "") or "")
            if window_id:
                if updated_windows is windows_by_id:
                    updated_windows = dict(windows_by_id)
                if window_payload.get("is_focused") is True:
                    for existing_window_id, existing_window in updated_windows.items():
                        if existing_window_id == window_id:
                            continue
                        if existing_window.get("is_focused") is True:
                            updated_windows[existing_window_id] = {
                                **existing_window,
                                "is_focused": False,
                            }
                updated_windows[window_id] = dict(window_payload)

    window_closed = event_data.get("WindowClosed")
    if isinstance(window_closed, dict):
        window_id = str(window_closed.get("id", "") or "")
        if window_id and window_id in updated_windows:
            if updated_windows is windows_by_id:
                updated_windows = dict(windows_by_id)
            updated_windows.pop(window_id, None)

    return updated_windows


def main() -> int:
    rule_cache = RuleCache()
    windows_by_id = windows_snapshot()
    previous = focused_window_from_snapshot(windows_by_id)

    process = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    assert process.stdout is not None
    for event_line in process.stdout:
        if not any(marker in event_line for marker in WINDOW_STATE_EVENT_MARKERS):
            continue

        try:
            event_data = json.loads(event_line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event_data, dict):
            continue

        windows_by_id = apply_event_to_snapshot(event_data, windows_by_id)
        current = focused_window_from_snapshot(windows_by_id)
        previous_id = str(previous.get("id", "") or "")
        current_id = str(current.get("id", "") or "")

        if previous_id and previous_id != current_id:
            for rule in load_rules(rule_cache):
                if rule_matches(rule, previous, current):
                    apply_action(rule, previous, current)

        previous = current

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
