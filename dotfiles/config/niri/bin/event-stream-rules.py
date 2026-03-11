#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import socket
import sys
from pathlib import Path
from typing import Any, TextIO


RULES_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "niri"
    / "event-stream-rules.json"
)
NIRI_SOCKET_PATH = os.environ.get("NIRI_SOCKET", "")
SUPPORTED_RULE_EVENTS = {"active-window-changed", "focus-changed"}
RELEVANT_EVENT_TYPES = {
    "WorkspacesChanged",
    "WorkspaceActivated",
    "WorkspaceActiveWindowChanged",
    "WindowsChanged",
    "WindowOpenedOrChanged",
    "WindowClosed",
    "WindowFocusChanged",
}


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


def niri_connect() -> socket.socket:
    if not NIRI_SOCKET_PATH:
        raise RuntimeError("NIRI_SOCKET is not set")

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(NIRI_SOCKET_PATH)
    return client


def send_json_line(sock: socket.socket, payload: Any) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sock.sendall(encoded)
    sock.sendall(b"\n")


def read_json_line(file_obj: TextIO) -> Any:
    response_line = file_obj.readline()
    if not response_line:
        raise RuntimeError("unexpected EOF from niri IPC")
    return json.loads(response_line)


def unwrap_ok_reply(reply: Any) -> Any:
    if not isinstance(reply, dict) or len(reply) != 1:
        raise RuntimeError(f"unexpected IPC reply shape: {reply!r}")

    kind, payload = next(iter(reply.items()))
    if kind == "Ok":
        return payload
    if kind == "Err":
        raise RuntimeError(str(payload))

    raise RuntimeError(f"unexpected IPC reply discriminator: {kind!r}")


def niri_request(payload: Any) -> Any:
    with niri_connect() as sock:
        send_json_line(sock, payload)
        with sock.makefile("r", encoding="utf-8", newline="\n") as file_obj:
            return unwrap_ok_reply(read_json_line(file_obj))


def close_window(window_id: str) -> None:
    if not window_id:
        return

    try:
        niri_request({"Action": {"CloseWindow": {"id": int(window_id)}}})
    except Exception:
        return


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
    if event_name not in SUPPORTED_RULE_EVENTS:
        raise ValueError(f"unsupported event {event_name!r}")

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


def replace_windows(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        return {}

    next_windows: dict[str, dict[str, Any]] = {}
    for window in payload:
        if not isinstance(window, dict):
            continue
        window_id = str(window.get("id", "") or "")
        if window_id:
            next_windows[window_id] = dict(window)
    return next_windows


def replace_workspaces(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        return {}

    next_workspaces: dict[str, dict[str, Any]] = {}
    for workspace in payload:
        if not isinstance(workspace, dict):
            continue
        workspace_id = str(workspace.get("id", "") or "")
        if workspace_id:
            next_workspaces[workspace_id] = dict(workspace)
    return next_workspaces


def apply_event_to_state(
    event_type: str,
    payload: Any,
    windows_by_id: dict[str, dict[str, Any]],
    workspaces_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    updated_windows = windows_by_id
    updated_workspaces = workspaces_by_id

    if event_type == "WorkspacesChanged" and isinstance(payload, dict):
        updated_workspaces = replace_workspaces(payload.get("workspaces"))
    elif event_type == "WorkspaceActivated" and isinstance(payload, dict):
        workspace_id = str(payload.get("id", "") or "")
        focused = payload.get("focused")
        workspace = workspaces_by_id.get(workspace_id)
        if workspace_id and isinstance(workspace, dict):
            if updated_workspaces is workspaces_by_id:
                updated_workspaces = dict(workspaces_by_id)

            output_name = workspace.get("output")
            for existing_workspace_id, existing_workspace in updated_workspaces.items():
                next_workspace = existing_workspace
                if existing_workspace.get("output") == output_name:
                    next_workspace = {
                        **next_workspace,
                        "is_active": existing_workspace_id == workspace_id,
                    }
                if focused is True:
                    next_workspace = {
                        **next_workspace,
                        "is_focused": existing_workspace_id == workspace_id,
                    }
                updated_workspaces[existing_workspace_id] = next_workspace
    elif event_type == "WorkspaceActiveWindowChanged" and isinstance(payload, dict):
        workspace_id = str(payload.get("workspace_id", "") or "")
        if workspace_id and workspace_id in workspaces_by_id:
            if updated_workspaces is workspaces_by_id:
                updated_workspaces = dict(workspaces_by_id)
            workspace = dict(updated_workspaces[workspace_id])
            workspace["active_window_id"] = payload.get("active_window_id")
            updated_workspaces[workspace_id] = workspace
    elif event_type == "WindowsChanged" and isinstance(payload, dict):
        updated_windows = replace_windows(payload.get("windows"))
    elif event_type == "WindowOpenedOrChanged" and isinstance(payload, dict):
        window_payload = payload.get("window")
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
    elif event_type == "WindowClosed" and isinstance(payload, dict):
        window_id = str(payload.get("id", "") or "")
        if window_id and window_id in updated_windows:
            if updated_windows is windows_by_id:
                updated_windows = dict(windows_by_id)
            updated_windows.pop(window_id, None)
    elif event_type == "WindowFocusChanged" and isinstance(payload, dict):
        focused_window_id = str(payload.get("id", "") or "")
        if updated_windows is windows_by_id:
            updated_windows = dict(windows_by_id)
        for existing_window_id, existing_window in updated_windows.items():
            should_be_focused = bool(
                focused_window_id and existing_window_id == focused_window_id
            )
            if existing_window.get("is_focused") is should_be_focused:
                continue
            updated_windows[existing_window_id] = {
                **existing_window,
                "is_focused": should_be_focused,
            }

    return updated_windows, updated_workspaces


def focused_window_from_state(windows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for window in windows_by_id.values():
        if window.get("is_focused") is True:
            return dict(window)
    return {}


def active_window_from_state(
    windows_by_id: dict[str, dict[str, Any]],
    workspaces_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    preferred_workspace: dict[str, Any] | None = None
    for workspace in workspaces_by_id.values():
        if workspace.get("is_focused") is True:
            preferred_workspace = workspace
            break

    if preferred_workspace is None:
        active_workspaces = [
            workspace
            for workspace in workspaces_by_id.values()
            if workspace.get("is_active") is True
        ]
        if len(active_workspaces) == 1:
            preferred_workspace = active_workspaces[0]

    if preferred_workspace is None:
        return {}

    active_window_id = str(preferred_workspace.get("active_window_id", "") or "")
    if not active_window_id:
        return {}

    window = windows_by_id.get(active_window_id)
    if not isinstance(window, dict):
        return {}

    return dict(window)


def process_transition(
    event_name: str,
    rule_cache: RuleCache,
    previous: dict[str, Any],
    current: dict[str, Any],
) -> None:
    previous_id = str(previous.get("id", "") or "")
    current_id = str(current.get("id", "") or "")
    if not previous_id or previous_id == current_id:
        return

    for rule in load_rules(rule_cache):
        if rule.event != event_name:
            continue
        if rule_matches(rule, previous, current):
            apply_action(rule, previous, current)


def main() -> int:
    rule_cache = RuleCache()
    windows_by_id: dict[str, dict[str, Any]] = {}
    workspaces_by_id: dict[str, dict[str, Any]] = {}
    previous_active: dict[str, Any] = {}
    previous_focused: dict[str, Any] = {}

    try:
        with niri_connect() as sock:
            send_json_line(sock, "EventStream")
            with sock.makefile("r", encoding="utf-8", newline="\n") as file_obj:
                reply = unwrap_ok_reply(read_json_line(file_obj))
                if reply != "Handled":
                    print(f"event-stream-rules: unexpected EventStream reply: {reply!r}", file=sys.stderr)
                    return 1

                for event_line in file_obj:
                    if not event_line.strip():
                        continue

                    try:
                        event = json.loads(event_line)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(event, dict) or len(event) != 1:
                        continue

                    event_type, payload = next(iter(event.items()))
                    if event_type not in RELEVANT_EVENT_TYPES:
                        continue

                    windows_by_id, workspaces_by_id = apply_event_to_state(
                        event_type,
                        payload,
                        windows_by_id,
                        workspaces_by_id,
                    )

                    current_active = active_window_from_state(windows_by_id, workspaces_by_id)
                    current_focused = focused_window_from_state(windows_by_id)

                    process_transition(
                        "active-window-changed",
                        rule_cache,
                        previous_active,
                        current_active,
                    )
                    process_transition(
                        "focus-changed",
                        rule_cache,
                        previous_focused,
                        current_focused,
                    )

                    previous_active = current_active
                    previous_focused = current_focused
    except Exception as exc:
        print(f"event-stream-rules: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
